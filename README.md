# YouTube Transport Research Tool

A research workflow application for a content analysis of YouTube videos about how to use
public transport and alternative transport services in Australia. See
[`youtube_transport_research_tool_handover.md`](youtube_transport_research_tool_handover.md)
for the full product specification.

This is a research data collection, screening, coding, accuracy-assessment, and export tool —
not a general-purpose YouTube analytics dashboard.

## Status

**Phases 1–2 implemented:**

- Study / reviewer / search-query CRUD, SQLite persistence
- YouTube API pilot search, relevance rating, per-query performance stats, diagnostics
- Pilot-run history (never overwritten) and search-strategy approval

Full search, screening, coding, accuracy assessment, dashboard, and export are scaffolded as
placeholder pages/services and arrive in later phases (see the handover doc, section 35).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set YOUTUBE_API_KEY=<your key>
```

Get a YouTube Data API v3 key from the
[Google Cloud Console](https://console.cloud.google.com/apis/credentials) (enable "YouTube Data
API v3" for your project first). The key lives only in your local `.env` file, which is
git-ignored — it's never committed or shown in the UI.

## Run

```bash
streamlit run app.py
```

The SQLite database is created automatically at `data/research_tool.db` on first run.

## Tests

```bash
pytest
```

Tests mock the YouTube API and use an in-memory SQLite database — no live API key or network
access is required to run them.

## Project structure

```text
app.py                 # entry point / page router
pages/                  # one file per sidebar page
db/                     # SQLAlchemy models, session management, CRUD
services/               # business logic (YouTube API client, pilot search, ...)
components/             # shared Streamlit UI pieces (sidebar, video embed, forms)
utils/                  # constants (coding domains/vocabularies), validators, helpers
tests/                  # pytest suite (mocked YouTube API, in-memory DB)
data/                   # local SQLite database file (git-ignored)
```

Coding-domain vocabularies (transport modes, information-coverage domains, older-adult needs,
accuracy categories, etc.) live centrally in `utils/constants.py` so the research team can amend
the coding framework without touching UI code.
