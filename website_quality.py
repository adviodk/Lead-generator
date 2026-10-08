"""Classify a business website as god / dårlig / ingen (aggressive ruleset).

Leads worth keeping are the ones with a BAD or NO website, so callers keep
verdict in {"dårlig", "ingen"} and drop {"god"}.

No LLM required — pure heuristics over the fetched HTML.
"""
from __future__ import annotations

import datetime
import re
import socket
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

def _strip_www(h: str) -> str:
    return h[4:] if h.startswith("www.") else h


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 12
GOOD_THRESHOLD = 60  # score >= this => "god" (lead dropped)

SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com",
    "x.com", "tiktok.com", "youtube.com", "pinterest.com", "linktr.ee",
)
FREE_SUBDOMAIN_MARKERS = (
    ".wixsite.com", ".business.site", ".weebly.com", ".blogspot.", ".wordpress.com",
    ".squarespace.com", ".webnode.", ".jimdofree.com", ".simplesite.com",
    ".google.com/site", "sites.google.com",
)
PARKED_MARKERS = (
    "domain is for sale", "buy this domain", "this domain is parked", "domain parking",
    "website coming soon", "coming soon", "under construction", "under konstruktion",
    "siden er under opbygning", "default web page", "apache2 ubuntu default",
    "welcome to nginx", "it works!", "index of /", "domænet er til salg",
    "this page is used to test", "hostingselskab",
)
OLD_TECH = ("frontpage", "dreamweaver mx", "shockwave", "flash player")

# Webmail / ISP portals / free builders listed instead of a real company site
# => the business effectively has NO website.
PORTAL_HOSTS = (
    "sol.dk", "ofir.dk", "events.dk", "sport.dk", "forum.dk", "chicks.dk",
    "adr.dk", "imagica.dk", "m-office.dk", "vestnet.dk", "nyvang.dk", "brygge.dk",
    "aol.dk", "aol.com", "tiscali.dk", "get2net.dk", "webcare.dk", "esenet.dk",
    "brammingnet.dk", "greennet.gl", "star-up.dk", "bakob.dk",
    "inbox.com", "inbox.lv", "wp.pl", "onet.pl", "o2.pl", "interia.pl",
    "hotmail.com", "hotmali.com", "gmail.com", "outlook.com", "live.dk",
    "mail.dk", "mail.tele.dk", "post.tele.dk", "business.tele.dk", "webspeed.dk",
    "stofanet.dk", "privat.dk", "pc.dk", "c.dk", "mail.com", "yahoo.com",
    "bolignet.dk", "mono.net", "123hjemmeside.dk", "simplesite.com",
)


def _empty_website(value: str | None) -> bool:
    v = (value or "").strip().lower()
    return v in {"", "none", "n/a", "na", "null", "-", "ingen", "-", "—"}


def classify(url: str | None) -> dict:
    """Return {verdict, score, reasons, final_url, real_site}."""
    if _empty_website(url):
        return {"verdict": "ingen", "score": 0, "reasons": ["ingen hjemmeside"],
                "final_url": "", "real_site": False}

    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "http://" + u

    host = _strip_www((urlparse(u).hostname or "").lower())
    if any(host == s or host.endswith("." + s) for s in SOCIAL_HOSTS):
        return {"verdict": "ingen", "score": 0,
                "reasons": [f"kun social-side ({host})"], "final_url": u, "real_site": False}
    if any(host == s or host.endswith("." + s) for s in PORTAL_HOSTS):
        return {"verdict": "ingen", "score": 0,
                "reasons": [f"ingen egen hjemmeside (kun {host})"],
                "final_url": u, "real_site": False}

    reasons: list[str] = []
    score = 100
    ssl_bad = False

    # Codes that usually mean "a bot wall / rate-limit got in the way", not a
    # genuinely broken site — retried once, then reported as unverified (kept).
    AMBIGUOUS = {403, 406, 409, 429, 451, 454, 503}
    hdrs = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "da,en;q=0.8",
    }

    def _get(verify=True):
        return requests.get(u, headers=hdrs, timeout=TIMEOUT, allow_redirects=True, verify=verify)

    try:
        r = _get()
        if r.status_code in AMBIGUOUS:
            time.sleep(3)
            r = _get()
        elapsed = r.elapsed.total_seconds()
    except requests.exceptions.SSLError:
        ssl_bad = True
        try:
            r = _get(verify=False)
            elapsed = r.elapsed.total_seconds()
        except Exception as e:  # noqa: BLE001
            return {"verdict": "dårlig", "score": 0,
                    "reasons": [f"kan ikke hentes: {type(e).__name__}"],
                    "final_url": u, "real_site": False}
    except (requests.exceptions.ConnectionError, socket.gaierror):
        return {"verdict": "dårlig", "score": 0, "reasons": ["domæne svarer ikke / DNS-fejl"],
                "final_url": u, "real_site": False}
    except requests.exceptions.Timeout:
        return {"verdict": "dårlig", "score": 0, "reasons": ["timeout ved indlæsning"],
                "final_url": u, "real_site": False}
    except Exception as e:  # noqa: BLE001
        return {"verdict": "dårlig", "score": 0, "reasons": [f"fejl: {type(e).__name__}"],
                "final_url": u, "real_site": False}

    final_url = r.url
    final_host = _strip_www((urlparse(final_url).hostname or "").lower())

    if r.status_code in AMBIGUOUS:
        return {"verdict": "uverificeret", "score": "",
                "reasons": [f"kunne ikke hentes (HTTP {r.status_code}, muligt bot-værn) – tjek manuelt"],
                "final_url": final_url, "real_site": True}
    if r.status_code >= 400:
        return {"verdict": "dårlig", "score": 0,
                "reasons": [f"HTTP {r.status_code}"], "final_url": final_url, "real_site": False}

    # Redirected to a social page => not a real site.
    if any(final_host == s or final_host.endswith("." + s) for s in SOCIAL_HOSTS):
        return {"verdict": "ingen", "score": 0,
                "reasons": [f"omdirigerer til social-side ({final_host})"],
                "final_url": final_url, "real_site": False}

    html = r.text or ""
    low = html.lower()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()

    # Parked / placeholder page.
    if any(m in low for m in PARKED_MARKERS) and len(text) < 1200:
        return {"verdict": "dårlig", "score": 5, "reasons": ["parkeret / placeholder-side"],
                "final_url": final_url, "real_site": False}

    # --- HTTPS / SSL ---
    if ssl_bad:
        score -= 30
        reasons.append("ugyldigt SSL-certifikat")
    elif not final_url.startswith("https://"):
        score -= 25
        reasons.append("ingen HTTPS")

    # --- free builder subdomain ---
    if any(m in final_url.lower() for m in FREE_SUBDOMAIN_MARKERS):
        score -= 20
        reasons.append("gratis builder-underside")

    # --- responsive ---
    if not soup.find("meta", attrs={"name": re.compile("viewport", re.I)}):
        score -= 20
        reasons.append("ikke mobilvenlig (ingen viewport)")

    # --- content volume ---
    if len(text) < 400:
        score -= 25
        reasons.append("næsten intet indhold")
    elif len(text) < 1500:
        score -= 10
        reasons.append("meget lidt indhold")

    # --- old tech ---
    if soup.find(["frameset", "frame"]):
        score -= 30
        reasons.append("frames (forældet)")
    if ".swf" in low or "application/x-shockwave-flash" in low or "<embed" in low:
        score -= 25
        reasons.append("Flash/embed (forældet)")
    if soup.find("font"):
        score -= 15
        reasons.append("<font>-tags (forældet)")
    gen = soup.find("meta", attrs={"name": re.compile("generator", re.I)})
    gen_val = (gen.get("content", "").lower() if gen else "")
    if any(m in gen_val for m in OLD_TECH) or "frontpage" in low:
        score -= 20
        reasons.append("bygget i forældet værktøj")
    tables = soup.find_all("table")
    if len(tables) >= 4 and "display:flex" not in low and "display:grid" not in low:
        score -= 10
        reasons.append("table-baseret layout")

    # --- meta description / favicon ---
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if not md or not md.get("content", "").strip():
        score -= 10
        reasons.append("ingen meta-description")
    if not soup.find("link", rel=lambda v: v and "icon" in " ".join(v).lower()):
        score -= 8
        reasons.append("intet favicon")

    # --- speed ---
    if elapsed > 5:
        score -= 15
        reasons.append(f"meget langsom ({elapsed:.1f}s)")
    elif elapsed > 2.5:
        score -= 8
        reasons.append(f"langsom ({elapsed:.1f}s)")

    # --- contact info on homepage ---
    has_tel = "tel:" in low or bool(re.search(r"\b(?:\+?45[\s.-]?)?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b", text))
    has_mail = "mailto:" in low or bool(re.search(r"[\w.\-]+@[\w.\-]+\.\w{2,}", low))
    if not has_tel and not has_mail and "kontakt" not in low:
        score -= 15
        reasons.append("ingen kontaktinfo på forsiden")

    # --- one-pager ---
    internal = 0
    for a in soup.find_all("a", href=True):
        h = a["href"].strip().lower()
        if h.startswith("#") or h.startswith(("mailto:", "tel:", "javascript:")):
            continue
        ah = _strip_www((urlparse(h).hostname or "").lower())
        if ah in ("", final_host):
            internal += 1
    if internal <= 2:
        score -= 10
        reasons.append("ét-sides-side")

    # --- old copyright year ---
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)[^\d]{0,15}(20\d{2})", low)]
    if years:
        newest = max(years)
        if newest <= datetime.date.today().year - 3:
            score -= 15
            reasons.append(f"copyright {newest} (forældet)")

    score = max(0, min(100, score))
    verdict = "god" if score >= GOOD_THRESHOLD else "dårlig"
    if not reasons:
        reasons.append("ingen problemer fundet")
    return {"verdict": verdict, "score": score, "reasons": reasons,
            "final_url": final_url, "real_site": True}


if __name__ == "__main__":
    import json
    import sys

    requests.packages.urllib3.disable_warnings()  # type: ignore
    for arg in sys.argv[1:]:
        print(json.dumps({arg: classify(arg)}, ensure_ascii=False, indent=2))
