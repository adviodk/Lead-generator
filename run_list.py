"""Take a pasted/loose lead list -> website check + score -> Google Sheet.

    .venv/bin/python run_list.py leads_input.txt
    .venv/bin/python run_list.py leads_input.txt --dry-run
    .venv/bin/python run_list.py leads_input.csv --keep-all

Accepts CSV / TSV / semicolon / pipe / "name - phone - website" lines. A header
row is used if present (navn/firma, telefon/tlf, web/hjemmeside/url). Otherwise
the first field is the name and phone/website are detected by pattern. Missing
website => treated as "ingen" (lead kept).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys

from run import enrich_and_filter
from sheets import append_leads

_NAME_H = ("navn", "firma", "virksomhed", "name", "company")
_PHONE_H = ("telefon", "tlf", "phone", "mobil", "nummer")
_WEB_H = ("web", "hjemmeside", "url", "site", "www", "domæne", "domaene")

_PHONE_RE = re.compile(r"[\d()+\-.\s]{6,}")
_WEB_RE = re.compile(r"(https?://|www\.)|([a-z0-9-]+\.(dk|com|net|org|eu|nu|de|se|no|io|biz))", re.I)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _looks_phone(s: str) -> bool:
    d = _digits(s)
    return 6 <= len(d) <= 15 and bool(_PHONE_RE.fullmatch(s.strip() or " "))


def _clean_web(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"\[[^\]]*\]\(\s*([^)\s]+)\s*\)", s)  # markdown link -> its URL
    if m:
        s = m.group(1)
    s = re.sub(r"\s+", "", s)          # "keba-byg .dk" -> "keba-byg.dk"
    return s.strip().strip("<>\"'")


def _looks_web(s: str) -> bool:
    s = _clean_web(s)
    return bool(s) and bool(_WEB_RE.search(s))


def _split_line(line: str) -> list[str]:
    for delim in ("\t", ";", "|", ","):
        if delim in line:
            return [c.strip() for c in next(csv.reader(io.StringIO(line), delimiter=delim))]
    if " - " in line:
        return [c.strip() for c in line.split(" - ")]
    return [line.strip()]


def parse(text: str) -> list[dict]:
    # split every line into cells, drop rows that are entirely empty (handles
    # leading ",,,,," junk rows and blank lines from spreadsheet exports)
    grid = [_split_line(ln) for ln in text.splitlines()]
    grid = [cells for cells in grid if any(c.strip() for c in cells)]
    if not grid:
        return []

    # optional header (now reliably the first non-empty row)
    first = [c.lower() for c in grid[0]]
    idx = {}
    if any(any(h in c for h in _NAME_H) for c in first):
        for i, c in enumerate(first):
            if "name" not in idx and any(h in c for h in _NAME_H):
                idx["name"] = i
            elif "phone" not in idx and any(h in c for h in _PHONE_H):
                idx["phone"] = i
            elif "web" not in idx and any(h in c for h in _WEB_H):
                idx["web"] = i
        grid = grid[1:]

    leads = []
    for cells in grid:
        if not any(c.strip() for c in cells):
            continue
        if idx:
            name = cells[idx.get("name", 0)] if idx.get("name", 0) < len(cells) else ""
            phone = cells[idx["phone"]] if "phone" in idx and idx["phone"] < len(cells) else ""
            web = cells[idx["web"]] if "web" in idx and idx["web"] < len(cells) else ""
        else:
            nonempty = [c for c in cells if c.strip()]
            if not nonempty:
                continue
            name = nonempty[0]
            rest = nonempty[1:]
            phone = next((c for c in rest if _looks_phone(c)), "")
            web = next((c for c in rest if _looks_web(c)), "")
        name = name.strip(" \"'")
        if not name:
            continue
        leads.append({
            "virksomhedsnavn": name,
            "telefon": phone.strip(),
            "hjemmeside": _clean_web(web),
        })
    return leads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="path to the pasted list (txt/csv/tsv)")
    ap.add_argument("--tab", default=None, help="worksheet/tab name in the Google Sheet")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-all", action="store_true")
    args = ap.parse_args()

    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    leads = parse(text)
    print(f"{len(leads)} leads parsed. Tjekker hjemmesider...\n")
    if not leads:
        print("Ingen leads fundet i input.")
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
