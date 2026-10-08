"""End-to-end: scrape leads, keep only those with a BAD or NO website, append to Sheet.

    .venv/bin/python run.py "https://example.com/directory"
    .venv/bin/python run.py "https://example.com" --prompt "custom instructions"
    .venv/bin/python run.py --dry-run "https://example.com"   # print, don't write
    .venv/bin/python run.py --keep-all "https://example.com"  # skip website filtering
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import requests

from scrape import scrape_leads
from sheets import append_leads
from website_quality import classify

requests.packages.urllib3.disable_warnings()  # type: ignore

LOG_PATH = Path(__file__).parent / "leads.log"
logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)


def enrich_and_filter(leads: list[dict], keep_all: bool) -> list[dict]:
    kept = []
    for ld in leads:
        name = ld.get("virksomhedsnavn") or ld.get("name") or "?"
        website = ld.get("hjemmeside") or ld.get("website") or ""
        res = classify(website)
        verdict, score = res["verdict"], res["score"]
        reason = "; ".join(res["reasons"])

        ld["website_score"] = "" if verdict in ("ingen", "uverificeret") else score
        ld["website_reason"] = ("ingen hjemmeside" if verdict == "ingen" else reason)
        # A social-only / fake site counts as "no website" per the schema.
        if not res["real_site"]:
            ld["hjemmeside"] = ""
            ld["website"] = ""

        keep = keep_all or verdict in ("dårlig", "ingen", "uverificeret")
        mark = "KEEP" if keep else "drop"
        line = f"[{mark}] {name} | {website or '(ingen)'} | {verdict} {score} | {reason}"
        print(line)
        logging.info(line)
        if keep:
            kept.append(ld)
        time.sleep(0.4)  # be polite across large batches
    return kept


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="URL, local HTML file path, or raw HTML")
    ap.add_argument("--prompt", default=None, help="override extraction instructions")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write to Sheets")
    ap.add_argument("--keep-all", action="store_true",
                    help="do not filter out good websites (still scores them)")
    args = ap.parse_args()

    leads = scrape_leads(args.source, args.prompt)
    print(f"Scraped {len(leads)} lead(s). Checking websites...\n")
    kept = enrich_and_filter(leads, args.keep_all)
    print(f"\n{len(kept)} of {len(leads)} lead(s) kept (bad/no website).")

    if args.dry_run:
        print(json.dumps(kept, ensure_ascii=False, indent=2))
        return
    if not kept:
        print("Nothing to write.")
        return

    res = append_leads(kept)
    print(f"Sheet updated: +{res['added']} added, {res['skipped']} skipped (already present).")


if __name__ == "__main__":
    main()
