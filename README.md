# Lead Scraper Tool

Scrapes business leads with **ScrapeGraphAI**, then **checks each website** and
keeps only leads whose site is **bad or missing**, and appends them to a
**Google Sheet**:

| Virksomhedsnavn | Telefon | Kontaktet? | Hjemmeside | Website-score | Årsag |
|---|---|---|---|---|---|

`Kontaktet?` values: `nej` (default), `ring tilbage`, `møde`, `tog ikke tlf`.
`Hjemmeside` is empty when there is no site (or only a Facebook/social page, or a dead domain).
`Website-score` is 0–100 from `website_quality.py` (aggressive ruleset; score ≥ 60 = "god" = lead dropped).
`Årsag` lists why it was flagged, e.g. `ikke mobilvenlig; Flash; ét-sides-side`.

Check a single URL directly:
```bash
.venv/bin/python website_quality.py https://example.com
```

Everything lives in this folder: Python 3.12 in `./.venv`, config in `./.env`.
Nothing is installed system-wide.

## One-time setup

1. `cp .env.example .env` and fill in:
   - `GEMINI_API_KEY` (free tier) — or another LLM provider, see `.env.example`
   - `GOOGLE_SHEET_ID` – the id (or full URL) of a Google Sheet you own
2. Google OAuth (Desktop App):
   - Google Cloud console → enable **Google Sheets API**
   - APIs & Services → Credentials → **Create credentials → OAuth client ID → Desktop app**
   - Download the JSON and save it in the project root as `credentials.json`
3. Smoke-test / sign in (opens a browser once, caches `token.json`):
   ```bash
   .venv/bin/python sheets.py
   ```

## Usage

```bash
.venv/bin/python run.py "https://some-directory-page/with/businesses"
.venv/bin/python run.py --dry-run "https://..."          # preview, no write
.venv/bin/python run.py --keep-all "https://..."         # score sites but keep all
.venv/bin/python run.py "https://..." --prompt "only dentists in Aarhus"
```

Re-running is safe: rows already in the sheet (matched on phone, else name) are skipped.
Every run also writes a per-lead KEEP/drop log to `leads.log`.

## Setup på en ny computer (Windows / Git Bash)

```bash
git clone https://github.com/adviodk/Lead-generator.git
cd Lead-generator

# Python 3.12 + venv (uv henter Python selv)
pip install uv
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install -r requirements.txt          # Windows: tilføj --python .venv/Scripts/python hvis den ikke finder venv
.venv/Scripts/python -m playwright install chromium

cp .env.example .env                        # udfyld nøgler (se nedenfor)
```

Hemmeligheder ligger IKKE i repoet. Kopiér dem manuelt fra den gamle computer:
`.env`, `credentials.json`, `token.json` (placeres i projektets rod).
Mangler `token.json`, åbner første kørsel af `.venv/Scripts/python sheets.py` et browser-login.

Kør scripts med `.venv/Scripts/python <script>.py` (macOS/Linux: `.venv/bin/python`).
