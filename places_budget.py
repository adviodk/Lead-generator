"""Shared month-keyed call ledger for Google Places API usage.

Both places_enrich.py and places_pull.py record every Places API call here so a
single monthly budget covers all of them. The point is a hard guarantee that
runaway or repeated runs cannot quietly cross the 5000-calls/month free tier.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

LEDGER = Path(__file__).parent / "places_usage.json"
MONTHLY_CAP_DEFAULT = int(os.environ.get("PLACES_MONTHLY_CAP", "4500"))


def _month() -> str:
    return datetime.date.today().strftime("%Y-%m")


def _load() -> dict:
    try:
        return json.loads(LEDGER.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def used_this_month() -> int:
    return int(_load().get(_month(), 0))


def record(n: int) -> None:
    if n <= 0:
        return
    data = _load()
    data[_month()] = int(data.get(_month(), 0)) + int(n)
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(LEDGER)


def check_budget(planned: int, cap: int = MONTHLY_CAP_DEFAULT) -> None:
    """Raise SystemExit if this run would push the month's total over `cap`."""
    used = used_this_month()
    if used + planned > cap:
        raise SystemExit(
            f"AFVIST: månedsloft for Places-kald nået.\n"
            f"  Brugt i {_month()}: {used}\n"
            f"  Denne kørsel vil bruge op til: {planned}\n"
            f"  Loft: {cap}  (fri kvote hos Google: 5000/md)\n"
            f"  Hæv med --monthly-cap <tal> eller sæt PLACES_MONTHLY_CAP i .env, "
            f"hvis du bevidst vil bruge mere."
        )


if __name__ == "__main__":
    print(f"{LEDGER}")
    print(f"Brugt i {_month()}: {used_this_month()} / {MONTHLY_CAP_DEFAULT}")
