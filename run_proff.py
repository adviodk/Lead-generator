"""proff.dk -> website check -> Google Sheet.  Temporary source until CVR access.

    .venv/bin/python run_proff.py --dry-run --limit 20
    .venv/bin/python run_proff.py                       # all trades, Odense, write
    .venv/bin/python run_proff.py --trades tømrer,maler --limit 50
    .venv/bin/python run_proff.py --city Odense --max-pages 12
"""
from __future__ import annotations

import argparse
import json

from proff_pull import TRADES, pull
from run import enrich_and_filter
from sheets import append_leads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="Odense")
    ap.add_argument("--trades", default="", help="comma-separated; default = all trades")
    ap.add_argument("--max-pages", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-all", action="store_true")
    args = ap.parse_args()

    trades = [t.strip() for t in args.trades.split(",") if t.strip()] or TRADES
    print(f"proff.dk: {args.city}, brancher: {', '.join(trades)}\n")
    leads = pull(city=args.city, trades=trades, max_pages=args.max_pages, limit=args.limit)
    print(f"\n{len(leads)} virksomheder hentet. Tjekker hjemmesider...\n")

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
