"""Look up companies by name in Google Places (New) and report who has a website.

Input: a CSV/TSV with NAVN + TELEFON (e.g. the "uden hjemmeside" list).
For each company one Places Text Search call is made; the best match is chosen
(phone match preferred, else name overlap). Output: a results CSV plus an
aggregate summary of how many actually have a website.

Needs GOOGLE_MAPS_API_KEY in .env, "Places API (New)" enabled, billing on.
Free tier: 5000 Text Search calls/month.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv

import places_budget
from run_list import parse as parse_list

load_dotenv()

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.formattedAddress",
])


def _key() -> str:
    k = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not k:
        raise SystemExit("GOOGLE_MAPS_API_KEY not set in .env")
    return k


def _digits(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    return d[-8:] if len(d) >= 8 else d


_STOP = {"aps", "a/s", "i/s", "v", "og", "and", "the", "danmark", "dk", "smba", "s.m.b.a."}


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-zæøå0-9]+", (name or "").lower()) if t not in _STOP and len(t) > 2}


def _search(query: str, key: str) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {"textQuery": query, "languageCode": "da", "regionCode": "DK", "pageSize": 5}
    r = requests.post(SEARCH_URL, json=body, headers=headers, timeout=30)
    if r.status_code == 429:
        raise SystemExit("Places API 429 RESOURCE_EXHAUSTED — fri kvote brugt op for i dag/måned.")
    if r.status_code != 200:
        raise SystemExit(f"Places API {r.status_code}: {r.text[:300]}")
    return r.json().get("places", [])


def _best_match(company: dict, results: list[dict]) -> tuple[dict | None, str]:
    want_phone = _digits(company["telefon"])
    want_tok = _tokens(company["virksomhedsnavn"])
    best, best_score, conf = None, 0.0, "ingen match"
    for pl in results:
        pl_phone = _digits(pl.get("nationalPhoneNumber") or pl.get("internationalPhoneNumber") or "")
        pl_tok = _tokens((pl.get("displayName") or {}).get("text", ""))
        overlap = len(want_tok & pl_tok) / max(1, len(want_tok))
        if want_phone and pl_phone and want_phone == pl_phone:
            return pl, "telefon-match"
        if overlap > best_score:
            best, best_score = pl, overlap
    if best and best_score >= 0.5:
        conf = "navn-match"
    elif best and best_score > 0:
        conf = "svag navn-match"
        best = best if best_score >= 0.34 else None
        if best is None:
            conf = "ingen match"
    else:
        best = None
    return best, conf


FIELDNAMES = ["virksomhedsnavn", "telefon", "match_navn", "match_telefon",
              "match_adresse", "hjemmeside", "sikkerhed"]


def _summarise(out_path: str, total: int) -> dict:
    """Aggregate stats over the whole results file (correct across resume runs)."""
    stats = {"med_website": 0, "uden_website": 0, "ingen_match": 0, "i_alt": total}
    conf_website = {"telefon-match": 0, "navn-match": 0, "svag navn-match": 0}
    n = 0
    try:
        with open(out_path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                n += 1
                if row["sikkerhed"] == "ingen match":
                    stats["ingen_match"] += 1
                elif row["hjemmeside"]:
                    stats["med_website"] += 1
                    if row["sikkerhed"] in conf_website:
                        conf_website[row["sikkerhed"]] += 1
                else:
                    stats["uden_website"] += 1
    except FileNotFoundError:
        pass
    stats["conf_website"] = conf_website
    stats["behandlet"] = n
    stats["out"] = out_path
    return stats


def run(leads: list[dict], out_path: str, max_calls: int,
        monthly_cap: int, resume: bool = True, delay: float = 0.08) -> dict:
    total = len(leads)

    done: set[str] = set()
    if resume and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        with open(out_path, encoding="utf-8", newline="") as f:
            done = {r["virksomhedsnavn"] for r in csv.DictReader(f)}
    todo = [ld for ld in leads if ld["virksomhedsnavn"] not in done]
    if done:
        print(f"Genoptager: {len(done)} allerede slået op, {len(todo)} tilbage.")

    # planned calls this run = min(remaining companies, per-run cap) — checked
    # before touching the key or the network so a refusal is unambiguous.
    planned = min(len(todo), max_calls)
    places_budget.check_budget(planned, monthly_cap)

    key = _key()
    new_file = not (os.path.exists(out_path) and os.path.getsize(out_path) > 0)
    calls_made = 0
    try:
        with open(out_path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if new_file:
                w.writeheader()
            for i, ld in enumerate(todo, 1):
                if calls_made >= max_calls:
                    print(f"\nPer-kørsel loft ({max_calls}) nået. Kør igen for at "
                          f"fortsætte (genoptager automatisk).")
                    break
                try:
                    res = _search(ld["virksomhedsnavn"], key)
                    calls_made += 1
                except SystemExit as e:
                    print(f"\n{e}")
                    print(f"Stoppet efter {calls_made} kald. Delresultat gemt.")
                    break
                match, conf = _best_match(ld, res)
                website = (match or {}).get("websiteUri", "") if match else ""
                w.writerow({
                    "virksomhedsnavn": ld["virksomhedsnavn"], "telefon": ld["telefon"],
                    "match_navn": ((match or {}).get("displayName") or {}).get("text", "") if match else "",
                    "match_telefon": (match or {}).get("nationalPhoneNumber", "") if match else "",
                    "match_adresse": (match or {}).get("formattedAddress", "") if match else "",
                    "hjemmeside": website, "sikkerhed": conf,
                })
                f.flush()
                if i % 50 == 0:
                    left = monthly_cap - places_budget.used_this_month() - calls_made
                    print(f"  {i}/{len(todo)}   kald i alt (denne kørsel): {calls_made}   "
                          f"månedsbudget tilbage: ~{left}")
                time.sleep(delay)
    finally:
        places_budget.record(calls_made)

    print(f"\nKald brugt denne kørsel: {calls_made}   "
          f"(måned {places_budget._month()}: {places_budget.used_this_month()}/{monthly_cap})")
    return _summarise(out_path, total)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--out", default="places_enrich_resultat.csv")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-calls", type=int, default=1500,
                    help="hårdt loft for API-kald i denne ene kørsel")
    ap.add_argument("--monthly-cap", type=int, default=places_budget.MONTHLY_CAP_DEFAULT,
                    help="hårdt loft for API-kald i indeværende måned (på tværs af kørsler)")
    ap.add_argument("--no-resume", action="store_true",
                    help="slå genoptagelse fra (skriver forfra, kan koste kald igen)")
    args = ap.parse_args()

    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    leads = parse_list(text)
    if args.limit:
        leads = leads[:args.limit]
    print(f"{len(leads)} firmaer at slå op i Google Places "
          f"(måned {places_budget._month()}: {places_budget.used_this_month()}/{args.monthly_cap} brugt)\n")

    s = run(leads, args.out, max_calls=args.max_calls,
            monthly_cap=args.monthly_cap, resume=not args.no_resume)
    print("\n=== RESULTAT ===")
    print(f"  Behandlet:        {s['behandlet']} / {s['i_alt']}")
    print(f"  HAR hjemmeside:   {s['med_website']}")
    print(f"    heraf telefon-match: {s['conf_website']['telefon-match']}, "
          f"navn-match: {s['conf_website']['navn-match']}, "
          f"svag: {s['conf_website']['svag navn-match']}")
    print(f"  INGEN hjemmeside: {s['uden_website']}")
    print(f"  Fandt ikke firma: {s['ingen_match']}")
    print(f"  Fuld liste:       {s['out']}")


if __name__ == "__main__":
    main()
