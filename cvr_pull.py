"""Pull companies from the official CVR distribution API (distribution.virk.dk).

Requires system-to-system credentials from Erhvervsstyrelsen (free — see
EMAIL_TIL_ERST.md). Put them in .env as CVR_USERNAME / CVR_PASSWORD.

Default filter: construction / trades (branchekode 41–43) in Odense Kommune,
active companies only, advertising-protected units excluded.
"""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

ES_URL = "http://distribution.virk.dk/cvr-permanent/virksomhed/_search"
SCROLL_URL = "http://distribution.virk.dk/_search/scroll"

# DB07 main sections for "håndværkere / bygge og anlæg".
DEFAULT_BRANCHE_PREFIXES = ["41", "42", "43"]
# Odense Kommune.
DEFAULT_KOMMUNE_KODE = "461"


def _auth() -> tuple[str, str]:
    u = os.environ.get("CVR_USERNAME")
    p = os.environ.get("CVR_PASSWORD")
    if not u or not p:
        raise SystemExit("CVR_USERNAME / CVR_PASSWORD not set in .env (see EMAIL_TIL_ERST.md)")
    return u, p


def _query(branche_prefixes: list[str], kommune_kode: str) -> dict:
    md = "Vrvirksomhed.virksomhedMetadata"
    return {
        "size": 1000,
        "_source": [
            f"{md}.nyesteNavn.navn",
            f"{md}.nyesteHovedbranche",
            f"{md}.nyesteBeliggenhedsadresse",
            f"{md}.sammensatStatus",
            "Vrvirksomhed.cvrNummer",
            "Vrvirksomhed.reklamebeskyttet",
            "Vrvirksomhed.telefonNummer",
            "Vrvirksomhed.hjemmeside",
            "Vrvirksomhed.elektroniskPost",
        ],
        "query": {
            "bool": {
                "must": [
                    {"term": {f"{md}.nyesteBeliggenhedsadresse.kommune.kommuneKode": kommune_kode}},
                    {"term": {f"{md}.sammensatStatus": "AKTIV"}},
                ],
                "should": [
                    {"prefix": {f"{md}.nyesteHovedbranche.branchekode": p}}
                    for p in branche_prefixes
                ],
                "minimum_should_match": 1,
                "must_not": [{"term": {"Vrvirksomhed.reklamebeskyttet": True}}],
            }
        },
    }


def _first_public(items) -> str:
    for it in items or []:
        if isinstance(it, dict) and not it.get("hemmelig"):
            v = (it.get("kontaktoplysning") or "").strip()
            if v:
                return v
    return ""


def _to_lead(hit: dict) -> dict:
    v = hit.get("_source", {}).get("Vrvirksomhed", {})
    md = v.get("virksomhedMetadata", {})
    adr = md.get("nyesteBeliggenhedsadresse") or {}
    komm = " ".join(str(x) for x in [
        adr.get("vejnavn"), adr.get("husnummerFra"), adr.get("postnummer"), adr.get("postdistrikt"),
    ] if x)
    return {
        "virksomhedsnavn": (md.get("nyesteNavn") or {}).get("navn", ""),
        "telefon": _first_public(v.get("telefonNummer")),
        "hjemmeside": _first_public(v.get("hjemmeside")),
        "email": _first_public(v.get("elektroniskPost")),
        "cvr": v.get("cvrNummer"),
        "branchekode": (md.get("nyesteHovedbranche") or {}).get("branchekode", ""),
        "branche": (md.get("nyesteHovedbranche") or {}).get("branchetekst", ""),
        "adresse": komm,
    }


def pull(branche_prefixes: list[str] | None = None,
         kommune_kode: str = DEFAULT_KOMMUNE_KODE,
         limit: int | None = None) -> list[dict]:
    prefixes = branche_prefixes or DEFAULT_BRANCHE_PREFIXES
    auth = _auth()
    body = _query(prefixes, kommune_kode)

    r = requests.post(ES_URL + "?scroll=2m", json=body, auth=auth, timeout=60)
    r.raise_for_status()
    data = r.json()
    scroll_id = data.get("_scroll_id")
    hits = data.get("hits", {}).get("hits", [])
    leads = [_to_lead(h) for h in hits]

    while hits and (limit is None or len(leads) < limit):
        r = requests.post(SCROLL_URL, json={"scroll": "2m", "scroll_id": scroll_id},
                          auth=auth, timeout=60)
        r.raise_for_status()
        data = r.json()
        scroll_id = data.get("_scroll_id")
        hits = data.get("hits", {}).get("hits", [])
        leads.extend(_to_lead(h) for h in hits)

    # de-dupe on CVR
    seen, out = set(), []
    for ld in leads:
        if ld["cvr"] in seen:
            continue
        seen.add(ld["cvr"])
        out.append(ld)
    return out[:limit] if limit else out


if __name__ == "__main__":
    import json
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = pull(limit=n)
    print(f"{len(rows)} virksomheder")
    print(json.dumps(rows[:20], ensure_ascii=False, indent=2))
