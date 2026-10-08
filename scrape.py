"""Scrape business leads from a web page with ScrapeGraphAI + Claude."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from scrapegraphai.graphs import SmartScraperGraph

load_dotenv()

_PROMPT = (
    "Extract every business/company listed on this page as lead entries. "
    "For each one return: virksomhedsnavn (company name), telefon (phone number, "
    "keep the local format), hjemmeside (the company's own website URL, or an empty "
    "string if none is shown). Do not invent data. Return a JSON list under the key "
    "'leads'."
)


def _config() -> dict:
    """Pick the LLM provider from .env.

    Set LLM_PROVIDER=gemini|ollama|openai|anthropic to force one; otherwise it is
    inferred from whichever key is present (gemini > openai > anthropic > ollama).
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not provider:
        if gemini_key:
            provider = "gemini"
        elif openai_key:
            provider = "openai"
        elif anthropic_key:
            provider = "anthropic"
        elif os.environ.get("OLLAMA_MODEL"):
            provider = "ollama"

    if provider == "gemini":
        if not gemini_key:
            raise SystemExit("GEMINI_API_KEY is not set in .env")
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        llm = {"api_key": gemini_key, "model": f"google_genai/{model}"}
    elif provider == "ollama":
        model = os.environ.get("OLLAMA_MODEL", "llama3.1")
        llm = {
            "model": f"ollama/{model}",
            "model_tokens": int(os.environ.get("OLLAMA_MODEL_TOKENS", "8192")),
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        }
    elif provider == "openai":
        if not openai_key:
            raise SystemExit("OPENAI_API_KEY is not set in .env")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        llm = {"api_key": openai_key, "model": f"openai/{model}"}
    elif provider == "anthropic":
        if not anthropic_key:
            raise SystemExit("ANTHROPIC_API_KEY is not set in .env")
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        llm = {"api_key": anthropic_key, "model": f"anthropic/{model}"}
    else:
        raise SystemExit(
            "No LLM configured. Set GEMINI_API_KEY (or OLLAMA_MODEL / OPENAI_API_KEY / "
            "ANTHROPIC_API_KEY) in .env"
        )

    return {"llm": llm, "verbose": False, "headless": True}


def scrape_leads(source: str, prompt: str | None = None) -> list[dict]:
    """`source` is a URL or a local file path/raw HTML string."""
    graph = SmartScraperGraph(prompt=prompt or _PROMPT, source=source, config=_config())
    result = graph.run()
    if isinstance(result, dict):
        leads = result.get("leads") or result.get("content") or []
    elif isinstance(result, list):
        leads = result
    else:
        leads = []
    return [ld for ld in leads if isinstance(ld, dict)]


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("usage: python scrape.py <url> [prompt]")
    out = scrape_leads(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(out, ensure_ascii=False, indent=2))
