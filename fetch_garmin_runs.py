"""Fetch recent running activities from Garmin Connect Personal API."""

from __future__ import annotations

import argparse
import getpass
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator


ROOT = Path(__file__).resolve().parent
TOKEN_CACHE = ROOT / ".garmin-private" / "bearer-token-cache.json"
OUTPUT = ROOT / "data" / "running_activities.json"
PAGE_SIZE = 100


def activity_items(response: Any) -> list[dict[str, Any]]:
    """Normalize the API's activity list response across list/envelope shapes."""
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
            raise RuntimeError(
                "Garmin returned an unexpected activity response shape. "
                "No local data file was written."
            )
    else:
        raise RuntimeError(
            "Garmin returned an unexpected activity response type. "
            "No local data file was written."
        )

    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError(
            "Garmin returned an unexpected activity item. No local data file was written."
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download your recent Garmin running activity summaries."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days to include (default: 365).",
    )
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be at least 1")

    api_key = getpass.getpass("Garmin Personal API key (input hidden): ").strip()
    if not api_key:
        parser.error("No API key entered")

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days - 1)
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)

    with PersonalApiAuthenticator(bearer_token_cache_file=TOKEN_CACHE) as auth:
        token = auth.obtain_token(api_key)

    # Drop the reference as soon as authentication is complete; only the short-lived
    # bearer token is cached locally by the official client.
    del api_key

    runs: list[dict[str, Any]] = []
    offset = 0
    with GarminPersonalApiClient(token.access_token) as client:
        while True:
            page = activity_items(
                client.search_activities(
                    start=offset,
                    limit=PAGE_SIZE,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    activity_type="running",
                )
            )
            runs.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "Garmin Connect Personal API",
        "activity_type": "running",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "count": len(runs),
        "activities": runs,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Downloaded {len(runs)} running activities ({start_date} to {end_date}).")
    print(f"Saved locally to: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
