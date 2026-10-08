"""Google Sheets writer for scraped leads.

Fixed column schema (Danish):
    Virksomhedsnavn | Telefon | Kontaktet? | Hjemmeside | Website-score | Årsag

Auth: Google OAuth (Desktop App). Put the downloaded OAuth client file in the
project root as `credentials.json`. On first run a browser opens to sign in and
grant access; the resulting token is cached in `token.json` and refreshed
automatically afterwards. Both files are git-ignored.
"""
from __future__ import annotations

import os
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

HEADER = ["Virksomhedsnavn", "Telefon", "Kontaktet?", "Hjemmeside", "Website-score", "Årsag"]
CONTACT_DEFAULT = "nej"
CONTACT_ALLOWED = {"nej", "ring tilbage", "møde", "tog ikke tlf"}

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_ROOT = Path(__file__).parent
_CREDENTIALS_FILE = _ROOT / os.environ.get("GOOGLE_OAUTH_CREDENTIALS", "credentials.json")
_TOKEN_FILE = _ROOT / os.environ.get("GOOGLE_OAUTH_TOKEN", "token.json")


def _norm_phone(p: str) -> str:
    return "".join(ch for ch in str(p or "") if ch.isdigit())


def get_credentials() -> Credentials:
    """Load cached OAuth creds, refreshing or running the sign-in flow as needed."""
    creds: Credentials | None = None
    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDENTIALS_FILE.exists():
                raise SystemExit(f"OAuth client file not found: {_CREDENTIALS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_FILE), _SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        _TOKEN_FILE.write_text(creds.to_json())
    return creds


def get_worksheet(tab: str | None = None):
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        raise SystemExit("GOOGLE_SHEET_ID is not set in .env")
    if "/spreadsheets/d/" in sheet_id:  # accept a full URL too
        sheet_id = sheet_id.split("/spreadsheets/d/")[1].split("/")[0]

    gc = gspread.authorize(get_credentials())
    sh = gc.open_by_key(sheet_id)

    tab = tab or os.environ.get("GOOGLE_WORKSHEET", "Leads")
    try:
        ws = sh.worksheet(tab)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab, rows=1000, cols=len(HEADER))

    if ws.row_values(1) != HEADER:
        ws.update([HEADER], "A1")
    return ws


def append_leads(leads: list[dict], tab: str | None = None) -> dict:
    """Append leads, skipping ones already present (matched on phone, else name).

    Each lead dict may use keys: virksomhedsnavn/name, telefon/phone,
    hjemmeside/website, kontaktet. `tab` targets a specific worksheet/tab
    (created if missing); default is GOOGLE_WORKSHEET or "Leads".
    Returns {"added": int, "skipped": int}.
    """
    ws = get_worksheet(tab)
    existing = ws.get_all_values()[1:]  # drop header
    seen_phones = {_norm_phone(r[1]) for r in existing if len(r) > 1 and _norm_phone(r[1])}
    seen_names = {r[0].strip().lower() for r in existing if r and r[0].strip()}

    rows, skipped = [], 0
    for ld in leads:
        name = str(ld.get("virksomhedsnavn") or ld.get("name") or "").strip()
        phone = str(ld.get("telefon") or ld.get("phone") or "").strip()
        website = str(ld.get("hjemmeside") or ld.get("website") or "").strip()
        if website.lower() in {"none", "n/a", "null", "-"}:
            website = ""
        contacted = str(ld.get("kontaktet") or CONTACT_DEFAULT).strip().lower()
        if contacted not in CONTACT_ALLOWED:
            contacted = CONTACT_DEFAULT
        score = ld.get("website_score", "")
        reason = str(ld.get("website_reason") or "").strip()

        if not name and not phone:
            continue
        np = _norm_phone(phone)
        if (np and np in seen_phones) or (not np and name.lower() in seen_names):
            skipped += 1
            continue
        if np:
            seen_phones.add(np)
        seen_names.add(name.lower())
        rows.append([name, phone, contacted, website, score, reason])

    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    return {"added": len(rows), "skipped": skipped}


if __name__ == "__main__":
    # Smoke test: run the OAuth flow (first time) and verify sheet access + header.
    ws = get_worksheet()
    print(f"Connected to '{ws.spreadsheet.title}' / tab '{ws.title}'. Rows: {ws.row_count}")
    print(f"Header: {ws.row_values(1)}")
    print(f"Token cached at: {_TOKEN_FILE}")
