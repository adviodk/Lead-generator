"""Temporary lead source: scrape company name + phone + website from proff.dk.

proff.dk is CVR-backed, not behind a bot wall, and its company pages link out to
the firm's real website — enough to feed the website-quality filter. Use this
until the official CVR credentials arrive (then switch to run_cvr.py).
"""
from __future__ import annotations

import re
import time
from collections import Counter
from urllib.parse import quote, urlparse

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Danish trade keywords — "håndværkere, alle brancher".
TRADES = [
    "tømrer", "snedker", "elektriker", "VVS", "blikkenslager", "maler",
    "murer", "tagdækker", "glarmester", "gulvlægger", "kloakmester",
    "brolægger", "stukkatør", "isolering", "smed", "anlægsgartner",
    "entreprenør", "byggefirma",
]

_LINK_DENY = (
    "proff.", "forvalt.", "static.proff", "datacvr.virk.dk", "virk.dk",
    "openstreetmap.org", "anmeld-haandvaerker.dk", "trustpilot.", "enento",
    "brreg.no", "allabolag.", "ratsit.", "birn.", "1881.no", "gulesider.no",
    "facebook.com", "linkedin.com", "instagram.com", "youtube.com", "google.",
    "apple.com", "microsoft.com", "cvr.dk", "krak.dk", "degulesider.dk",
    "wikipedia.org",
)
_PHONE_RE = re.compile(r"Telefon\s*((?:\+45[\s ]?)?\d{2}[\s ]?\d{2}[\s ]?\d{2}[\s ]?\d{2})")


def _company_id(href: str) -> str:
    return href.rstrip("/").rsplit("/", 1)[-1]


def _pick_website(links: list[str]) -> str:
    total = Counter()
    deep = Counter()  # linked with a real path (e.g. /kontakt) => likely the firm's own site
    for h in links:
        pr = urlparse(h)
        host = (pr.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or "." not in host or any(d in host for d in _LINK_DENY):
            continue
        total[host] += 1
        if pr.path.strip("/"):
            deep[host] += 1
    # A firm's own site is linked with a real path (…/kontakt); the Nordic
    # sister-site noise (uc.se, forvalt.no, proff.fi, …) is only ever root links.
    candidates = [d for d in total if deep[d] > 0]
    if not candidates:
        return ""
    candidates.sort(key=lambda d: (deep[d], total[d]), reverse=True)
    return "https://" + candidates[0]


def _extract(pg) -> dict:
    body = pg.inner_text("body")
    name = ""
    h1 = pg.query_selector("h1")
    if h1:
        name = re.split(r"\s*[|,]\s*", h1.inner_text().strip())[0]
    phone = ""
    m = _PHONE_RE.search(body)
    if m:
        phone = re.sub(r"\s+", " ", m.group(1)).strip()
    cvr = ""
    mc = re.search(r"CVR-nr\.?\s*(\d{8})", body)
    if mc:
        cvr = mc.group(1)
    ext = pg.eval_on_selector_all(
        'a[href^="http"]', "els => els.map(e => e.href)"
    )
    website = _pick_website(ext)
    return {"virksomhedsnavn": name, "telefon": phone, "hjemmeside": website, "cvr": cvr}


def pull(city: str = "Odense", trades: list[str] | None = None,
         max_pages: int = 8, limit: int | None = None,
         delay: float = 1.0) -> list[dict]:
    trades = trades or TRADES
    out: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(user_agent=UA)

        for trade in trades:
            hrefs: list[str] = []
            seen_page = set()
            for page_no in range(1, max_pages + 1):
                url = (f"https://www.proff.dk/branches%C3%B8g?"
                       f"q={quote(trade + ' ' + city)}&page={page_no}")
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                    pg.wait_for_timeout(1800)
                except Exception:
                    break
                found = pg.eval_on_selector_all(
                    'a[href*="/firma/"]',
                    "els => [...new Set(els.map(e => e.getAttribute('href')))]",
                )
                new = [h for h in found if h not in seen_page]
                if not new:
                    break
                seen_page.update(new)
                hrefs.extend(new)
                time.sleep(delay)

            print(f"  {trade}: {len(hrefs)} virksomheder fundet")
            for href in hrefs:
                cid = _company_id(href)
                if cid in out:
                    continue
                full = "https://www.proff.dk" + href if href.startswith("/") else href
                try:
                    pg.goto(full, wait_until="domcontentloaded", timeout=30000)
                    pg.wait_for_timeout(1500)
                    rec = _extract(pg)
                except Exception:
                    continue
                rec["branche"] = trade
                rec["kilde"] = full
                key = rec["cvr"] or cid
                if rec["virksomhedsnavn"] and key not in out:
                    out[key] = rec
                time.sleep(delay)
                if limit and len(out) >= limit:
                    browser.close()
                    return list(out.values())

        browser.close()
    return list(out.values())


if __name__ == "__main__":
    import json
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    rows = pull(trades=["tømrer"], limit=n)
    print(f"\n{len(rows)} virksomheder")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
