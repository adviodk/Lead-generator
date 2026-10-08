"""Lead source: Google Places API (New) Text Search.

Official API — same business data as Google Maps (name, phone, website, address).
Needs a Google Cloud API key with "Places API (New)" enabled and billing on.
Put it in .env as GOOGLE_MAPS_API_KEY. Free tier: 5000 Text Search calls/month.
"""
from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv

import places_budget

load_dotenv()

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.formattedAddress",
    "nextPageToken",
])

# Danish trade keywords — "håndværkere, alle brancher".
TRADES = [
    "tømrer", "snedker", "elektriker", "VVS", "blikkenslager", "maler",
    "murer", "tagdækker", "glarmester", "gulvlægger", "kloakmester",
    "brolægger", "stukkatør", "isoleringsfirma", "smed", "anlægsgartner",
    "entreprenør", "byggefirma", "belægning", "facaderenovering",
]

# Odense centre, ~13 km bias radius.
ODENSE = {"latitude": 55.4038, "longitude": 10.4024}


def _key() -> str:
    k = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not k:
        raise SystemExit("GOOGLE_MAPS_API_KEY not set in .env")
    return k


def _search(query: str, center: dict, radius_m: float, max_pages: int = 3) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _key(),
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "textQuery": query,
        "languageCode": "da",
        "regionCode": "DK",
        "pageSize": 20,
        "locationBias": {"circle": {"center": center, "radius": radius_m}},
    }
    out, token, pages = [], None, 0
    while pages < max_pages:
        if token:
            body["pageToken"] = token
        r = requests.post(SEARCH_URL, json=body, headers=headers, timeout=30)
        places_budget.record(1)  # count every call that reached Google
        if r.status_code == 429:
            raise SystemExit("Places API 429 RESOURCE_EXHAUSTED — fri kvote brugt op.")
        if r.status_code != 200:
            raise SystemExit(f"Places API {r.status_code}: {r.text[:300]}")
        data = r.json()
        out.extend(data.get("places", []))
        token = data.get("nextPageToken")
        pages += 1
        if not token:
            break
        time.sleep(2)  # page tokens need a moment to become valid
    return out


def _to_lead(pl: dict, trade: str) -> dict:
    return {
        "virksomhedsnavn": (pl.get("displayName") or {}).get("text", ""),
        "telefon": pl.get("nationalPhoneNumber") or pl.get("internationalPhoneNumber") or "",
        "hjemmeside": pl.get("websiteUri") or "",
        "adresse": pl.get("formattedAddress", ""),
        "branche": trade,
        "place_id": pl.get("id", ""),
    }


def pull(city_center: dict | None = None, radius_m: float = 13000,
         trades: list[str] | None = None, city_name: str = "Odense",
         limit: int | None = None, max_pages: int = 3,
         monthly_cap: int = places_budget.MONTHLY_CAP_DEFAULT) -> list[dict]:
    center = city_center or ODENSE
    trades = trades or TRADES
    places_budget.check_budget(len(trades) * max_pages, monthly_cap)
    by_id: dict[str, dict] = {}
    for trade in trades:
        hits = _search(f"{trade} i {city_name}", center, radius_m, max_pages=max_pages)
        added = 0
        for pl in hits:
            lead = _to_lead(pl, trade)
            pid = lead["place_id"]
            if pid and pid not in by_id and lead["virksomhedsnavn"]:
                by_id[pid] = lead
                added += 1
        print(f"  {trade}: {len(hits)} fundet, {added} nye")
        if limit and len(by_id) >= limit:
            break
    leads = list(by_id.values())
    return leads[:limit] if limit else leads


if __name__ == "__main__":
    import json
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = pull(trades=["tømrer"], limit=n)
    print(f"\n{len(rows)} virksomheder")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
