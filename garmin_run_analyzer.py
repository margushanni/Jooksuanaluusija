"""Local Garmin running analyzer for FIT files copied from a connected watch."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import statistics
import sys
import threading
import tkinter as tk
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from garmin_fit_sdk import Decoder, Stream


ROOT = Path(__file__).resolve().parent
MTP_VENDOR = ROOT / ".vendor" / "mtp-main"
if MTP_VENDOR.is_dir():
    sys.path.insert(0, str(MTP_VENDOR))
FIT_DIR = ROOT / "data" / "fit"
INCOMING_DIR = ROOT / "data" / ".mtp-incoming"
API_INCOMING_DIR = ROOT / "data" / ".api-incoming"
TOKEN_CACHE = ROOT / ".garmin-private" / "bearer-token-cache.json"
PACE_LIMIT_S_PER_KM = 5 * 60 + 30


@dataclass
class Run:
    key: str
    path: Path
    start: datetime
    distance_m: float
    duration_s: float
    ascent_m: float | None
    sport: str
    self_rpe: float | None
    self_feel: float | None
    active_lap_paces: list[float]
    active_lap_distances: list[float]
    active_lap_durations: list[float]

    @property
    def pace_s_per_km(self) -> float | None:
        if self.distance_m <= 0 or self.duration_s <= 0:
            return None
        return self.duration_s / (self.distance_m / 1000)


def _message_list(messages: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    for key, value in messages.items():
        if kind in key.lower() and isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _safe_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _activity_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        items = response
    elif isinstance(response, dict):
        items = next(
            (
                response[key]
                for key in ("activities", "activityList", "data", "results", "items")
                if isinstance(response.get(key), list)
            ),
            None,
        )
        if items is None:
            if not response:
                return []
            raise RuntimeError("Garmin tagastas tundmatu tegevuste vastuse kuju.")
    else:
        raise RuntimeError("Garmin tagastas tundmatu tegevuste vastuse tüübi.")
    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError("Garmin tagastas ootamatu tegevuse kirje.")
    return items


def decode_run(path: Path) -> Run | None:
    stream = Stream.from_file(str(path))
    decoder = Decoder(stream)
    if not decoder.is_fit():
        return None
    messages, errors = decoder.read()
    if errors:
        raise ValueError("FIT faili lugemisel tekkis viga: " + "; ".join(map(str, errors[:2])))

    sessions = _message_list(messages, "session")
    if not sessions:
        return None
    session = sessions[0]
    sport = str(session.get("sport") or "").lower()
    sub_sport = str(session.get("sub_sport") or "").lower()
    if "run" not in sport and "run" not in sub_sport:
        return None

    records = _message_list(messages, "record")
    distance_m = _safe_number(session.get("total_distance"))
    if not distance_m:
        distances = [_safe_number(row.get("distance")) for row in records]
        distances = [value for value in distances if value is not None]
        distance_m = max(distances, default=0.0)

    duration_s = _safe_number(session.get("total_timer_time"))
    if not duration_s:
        duration_s = _safe_number(session.get("total_elapsed_time")) or 0.0

    started = session.get("start_time")
    if not isinstance(started, datetime):
        timestamps = [row.get("timestamp") for row in records]
        timestamps = [value for value in timestamps if isinstance(value, datetime)]
        started = min(timestamps) if timestamps else None
    if not isinstance(started, datetime):
        return None

    ascent_m = _safe_number(session.get("total_ascent"))
    active_lap_paces: list[float] = []
    active_lap_distances: list[float] = []
    active_lap_durations: list[float] = []
    for lap in _message_list(messages, "lap"):
        if str(lap.get("intensity") or "").lower() != "active":
            continue
        distance = _safe_number(lap.get("total_distance")) or 0.0
        duration = _safe_number(lap.get("total_timer_time")) or _safe_number(
            lap.get("total_elapsed_time")
        ) or 0.0
        if distance > 0 and duration > 0:
            active_lap_paces.append(duration / (distance / 1000))
            active_lap_distances.append(distance)
            active_lap_durations.append(duration)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Run(
        key=digest,
        path=path,
        start=started,
        distance_m=distance_m or 0.0,
        duration_s=duration_s,
        ascent_m=ascent_m,
        sport=sport or sub_sport or "unknown",
        self_rpe=(
            _safe_number(session.get("workout_rpe")) / 10
            if _safe_number(session.get("workout_rpe")) is not None
            else None
        ),
        self_feel=_safe_number(session.get("workout_feel")),
        active_lap_paces=active_lap_paces,
        active_lap_distances=active_lap_distances,
        active_lap_durations=active_lap_durations,
    )


def _qualifying_work_laps(run: Run) -> list[tuple[float, float, float]]:
    return [
        (pace, distance, duration)
        for pace, distance, duration in zip(
            run.active_lap_paces, run.active_lap_distances, run.active_lap_durations
        )
        if pace <= PACE_LIMIT_S_PER_KM
    ]


def discover_activity_folders() -> list[Path]:
    """Find common Garmin mass-storage activity folders on Windows drive letters."""
    folders: list[Path] = []
    if os.name != "nt":
        return folders
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = Path(f"{letter}:\\")
        activity = drive / "GARMIN" / "ACTIVITY"
        if activity.is_dir():
            folders.append(activity)
    return folders


def _mtp_activity_folders(device: Any) -> list[Any]:
    """Find GARMIN/ACTIVITY folders through Windows Portable Devices (MTP)."""
    found: list[Any] = []
    pending = list(device.get_content())
    while pending:
        node = pending.pop()
        if getattr(node, "content_type", -1) not in (0, 1):  # WPD storage or directory
            continue
        children = list(node.get_children())
        if str(getattr(node, "name", "")).casefold() == "garmin":
            found.extend(
                child for child in children
                if str(getattr(child, "name", "")).casefold() == "activity"
            )
            continue
        pending.extend(child for child in children if getattr(child, "content_type", -1) in (0, 1))
    return found


def download_mtp_fit_files(status_callback: Any = None) -> tuple[list[Path], list[str], str | None]:
    """Download FIT files from connected MTP devices to a temporary local folder."""
    try:
        from mtp.win_access import get_portable_devices
    except ImportError:
        return [], [], "MTP toe tugi puudub. Käivita setup_run_analyzer.ps1 uuesti."

    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    try:
        devices = get_portable_devices()
    except Exception as exc:
        return [], [], f"Windowsi MTP-seadmete päring ebaõnnestus: {exc}"

    downloaded: list[Path] = []
    device_names: list[str] = []
    errors: list[str] = []
    for device in devices:
        device_names.append(str(getattr(device, "name", "Garmin")))
        try:
            activities = _mtp_activity_folders(device)
            for activity_folder in activities:
                pending = [activity_folder]
                while pending:
                    folder = pending.pop()
                    try:
                        children = list(folder.get_children())
                    except Exception as exc:
                        errors.append(f"{getattr(folder, 'full_filename', folder)}: {exc}")
                        continue
                    for item in children:
                        content_type = getattr(item, "content_type", -1)
                        if content_type in (0, 1):
                            pending.append(item)
                        elif str(getattr(item, "name", "")).casefold().endswith(".fit"):
                            identity = f"{getattr(device, 'devicename', device.name)}|{item.full_filename}"
                            temp_path = INCOMING_DIR / (hashlib.sha256(identity.encode()).hexdigest() + ".fit")
                            try:
                                temp_path.unlink(missing_ok=True)
                                item.download_file(str(temp_path))
                                downloaded.append(temp_path)
                                if status_callback and len(downloaded) % 25 == 0:
                                    status_callback(f"Kellast loetud {len(downloaded)} FIT-faili…")
                            except Exception as exc:
                                temp_path.unlink(missing_ok=True)
                                errors.append(f"{item.name}: {exc}")
            if status_callback:
                status_callback(f"MTP-seade läbi vaadatud: {device.name}")
        except Exception as exc:
            errors.append(f"{getattr(device, 'name', 'Garmin')}: {exc}")
        finally:
            try:
                device.close()
            except Exception:
                pass

    error_summary = "; ".join(errors[:3]) if errors else None
    return downloaded, device_names, error_summary


def fit_files_under(folder: Path) -> list[Path]:
    if folder.name.lower() == "activity":
        root = folder
    else:
        candidate = folder / "GARMIN" / "ACTIVITY"
        root = candidate if candidate.is_dir() else folder
    try:
        return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".fit")
    except OSError:
        return []


class RunAnalyzer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Garmini jooksuanalüüs")
        self.geometry("1020x700")
        self.minsize(840, 560)
        self.runs: dict[str, Run] = {}
        self.year_var = tk.StringVar(value="Kõik aastad")
        self._build_ui()
        self._load_local_files()
        if any(run.start.year == 2025 for run in self.runs.values()):
            self.year_var.set("2025")
        self._refresh()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Garmini jooksuanalüüs", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="RPE-tempovõrdluses kasutatakse ainult FIT-is aktiivseks märgitud lõike kuni 5:30/km; soojendus ja taastumine jäetakse välja.",
            wraplength=940,
        ).pack(anchor="w", pady=(4, 12))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Otsi ühendatud Garmini kella", command=self._scan_watch).pack(side="left")
        ttk.Button(actions, text="Vali FIT-kaust…", command=self._choose_folder).pack(side="left", padx=8)
        ttk.Button(actions, text="Vali FIT-failid…", command=self._choose_files).pack(side="left")
        self.api_button = ttk.Button(actions, text="Impordi 2025 API-st", command=self._import_2025_from_api)
        self.api_button.pack(side="left", padx=8)
        ttk.Label(actions, text="Analüüsi aasta:").pack(side="left", padx=(12, 4))
        self.year_choice = ttk.Combobox(
            actions, textvariable=self.year_var, values=("Kõik aastad",), state="readonly", width=12
        )
        self.year_choice.pack(side="left")
        self.year_choice.bind("<<ComboboxSelected>>", lambda _event: self._refresh())

        columns = (
            "date", "self_rating", "distance", "duration", "active_laps",
            "work_pace", "work_time", "work_distance", "ascent",
        )
        self.table = ttk.Treeview(outer, columns=columns, show="headings", selectmode="browse", height=16)
        headers = {
            "date": ("Kuupäev", 130),
            "self_rating": ("Enesehinnang", 180),
            "distance": ("Distants", 100),
            "duration": ("Aeg", 90),
            "active_laps": ("Lõikeid ≤5:30", 90),
            "work_pace": ("Töötempo", 105),
            "work_time": ("Töömin", 75),
            "work_distance": ("Töökilomeetrid", 110),
            "ascent": ("Tõus", 80),
        }
        for col, (title, width) in headers.items():
            self.table.heading(col, text=title)
            self.table.column(col, width=width, anchor="center")
        self.table.pack(fill="both", expand=True)

        ttk.Label(outer, text="Kokkuvõte", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 2))
        summary_box = ttk.Frame(outer)
        summary_box.pack(fill="x")
        self.summary = tk.Text(summary_box, height=14, wrap="word", state="disabled", font=("Consolas", 10))
        summary_scroll = ttk.Scrollbar(summary_box, orient="vertical", command=self.summary.yview)
        self.summary.configure(yscrollcommand=summary_scroll.set)
        self.summary.pack(side="left", fill="both", expand=True)
        summary_scroll.pack(side="right", fill="y")
        self.status = tk.StringVar(value="Ühenda kell USB-ga ja vajuta otsingunuppu või vali Activity-kaust.")
        ttk.Label(outer, textvariable=self.status, foreground="#555", wraplength=950).pack(anchor="w", pady=(8, 0))

    def _load_local_files(self) -> None:
        FIT_DIR.mkdir(parents=True, exist_ok=True)
        unparsed_dir = ROOT / "data" / "unparsed"
        paths = sorted(FIT_DIR.glob("*.fit")) + sorted(unparsed_dir.glob("*.fit"))
        recovered = 0
        for path in paths:
            try:
                run = decode_run(path)
                if run:
                    if path.parent == unparsed_dir:
                        target = FIT_DIR / f"{run.key}.fit"
                        if target.exists():
                            path.unlink(missing_ok=True)
                        else:
                            shutil.move(str(path), str(target))
                        run.path = target
                        recovered += 1
                    self.runs[run.key] = run
            except Exception:
                continue
        if recovered:
            self.status.set(f"Taastasin varasemast impordist {recovered} jooksu.")

    def _scan_watch(self) -> None:
        folders = discover_activity_folders()
        paths = [path for folder in folders for path in fit_files_under(folder)]
        self.status.set("Otsin ühendatud kella FIT-faile…")
        self.update_idletasks()
        mtp_paths, device_names, mtp_error = download_mtp_fit_files(
            lambda text: (self.status.set(text), self.update_idletasks())
        )
        paths.extend(mtp_paths)
        if not paths and not device_names and mtp_error:
            messagebox.showerror("Kella otsing ebaõnnestus", mtp_error)
            self.status.set("Kella ei leitud. Vali FIT-kaust või failid käsitsi.")
            return
        if not paths:
            if device_names:
                messagebox.showinfo(
                    "Tegevusfaile ei leitud",
                    f"Seade tuvastati ({', '.join(device_names)}), kuid GARMIN\\ACTIVITY alt ei leitud FIT-faile.",
                )
            else:
                messagebox.showinfo("Kella ei leitud", "Ühtegi ühendatud Garmini kella ei leitud.")
            self.status.set("Kella otsing lõpetatud; FIT-faile ei leitud.")
            return
        added, skipped, errors, _examples = self._import_files(paths)
        for path in mtp_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            INCOMING_DIR.rmdir()
        except OSError:
            pass
        if mtp_error:
            self.status.set(f"Import: {added} jooksu, {skipped} vahele jäetud, {errors} viga. {mtp_error}")
        elif device_names:
            self.status.set(
                f"Seade(d): {', '.join(device_names)}. {len(paths)} FIT-faili leitud; "
                f"{added} jooksu lisatud, {skipped} vahele jäetud, {errors} viga."
            )

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="Vali Garmin Activity-kaust või FIT-failidega kaust")
        if folder:
            self._import_files(fit_files_under(Path(folder)))

    def _choose_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Vali Garmin FIT-failid",
            filetypes=(("FIT-failid", "*.fit"), ("Kõik failid", "*.*")),
        )
        if paths:
            self._import_files([Path(path) for path in paths])

    def _import_2025_from_api(self) -> None:
        api_key = simpledialog.askstring(
            "Garmin Personal API",
            "Sisesta Garmini Personal API võti. Seda ei salvestata; kasutatakse ainult selle päringu jaoks.",
            show="*",
            parent=self,
        )
        if not api_key or not api_key.strip():
            return

        api_key = api_key.strip()
        self.api_button.configure(state="disabled")
        self.status.set("Ühendun Garmin Connectiga ja otsin 2025. aasta jookse…")
        self.update_idletasks()
        worker = threading.Thread(target=self._download_2025_api_files, args=(api_key,), daemon=True)
        worker.start()

    def _download_2025_api_files(self, api_key: str) -> None:
        paths: list[Path] = []
        failures: list[str] = []
        activity_count = 0
        try:
            from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator

            API_INCOMING_DIR.mkdir(parents=True, exist_ok=True)
            with PersonalApiAuthenticator(bearer_token_cache_file=TOKEN_CACHE) as auth:
                token = auth.obtain_token(api_key)
            del api_key

            with GarminPersonalApiClient(token.access_token) as client:
                activities: list[dict[str, Any]] = []
                offset = 0
                while True:
                    page = _activity_items(
                        client.search_activities(
                            start=offset,
                            limit=100,
                            start_date="2025-01-01",
                            end_date="2025-12-31",
                            activity_type="running",
                        )
                    )
                    activities.extend(page)
                    if len(page) < 100:
                        break
                    offset += 100

                activity_count = len(activities)
                for index, activity in enumerate(activities, start=1):
                    activity_id = activity.get("activityId")
                    if not activity_id:
                        failures.append("Ühel jooksul puudub API vastuses activityId.")
                        continue
                    try:
                        archive_bytes = client.download_activity(activity_id)
                        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                            fit_members = [
                                member for member in archive.infolist()
                                if not member.is_dir() and member.filename.casefold().endswith(".fit")
                            ]
                            if not fit_members:
                                failures.append(f"Tegevuse {activity_id} ZIP-is puudub FIT-fail.")
                                continue
                            for member_index, member in enumerate(fit_members, start=1):
                                target = API_INCOMING_DIR / f"{activity_id}-{member_index}.fit"
                                target.write_bytes(archive.read(member))
                                paths.append(target)
                    except Exception as exc:
                        if len(failures) < 8:
                            failures.append(f"Tegevus {activity_id}: {exc}")
                    if index % 10 == 0 or index == activity_count:
                        self.after(
                            0,
                            lambda done=index, total=activity_count: self.status.set(
                                f"2025 jooksude FIT-faile alla laaditud: {done}/{total}…"
                            ),
                        )
        except Exception as exc:
            failures.append(str(exc))
        finally:
            try:
                del api_key
            except UnboundLocalError:
                pass
            self.after(0, lambda: self._finish_api_import(paths, activity_count, failures))

    def _finish_api_import(
        self, paths: list[Path], activity_count: int, failures: list[str]
    ) -> None:
        self.api_button.configure(state="normal")
        if paths:
            self.year_var.set("2025")
            added, skipped, errors, examples = self._import_files(paths)
        else:
            added, skipped, errors, examples = 0, 0, 0, []
        for path in paths:
            path.unlink(missing_ok=True)
        try:
            API_INCOMING_DIR.rmdir()
        except OSError:
            pass

        self._refresh()
        self.status.set(
            f"2025 API import lõpetatud: {activity_count} jooksu leitud, {added} FIT-jooksu lisatud, "
            f"{skipped} vahele jäetud, {len(failures)} allalaadimisviga."
        )
        if failures:
            detail = "\n".join(failures[:5])
            if examples:
                detail += "\n" + examples[0]
            messagebox.showwarning(
                "Garmin API import",
                f"Leiti {activity_count} 2025. aasta jooksu; FIT-failidest lisati {added}.\n\n{detail}",
            )

    def _import_files(self, paths: list[Path]) -> tuple[int, int, int, list[str]]:
        if not paths:
            self.status.set("Valitud asukohast FIT-faile ei leitud.")
            return 0, 0, 0, []
        added = 0
        skipped = 0
        errors = 0
        examples: list[str] = []
        for source in paths:
            try:
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                if digest in self.runs:
                    skipped += 1
                    continue
                target = FIT_DIR / f"{digest}.fit"
                if not target.exists():
                    shutil.copy2(source, target)
                run = decode_run(target)
                if run is None:
                    if source.parent == INCOMING_DIR:
                        diagnostic_dir = ROOT / "data" / "unparsed"
                        diagnostic_dir.mkdir(parents=True, exist_ok=True)
                        diagnostic_path = diagnostic_dir / f"{digest}.fit"
                        if not diagnostic_path.exists():
                            shutil.copy2(source, diagnostic_path)
                    target.unlink(missing_ok=True)
                    skipped += 1
                    continue
                self.runs[run.key] = run
                added += 1
            except Exception as exc:
                errors += 1
                if len(examples) < 3:
                    examples.append(f"{source.name}: {exc}")
        self._refresh()
        self.status.set(
            f"Leitud {len(paths)} FIT-faili; lisatud jooksuna {added}; "
            f"vahele jäetud {skipped}; lugemisvead {errors}."
        )
        if added == 0 and paths:
            details = f"Leiti {len(paths)} FIT-faili, kuid ühtegi jooksu ei lisatud."
            if skipped:
                details += f" {skipped} faili ei tuvastatud jooksuna või nende FIT-struktuuri ei õnnestunud tõlgendada."
            if examples:
                details += "\n\nNäidisviga: " + examples[0]
            details += "\n\nLeitud, kuid tõlgendamata kellafailid on säilitatud kaustas data\\unparsed."
            messagebox.showwarning("FIT-faile ei saanud kuvada", details)
        return added, skipped, errors, examples

    def _refresh(self) -> None:
        years = sorted({str(run.start.year) for run in self.runs.values()}, reverse=True)
        year_values = ("Kõik aastad", *years)
        self.year_choice.configure(values=year_values)
        if self.year_var.get() not in year_values:
            self.year_var.set("Kõik aastad")
        for row in self.table.get_children():
            self.table.delete(row)
        selected_year = self.year_var.get()
        filtered = [
            run for run in self.runs.values()
            if selected_year == "Kõik aastad" or str(run.start.year) == selected_year
        ]
        ordered = sorted(filtered, key=lambda run: run.start, reverse=True)
        for run in ordered:
            key = run.key
            work_laps = _qualifying_work_laps(run)
            work_pace = (
                sum(lap[2] for lap in work_laps) / (sum(lap[1] for lap in work_laps) / 1000)
                if work_laps else None
            )
            pace_label = (
                _format_pace(work_pace)
                if work_pace is not None
                else "Pole ≤5:30" if run.active_lap_paces else "FIT-is märkimata"
            )
            self.table.insert(
                "",
                "end",
                iid=key,
                values=(
                    run.start.strftime("%Y-%m-%d %H:%M"),
                    _format_self_rating(run),
                    f"{run.distance_m / 1000:.2f} km",
                    _format_duration(run.duration_s),
                    str(len(work_laps)) if run.active_lap_paces else "—",
                    pace_label,
                    f"{sum(lap[2] for lap in work_laps) / 60:.0f} min" if work_laps else "—",
                    f"{sum(lap[1] for lap in work_laps) / 1000:.1f} km" if work_laps else "—",
                    f"{run.ascent_m:.0f} m" if run.ascent_m is not None else "—",
                ),
            )
        self._update_summary(ordered)

    def _update_summary(self, runs: list[Run]) -> None:
        total_km = sum(run.distance_m for run in runs) / 1000
        total_hours = sum(run.duration_s for run in runs) / 3600
        lines = [f"Kokku: {len(runs)} jooksu · {total_km:.1f} km · {total_hours:.1f} tundi"]
        rated = [run for run in runs if run.self_rpe is not None or run.self_feel is not None]
        unmarked = len(runs) - len(rated)
        lines.append(f"FIT-enesehinnang olemas: {len(rated)} jooksu · hinnang märkimata: {unmarked} jooksu")
        runs_with_rpe = [run for run in runs if run.self_rpe is not None]
        work_laps = {
            run.key: _qualifying_work_laps(run)
            for run in runs_with_rpe
        }
        runs_with_active_laps = [run for run in runs_with_rpe if work_laps[run.key]]
        lines.append(
            f"Lõiguanalüüs: {len(runs_with_active_laps)}/{len(runs_with_rpe)} RPE-ga jooksus on aktiivseid lõike tempoga kuni 5:30/km."
        )
        lines.append("RPE järgi · aktiivse töö aja ja distantsi kaalutud keskmine tempo kuni 5:30/km:")
        rpe_values = sorted({run.self_rpe for run in runs if run.self_rpe is not None})
        for rpe in rpe_values:
            group = [run for run in runs if run.self_rpe == rpe]
            selected = [run for run in group if work_laps.get(run.key)]
            paces = [
                sum(lap[2] for lap in work_laps[run.key]) / (sum(lap[1] for lap in work_laps[run.key]) / 1000)
                for run in selected
            ]
            active_minutes = [sum(lap[2] for lap in work_laps[run.key]) / 60 for run in selected]
            active_km = [sum(lap[1] for lap in work_laps[run.key]) / 1000 for run in selected]
            pace_text = f"{_format_pace(statistics.median(paces))}/km" if paces else "—"
            lines.append(
                f"  RPE {rpe:g}/10: {len(group):>3} jooksu · lõikudega {len(paces):>2} · keskmine töötempo {pace_text} · "
                f"aktiivtöö mediaan {statistics.median(active_minutes):.0f} min / {statistics.median(active_km):.1f} km"
                if paces else f"  RPE {rpe:g}/10: {len(group):>3} jooksu · aktiivseid lõike pole"
            )

        pace_bins: dict[int, dict[str, list[tuple[float, float, float]]]] = {}
        run_by_key = {run.key: run for run in runs_with_rpe}
        for run in runs_with_rpe:
            for pace, distance, duration in work_laps[run.key]:
                lower = min(int(pace // 15) * 15, PACE_LIMIT_S_PER_KM - 15)
                pace_bins.setdefault(lower, {}).setdefault(run.key, []).append((pace, distance, duration))
        lines.append("Tempo kaupa · 15-sekundilised vahemikud (n = eri treeningud):")
        for lower, grouped_runs in sorted(pace_bins.items()):
            rpes = [run_by_key[key].self_rpe for key in grouped_runs]
            workouts = len(grouped_runs)
            segments = sum(len(values) for values in grouped_runs.values())
            minutes = [sum(lap[2] for lap in laps) / 60 for laps in grouped_runs.values()]
            distance_km = [sum(lap[1] for lap in laps) / 1000 for laps in grouped_runs.values()]
            label = f"{_format_pace(lower)}–{_format_pace(lower + 15)}/km"
            lines.append(
                f"  {label}: RPE {statistics.median(rpes):g} · {workouts} treeningut / {segments} lõiku · "
                f"mediaan {statistics.median(minutes):g} min, {statistics.median(distance_km):g} km selles vahemikus"
            )
        feel_values = [run.self_feel for run in runs if run.self_feel is not None]
        if feel_values:
            lines.append("RPE ja töölõikude tempo enesetunde järgi (workout_feel: 0 kehv – 100 hea):")
            for feel in sorted(set(feel_values)):
                group = [run for run in runs if run.self_feel == feel]
                rpes = [run.self_rpe for run in group if run.self_rpe is not None]
                paces = [
                    sum(lap[2] for lap in work_laps[run.key]) / (sum(lap[1] for lap in work_laps[run.key]) / 1000)
                    for run in group if work_laps.get(run.key)
                ]
                rpe_text = f"{statistics.median(rpes):g}/10" if rpes else "—"
                pace_text = f"{_format_pace(statistics.mean(paces))}/km" if paces else "—"
                lines.append(
                    f"  tunne {feel:g}/100: {len(group):>3} jooksu · mediaan-RPE {rpe_text} · keskmine töötempo {pace_text}"
                )
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.configure(state="disabled")


def _format_self_rating(run: Run) -> str:
    parts = []
    if run.self_rpe is not None:
        parts.append(f"RPE {run.self_rpe:g}/10")
    if run.self_feel is not None:
        parts.append(f"tunne {run.self_feel:g}/100")
    return " · ".join(parts) if parts else "Hinnang - märkimata"


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _format_pace(seconds_per_km: float | None) -> str:
    if seconds_per_km is None or seconds_per_km <= 0:
        return "—"
    total = int(round(seconds_per_km))
    return f"{total // 60}:{total % 60:02d}"


if __name__ == "__main__":
    app = RunAnalyzer()
    app.mainloop()
