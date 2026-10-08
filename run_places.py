"""Google Places API -> website check -> Google Sheet.

    .venv/bin/python run_places.py --dry-run --trades tømrer --limit 30
    .venv/bin/python run_places.py                       # all trades, Odense, write
    .venv/bin/python run_places.py --city Odense --radius 13000
    .venv/bin/python run_places.py --trades tømrer,elektriker,VVS,maler,murer
"""
from __future__ import annotations

import argparse
import json

from places_pull import ODENSE, TRADES, pull
from run import enrich_and_filter
from sheets import append_leads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="Odense")
    ap.add_argument("--radius", type=float, default=13000, help="location-bias radius in metres")
    ap.add_argument("--trades", default="", help="comma-separated; default = all trades")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-all", action="store_true")
    args = ap.parse_args()

    trades = [t.strip() for t in args.trades.split(",") if t.strip()] or TRADES
    print(f"Places API: {args.city} (r={args.radius:.0f} m), brancher: {', '.join(trades)}\n")
    leads = pull(city_center=ODENSE, radius_m=args.radius, trades=trades,
                 city_name=args.city, limit=args.limit)
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
