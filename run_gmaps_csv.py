"""Google Maps CSV export (Instant Data Scraper etc.) -> website check -> Sheet tab.

    .venv/bin/python run_gmaps_csv.py "~/Downloads/google.csv" --tab "håndværkere fyn" --dry-run
    .venv/bin/python run_gmaps_csv.py "~/Downloads/google.csv" --tab "håndværkere fyn"

Column names in these exports are opaque (hfpxzc href, xxVWCe, UsdlK, ...), so
the name/phone/website columns are detected by content, not header.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re

from run import enrich_and_filter
from sheets import append_leads

_PHONE_RE = re.compile(r"^\+?\d[\d\s().-]{5,}\d$")
_NOISE = {"·", "", "åben", "lukket", "website", "rutevejledning", "gem", "opkald"}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _is_phone(s: str) -> bool:
    s = (s or "").strip()
    return bool(_PHONE_RE.match(s)) and 6 <= len(_digits(s)) <= 12


def _is_site(s: str) -> bool:
    s = (s or "").strip().lower()
    if not s or " " in s:
        return False
    if "google.com" in s or "google.dk" in s or "/maps/" in s:
        return False
    return s.startswith(("http://", "https://")) or bool(re.search(r"[a-z0-9-]+\.[a-z]{2,}", s))


def _detect(rows: list[list[str]]) -> dict:
    ncol = max(len(r) for r in rows)
    phone_hits = [0] * ncol
    site_hits = [0] * ncol
    text_len = [0] * ncol
    for r in rows:
        for i in range(ncol):
            v = r[i].strip() if i < len(r) else ""
            if _is_phone(v):
                phone_hits[i] += 1
            if _is_site(v):
                site_hits[i] += 1
            if v.lower() not in _NOISE and not _is_phone(v) and not v.startswith(("http", "www")):
                text_len[i] += len(v)
    phone_col = max(range(ncol), key=lambda i: phone_hits[i])
    site_col = max(range(ncol), key=lambda i: site_hits[i])
    # name = wordiest text column that isn't the maps-url column (col 0 usually)
    name_col = max((i for i in range(ncol) if i not in (0,)), key=lambda i: text_len[i])
    return {"name": name_col, "phone": phone_col, "site": site_col}


def parse_csv(path: str) -> list[dict]:
    with open(os.path.expanduser(path), encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    if len(rows) < 2:
        return []
    # drop a header row if it has no phone-looking / url-looking cell
    body = rows[1:] if not any(_is_phone(c) or _is_site(c) for c in rows[0]) else rows
    col = _detect(body)

    leads, seen = [], set()
    for r in body:
        get = lambda i: r[i].strip() if i < len(r) else ""
        name = get(col["name"]).strip(" \"'")
        phone = get(col["phone"])
        site = get(col["site"])
        if not _is_phone(phone):
            phone = ""
        if not _is_site(site):
            site = ""
        if not name or name.lower() in _NOISE:
            continue
        key = _digits(phone) or name.lower()
        if key in seen:
            continue
        seen.add(key)
        leads.append({"virksomhedsnavn": name, "telefon": phone, "hjemmeside": site})
    return leads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--tab", default=None, help="worksheet/tab name in the Google Sheet")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-all", action="store_true")
    args = ap.parse_args()

    leads = parse_csv(args.file)
    print(f"{len(leads)} leads parset fra {args.file}. Tjekker hjemmesider...\n")
    if not leads:
        print("Ingen leads fundet.")
        return

    kept = enrich_and_filter(leads, args.keep_all)
    print(f"\n{len(kept)} af {len(leads)} beholdt (dårlig/ingen hjemmeside).")

    if args.dry_run:
        print(json.dumps(kept, ensure_ascii=False, indent=2))
        return
    if not kept:
        print("Intet at skrive.")
        return

    res = append_leads(kept, tab=args.tab)
    where = f'fanen "{args.tab}"' if args.tab else "standardfanen"
    print(f"{where}: +{res['added']} tilføjet, {res['skipped']} sprunget over (dublet).")


if __name__ == "__main__":
    main()
