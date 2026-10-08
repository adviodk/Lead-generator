"""CVR -> website check -> Google Sheet.

    .venv/bin/python run_cvr.py                 # Odense, branche 41-43, write to sheet
    .venv/bin/python run_cvr.py --dry-run
    .venv/bin/python run_cvr.py --limit 50
    .venv/bin/python run_cvr.py --kommune 461 --branche 41,42,43
    .venv/bin/python run_cvr.py --keep-all      # keep good websites too
"""
from __future__ import annotations

import argparse
import json

from cvr_pull import DEFAULT_KOMMUNE_KODE, pull
from run import enrich_and_filter
from sheets import append_leads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kommune", default=DEFAULT_KOMMUNE_KODE, help="kommunekode (461 = Odense)")
    ap.add_argument("--branche", default="41,42,43", help="comma-separated branchekode prefixes")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-all", action="store_true")
    args = ap.parse_args()

    prefixes = [p.strip() for p in args.branche.split(",") if p.strip()]
    leads = pull(branche_prefixes=prefixes, kommune_kode=args.kommune, limit=args.limit)
    print(f"CVR: {len(leads)} virksomheder. Tjekker hjemmesider...\n")

    kept = enrich_and_filter(leads, args.keep_all)
    print(f"\n{len(kept)} af {len(leads)} beholdt (dårlig/ingen hjemmeside).")

    if args.dry_run:
        print(json.dumps(kept, ensure_ascii=False, indent=2))
        return
    if not kept:
        print("Intet at skrive.")
        return

    res = append_leads(kept)
    print(f"Ark opdateret: +{res['added']} tilføjet, {res['skipped']} sprunget over (dublet).")


if __name__ == "__main__":
    main()
