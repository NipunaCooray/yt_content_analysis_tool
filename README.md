# Transport Information Analysis Tool

A research workflow application for a content analysis of YouTube videos about how to use
public transport and alternative transport services in Australia. See
[`youtube_transport_research_tool_handover.md`](youtube_transport_research_tool_handover.md)
for the full product specification.

This is a research data collection, screening, coding, accuracy-assessment, reliability, and
export tool — not a general-purpose YouTube analytics dashboard.

## Status

**All 7 phases from the handover doc implemented** (see section 35 for the phase breakdown),
**plus reviewer-scoped double screening/coding and inter-rater reliability**:

- Study / reviewer / search-query CRUD, SQLite persistence
- Pilot search: relevance rating, per-query performance stats, diagnostics, run history, and
  search-strategy approval
- Full search: raw-result storage (never overwritten across runs), metadata enrichment, and
  deduplication into a master video list
- Publication-date filtering (all time / after / before / between) on both pilot and full
  search, as a filter independent of sort order; saved per run and as part of the approved
  strategy
- Screening: include/exclude/unsure decisions with reasons, notes, and filters
- Video coding: characteristics, information-coverage, older-adult-needs, and presentation
  coding, gated to included videos
- Accuracy assessment: claim-level fact-checking against official sources
- **Reliability**: each reviewer's screening/coding is kept as an independent record (never
  overwritten by a second reviewer), a random double-coding sample selector, blind-until-
  completion comparison, percentage agreement, and Cohen's kappa
- Dashboard: study-wide counters and descriptive charts, including a reliability summary
- Export: the 14 required CSV/JSON datasets plus 3 reliability datasets (every reviewer's raw
  records, and a computed agreement/kappa summary), individually or as one ZIP

73 automated tests pass (mocked YouTube API, in-memory DB — see Tests below).

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

## License

MIT — see [LICENSE](LICENSE).
