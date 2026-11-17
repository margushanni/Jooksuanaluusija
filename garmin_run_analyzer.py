"""Local Garmin running analyzer for FIT files copied from a connected watch."""

from __future__ import annotations

import calendar
import hashlib
import io
import os
import queue
import shutil
import statistics
import sys
import threading
import tkinter as tk
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
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
DEFAULT_MAX_PACE_S_PER_KM = 5 * 60 + 30


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


def _qualifying_work_laps(
    run: Run, min_pace: float | None = None, max_pace: float | None = DEFAULT_MAX_PACE_S_PER_KM
) -> list[tuple[float, float, float]]:
    return [
        (pace, distance, duration)
        for pace, distance, duration in zip(
            run.active_lap_paces, run.active_lap_distances, run.active_lap_durations
        )
        if (min_pace is None or pace >= min_pace)
        and (max_pace is None or pace <= max_pace)
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
        self.start_date_var = tk.StringVar(value="")
        self.end_date_var = tk.StringVar(value="")
        self.min_pace_var = tk.StringVar(value="")
        self.max_pace_var = tk.StringVar(value="5:30")
        self.run_filter_var = tk.StringVar(value="Kõik jooksud")
        self._date_defaults_set = False
        self._local_load_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._build_ui()
        self._refresh()
        self._start_local_file_load()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Garmini jooksuanalüüs", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="RPE-tempovõrdluses saab valida FIT-is aktiivseks märgitud lõikude tempovahemiku; soojendus ja taastumine jäetakse välja.",
            wraplength=940,
        ).pack(anchor="w", pady=(4, 12))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Otsi ühendatud Garmini kella", command=self._scan_watch).pack(side="left")
        ttk.Button(actions, text="Vali FIT-kaust…", command=self._choose_folder).pack(side="left", padx=8)
        ttk.Button(actions, text="Vali FIT-failid…", command=self._choose_files).pack(side="left")
        self.api_button = ttk.Button(actions, text="Impordi API-st…", command=self._import_from_api)
        self.api_button.pack(side="left", padx=8)
        date_filter = ttk.Frame(outer)
        date_filter.pack(fill="x", pady=(0, 8))
        ttk.Label(date_filter, text="Analüüsi kuupäevavahemik:").pack(side="left", padx=(0, 8))
        ttk.Label(date_filter, text="Alates").pack(side="left")
        self.start_date_entry = ttk.Entry(date_filter, textvariable=self.start_date_var, width=12)
        self.start_date_entry.pack(side="left", padx=(4, 3))
        ttk.Button(
            date_filter, text="Vali kuupäev…", command=lambda: self._open_calendar(self.start_date_var)
        ).pack(side="left", padx=(0, 10))
        ttk.Label(date_filter, text="Kuni").pack(side="left")
        self.end_date_entry = ttk.Entry(date_filter, textvariable=self.end_date_var, width=12)
        self.end_date_entry.pack(side="left", padx=(4, 3))
        ttk.Button(
            date_filter, text="Vali kuupäev…", command=lambda: self._open_calendar(self.end_date_var)
        ).pack(side="left", padx=(0, 8))
        ttk.Button(date_filter, text="Kuva kõik kuupäevad", command=self._clear_date_filter).pack(side="left")
        for entry in (self.start_date_entry, self.end_date_entry):
            entry.bind("<Return>", lambda _event: self._refresh())
            entry.bind("<FocusOut>", lambda _event: self._refresh())

        run_filter = ttk.Frame(outer)
        run_filter.pack(fill="x", pady=(0, 8))
        ttk.Label(run_filter, text="Analüüsi jooksud:").pack(side="left", padx=(0, 8))
        self.run_filter_choice = ttk.Combobox(
            run_filter,
            textvariable=self.run_filter_var,
            values=("Kõik jooksud", "Ainult aktiivlõikudega"),
            state="readonly",
            width=24,
        )
        self.run_filter_choice.pack(side="left")
        self.run_filter_choice.bind("<<ComboboxSelected>>", lambda _event: self._refresh())

        pace_filter = ttk.Frame(outer)
        pace_filter.pack(fill="x", pady=(0, 8))
        ttk.Label(pace_filter, text="Analüüsitavate aktiivlõikude tempo (min/km):").pack(side="left", padx=(0, 8))
        ttk.Label(pace_filter, text="Alates (kiireim)").pack(side="left")
        self.min_pace_entry = ttk.Entry(pace_filter, textvariable=self.min_pace_var, width=7)
        self.min_pace_entry.pack(side="left", padx=(4, 8))
        ttk.Label(pace_filter, text="kuni (aeglaseim)").pack(side="left")
        self.max_pace_entry = ttk.Entry(pace_filter, textvariable=self.max_pace_var, width=7)
        self.max_pace_entry.pack(side="left", padx=(4, 8))
        ttk.Button(pace_filter, text="Rakenda", command=self._refresh).pack(side="left")
        ttk.Button(pace_filter, text="Kõik aktiivlõigud", command=self._clear_pace_filter).pack(side="left", padx=8)
        for entry in (self.min_pace_entry, self.max_pace_entry):
            entry.bind("<Return>", lambda _event: self._refresh())

        self.load_progress = ttk.Progressbar(outer, mode="determinate", maximum=1)
        self.load_progress.pack(fill="x", pady=(0, 3))
        self.load_status = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self.load_status, foreground="#555", wraplength=950).pack(anchor="w")

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
            "active_laps": ("Valitud lõikeid", 100),
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

    def _start_local_file_load(self) -> None:
        FIT_DIR.mkdir(parents=True, exist_ok=True)
        unparsed_dir = ROOT / "data" / "unparsed"
        paths = sorted(FIT_DIR.glob("*.fit")) + sorted(unparsed_dir.glob("*.fit"))
        if not paths:
            self.load_status.set("Kohalikke FIT-faile ei leitud.")
            return

        self.load_progress.configure(maximum=len(paths), value=0)
        self.load_status.set(f"Laadin kohalikke FIT-faile taustal: 0/{len(paths)}…")
        worker = threading.Thread(
            target=self._load_local_files,
            args=(paths, unparsed_dir),
            daemon=True,
            name="fit-startup-loader",
        )
        worker.start()
        self.after(100, self._process_local_file_queue)

    def _load_local_files(self, paths: list[Path], unparsed_dir: Path) -> None:
        loaded: dict[str, Run] = {}
        skipped = 0
        errors = 0
        examples: list[str] = []
        recovered = 0
        total = len(paths)
        for index, path in enumerate(paths, start=1):
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
                    loaded[run.key] = run
                else:
                    skipped += 1
            except Exception as exc:
                errors += 1
                if len(examples) < 3:
                    examples.append(f"{path.name}: {exc}")
            if index % 5 == 0 or index == total:
                self._local_load_queue.put(("progress", (index, total)))
        self._local_load_queue.put(("done", (loaded, skipped, errors, examples, recovered)))

    def _process_local_file_queue(self) -> None:
        while True:
            try:
                kind, payload = self._local_load_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                done, total = payload
                self.load_progress.configure(maximum=total, value=done)
                self.load_status.set(f"Laadin kohalikke FIT-faile taustal: {done}/{total}…")
            elif kind == "done":
                loaded, skipped, errors, examples, recovered = payload
                self.runs.update(loaded)
                self._refresh()
                self.load_progress.configure(value=self.load_progress["maximum"])
                summary = f"Kohalike FIT-failide laadimine valmis: {len(loaded)} jooksu."
                if recovered:
                    summary += f" Taastasin {recovered} varasemat jooksu."
                if skipped:
                    summary += f" {skipped} faili ei olnud jooksud."
                if errors:
                    summary += f" {errors} faili lugemisel tekkis viga."
                    if examples:
                        summary += f" Näide: {examples[0]}"
                self.load_status.set(summary)
                return
        self.after(100, self._process_local_file_queue)

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

    def _clear_date_filter(self) -> None:
        self.start_date_var.set("")
        self.end_date_var.set("")
        self._date_defaults_set = True
        self._refresh()

    def _clear_pace_filter(self) -> None:
        self.min_pace_var.set("")
        self.max_pace_var.set("")
        self._refresh()

    def _open_calendar(
        self, target_var: tk.StringVar, *, refresh_analysis: bool = True, parent: tk.Misc | None = None
    ) -> None:
        try:
            selected = date.fromisoformat(target_var.get())
        except ValueError:
            selected = date.today()
        month = [selected.replace(day=1)]

        owner = parent or self
        popup = tk.Toplevel(owner)
        popup.title("Vali kuupäev")
        popup.transient(owner)
        popup.resizable(False, False)
        popup.grab_set()

        header = ttk.Frame(popup, padding=(8, 8, 8, 4))
        header.pack(fill="x")
        body = ttk.Frame(popup, padding=(8, 0, 8, 8))
        body.pack()
        title = ttk.Label(header, width=18, anchor="center")

        def shift_month(delta: int) -> None:
            current = month[0]
            index = current.year * 12 + current.month - 1 + delta
            month[0] = date(index // 12, index % 12 + 1, 1)
            render_month()

        ttk.Button(header, text="‹", width=3, command=lambda: shift_month(-1)).pack(side="left")
        title.pack(side="left", padx=4)
        ttk.Button(header, text="›", width=3, command=lambda: shift_month(1)).pack(side="left")

        def choose_day(day_number: int) -> None:
            target_var.set(month[0].replace(day=day_number).isoformat())
            popup.destroy()
            if refresh_analysis:
                self._refresh()

        def render_month() -> None:
            month_names = (
                "jaanuar", "veebruar", "märts", "aprill", "mai", "juuni",
                "juuli", "august", "september", "oktoober", "november", "detsember",
            )
            title.configure(text=f"{month_names[month[0].month - 1]} {month[0].year}")
            for child in body.winfo_children():
                child.destroy()
            for column, weekday in enumerate(("E", "T", "K", "N", "R", "L", "P")):
                ttk.Label(body, text=weekday, width=4, anchor="center").grid(row=0, column=column, pady=(0, 4))
            for row, week in enumerate(calendar.Calendar(firstweekday=0).monthdayscalendar(
                month[0].year, month[0].month
            ), start=1):
                for column, day_number in enumerate(week):
                    if day_number:
                        ttk.Button(
                            body,
                            text=str(day_number),
                            width=4,
                            command=lambda value=day_number: choose_day(value),
                        ).grid(row=row, column=column, padx=1, pady=1)

        render_month()

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

    def _import_from_api(self) -> None:
        start_var = tk.StringVar(value=self.start_date_var.get() or "2025-01-01")
        end_var = tk.StringVar(value=self.end_date_var.get() or "2025-12-31")
        dialog = tk.Toplevel(self)
        dialog.title("Vali API impordi kuupäevavahemik")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=14)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Vali, millise ajavahemiku jooksud Garmin Connectist alla laadida.").pack(
            anchor="w", pady=(0, 10)
        )

        fields = ttk.Frame(content)
        fields.pack(fill="x")
        ttk.Label(fields, text="Alates").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        start_entry = ttk.Entry(fields, textvariable=start_var, width=13)
        start_entry.grid(row=0, column=1, padx=(0, 4), pady=4)
        ttk.Button(
            fields,
            text="Kalender…",
            command=lambda: self._open_calendar(start_var, refresh_analysis=False, parent=dialog),
        ).grid(row=0, column=2, padx=(0, 12), pady=4)
        ttk.Label(fields, text="Kuni").grid(row=0, column=3, sticky="w", padx=(0, 6), pady=4)
        end_entry = ttk.Entry(fields, textvariable=end_var, width=13)
        end_entry.grid(row=0, column=4, padx=(0, 4), pady=4)
        ttk.Button(
            fields,
            text="Kalender…",
            command=lambda: self._open_calendar(end_var, refresh_analysis=False, parent=dialog),
        ).grid(row=0, column=5, pady=4)

        def continue_to_key() -> None:
            try:
                start_date = date.fromisoformat(start_var.get())
                end_date = date.fromisoformat(end_var.get())
            except ValueError:
                messagebox.showerror(
                    "Vigane kuupäev",
                    "Sisesta kuupäevad kujul AAAA-KK-PP või vali need kalendrist.",
                    parent=dialog,
                )
                return
            if start_date > end_date:
                messagebox.showerror(
                    "Vigane kuupäevavahemik",
                    "Alguskuupäev peab olema lõppkuupäevast varasem või sama.",
                    parent=dialog,
                )
                return
            dialog.destroy()
            self._request_api_key(start_date.isoformat(), end_date.isoformat())

        controls = ttk.Frame(content)
        controls.pack(fill="x", pady=(12, 0))
        ttk.Button(controls, text="Katkesta", command=dialog.destroy).pack(side="right")
        ttk.Button(controls, text="Jätka API võtmega…", command=continue_to_key).pack(side="right", padx=(0, 8))
        start_entry.focus_set()

    def _request_api_key(self, start_date: str, end_date: str) -> None:
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
        self.status.set(f"Ühendun Garmin Connectiga ja otsin jookse: {start_date} kuni {end_date}…")
        self.update_idletasks()
        worker = threading.Thread(
            target=self._download_api_files, args=(api_key, start_date, end_date), daemon=True
        )
        worker.start()

    def _download_api_files(self, api_key: str, start_date: str, end_date: str) -> None:
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
                            start_date=start_date,
                            end_date=end_date,
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
                                f"API impordi FIT-faile alla laaditud: {done}/{total}…"
                            ),
                        )
        except Exception as exc:
            failures.append(str(exc))
        finally:
            try:
                del api_key
            except UnboundLocalError:
                pass
            self.after(
                0,
                lambda: self._finish_api_import(paths, activity_count, failures, start_date, end_date),
            )

    def _finish_api_import(
        self, paths: list[Path], activity_count: int, failures: list[str], start_date: str, end_date: str
    ) -> None:
        self.api_button.configure(state="normal")
        if paths:
            self._date_defaults_set = True
            self.start_date_var.set(start_date)
            self.end_date_var.set(end_date)
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
            f"API import lõpetatud ({start_date} kuni {end_date}): {activity_count} jooksu leitud, "
            f"{added} FIT-jooksu lisatud, "
            f"{skipped} vahele jäetud, {len(failures)} allalaadimisviga."
        )
        if failures:
            detail = "\n".join(failures[:5])
            if examples:
                detail += "\n" + examples[0]
            messagebox.showwarning(
                "Garmin API import",
                f"Leiti {activity_count} jooksu ajavahemikust {start_date} kuni {end_date}; "
                f"FIT-failidest lisati {added}.\n\n{detail}",
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
        if self.runs and not self._date_defaults_set and not (
            self.start_date_var.get() or self.end_date_var.get()
        ):
            dates = [run.start.date() for run in self.runs.values()]
            self.start_date_var.set(min(dates).isoformat())
            self.end_date_var.set(max(dates).isoformat())
            self._date_defaults_set = True
        try:
            start_date = date.fromisoformat(self.start_date_var.get()) if self.start_date_var.get() else None
            end_date = date.fromisoformat(self.end_date_var.get()) if self.end_date_var.get() else None
        except ValueError:
            self.status.set("Kuupäev peab olema kujul AAAA-KK-PP või vali see kalendrist.")
            return
        if start_date and end_date and start_date > end_date:
            self.status.set("Alguskuupäev peab olema lõppkuupäevast varasem või sama.")
            return
        try:
            min_pace = _parse_pace(self.min_pace_var.get())
            max_pace = _parse_pace(self.max_pace_var.get())
        except ValueError:
            self.status.set("Tempo sisesta kujul M:SS min/km, näiteks 4:15.")
            return
        if min_pace is not None and max_pace is not None and min_pace > max_pace:
            self.status.set("Kiireima tempo piir peab olema aeglasema tempo piirist väiksem või sama.")
            return
        for row in self.table.get_children():
            self.table.delete(row)
        filtered = [
            run for run in self.runs.values()
            if (start_date is None or run.start.date() >= start_date)
            and (end_date is None or run.start.date() <= end_date)
            and (self.run_filter_var.get() != "Ainult aktiivlõikudega" or bool(run.active_lap_paces))
        ]
        ordered = sorted(filtered, key=lambda run: run.start, reverse=True)
        for run in ordered:
            key = run.key
            work_laps = _qualifying_work_laps(run, min_pace, max_pace)
            work_pace = (
                sum(lap[2] for lap in work_laps) / (sum(lap[1] for lap in work_laps) / 1000)
                if work_laps else None
            )
            pace_label = (
                _format_pace(work_pace)
                if work_pace is not None
                else "Pole vahemikus" if run.active_lap_paces else "FIT-is märkimata"
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
        self._update_summary(ordered, min_pace, max_pace)

    def _update_summary(self, runs: list[Run], min_pace: float | None, max_pace: float | None) -> None:
        total_km = sum(run.distance_m for run in runs) / 1000
        total_hours = sum(run.duration_s for run in runs) / 3600
        lines = [f"Kokku: {len(runs)} jooksu · {total_km:.1f} km · {total_hours:.1f} tundi"]
        lines.append(f"Jooksufilter: {self.run_filter_var.get()}")
        if not runs:
            lines.append("Valitud filtritele vastavaid jookse ei leidu.")
        rated = [run for run in runs if run.self_rpe is not None or run.self_feel is not None]
        unmarked = len(runs) - len(rated)
        lines.append(f"FIT-enesehinnang olemas: {len(rated)} jooksu · hinnang märkimata: {unmarked} jooksu")
        runs_with_rpe = [run for run in runs if run.self_rpe is not None]
        work_laps = {
            run.key: _qualifying_work_laps(run, min_pace, max_pace)
            for run in runs_with_rpe
        }
        runs_with_active_laps = [run for run in runs_with_rpe if work_laps[run.key]]
        pace_range = _format_pace_range(min_pace, max_pace)
        lines.append(
            f"Lõiguanalüüs ({pace_range}): {len(runs_with_active_laps)}/{len(runs_with_rpe)} "
            "RPE-ga jooksus on valitud vahemikku jäävaid aktiivlõike."
        )
        lines.append(f"RPE järgi · valitud lõikude aja ja distantsi kaalutud keskmine tempo ({pace_range}):")
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
                lower = int(pace // 15) * 15
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


def _parse_pace(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("Tempo peab olema kujul M:SS.")
    minutes, seconds = map(int, parts)
    if seconds >= 60:
        raise ValueError("Tempo sekundid peavad jääma vahemikku 00–59.")
    if minutes == 0 and seconds == 0:
        raise ValueError("Tempo peab olema nullist suurem.")
    return float(minutes * 60 + seconds)


def _format_pace_range(min_pace: float | None, max_pace: float | None) -> str:
    if min_pace is None and max_pace is None:
        return "kõik tempod"
    if min_pace is None:
        return f"kuni {_format_pace(max_pace)}/km"
    if max_pace is None:
        return f"alates {_format_pace(min_pace)}/km"
    return f"{_format_pace(min_pace)}–{_format_pace(max_pace)}/km"


if __name__ == "__main__":
    app = RunAnalyzer()
    app.mainloop()
