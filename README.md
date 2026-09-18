# Transport Information Analysis Tool

A research workflow application for a content analysis of YouTube videos about how to use
public transport and alternative transport services in Australia. See
[`youtube_transport_research_tool_handover.md`](youtube_transport_research_tool_handover.md)
for the full product specification.

This is a research data collection, screening, coding, accuracy-assessment, reliability, and
export tool — not a general-purpose YouTube analytics dashboard.

> **Production research data must not be stored in a local SQLite database on Streamlit
> Community Cloud.** Streamlit Cloud's local disk is not persistent — it can be wiped on
> restart/redeploy. The production app must be configured with `DATABASE_URL` pointing at a
> real PostgreSQL database (e.g. Supabase); see [Production deployment](#production-deployment)
> below. SQLite remains supported for local development and automated tests only.

## Status

**All 7 phases from the handover doc implemented** (see section 35 for the phase breakdown),
**plus reviewer-scoped double screening/coding, inter-rater reliability, and a
PostgreSQL-backed production deployment path**:

- Study / reviewer / search-query CRUD
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
- **PostgreSQL in production, SQLite for local dev/tests**: pilot/full search runs are durable
  (a row exists as soon as a run starts, results save incrementally per query, and the run's
  status reflects partial/failed progress rather than losing work on a crash), Alembic manages
  schema changes, and secrets are never committed to Git

120 automated tests pass (mocked YouTube API, in-memory/temp-file SQLite — see
[Tests](#tests) below). 4 additional PostgreSQL integration tests are skipped unless a real
server is available (see [Tests](#tests)).

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set YOUTUBE_API_KEY=<your key>

streamlit run app.py
```

By default (no `DATABASE_URL` configured), the app uses a local SQLite file at
`data/research_tool.db`, created automatically on first run — nothing else to configure. This
is the easiest way to work on the app itself; switch to PostgreSQL locally only if you
specifically want to test against it (see below).

Get a YouTube Data API v3 key from the
[Google Cloud Console](https://console.cloud.google.com/apis/credentials) (enable "YouTube Data
API v3" for your project first).

### Secrets: how configuration is resolved

Both `YOUTUBE_API_KEY` and `DATABASE_URL` are resolved in this order:

1. Streamlit secrets (`.streamlit/secrets.toml` locally, or the Community Cloud Secrets panel
   in production)
2. Environment variable (`.env` locally is loaded automatically)
3. For `DATABASE_URL` only: a local SQLite fallback — **but only when `APP_ENV` is not
   `production`**. In production, a missing `DATABASE_URL` shows a configuration error and
   stops the app rather than silently using SQLite.

Never commit real secrets. `.env`, `.streamlit/secrets.toml`, and `*.db`/`*.sqlite*` files are
all git-ignored. Only `.env.example` and `.streamlit/secrets.toml.example` (placeholders) are
committed.

### Running locally against PostgreSQL (optional)

Useful for testing the production database path before deploying, or if you're migrating
existing SQLite data.

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml: set DATABASE_URL to your PostgreSQL/Supabase connection string
# (leave APP_ENV unset/"development" so a missing DATABASE_URL would still fall back to SQLite,
# not error out, if you ever remove it again)

alembic upgrade head    # creates the schema in that PostgreSQL database
streamlit run app.py
```

## Database migrations (Alembic)

Schema changes for PostgreSQL go through [Alembic](https://alembic.sqlalchemy.org/), not
`Base.metadata.create_all()` (which only creates missing tables and is used as a local
dev/test convenience and a first-deploy bootstrap — it never alters an existing table).

```bash
# Apply all pending migrations to whatever database DATABASE_URL currently resolves to:
alembic upgrade head

# After changing a model in db/models.py, generate a new migration:
alembic revision --autogenerate -m "describe the change"
# review the generated file in alembic/versions/ before committing it, then:
alembic upgrade head

# Roll back one migration:
alembic downgrade -1
```

`alembic/env.py` resolves the database URL the same way the app does (Streamlit secrets ->
`DATABASE_URL` env var -> local SQLite), so `alembic.ini` never needs real credentials in it.

### Migrating existing SQLite data to PostgreSQL

If you already collected data in the local SQLite database before setting up PostgreSQL:

```bash
# Always dry-run first -- reports row counts, writes nothing:
python scripts/migrate_sqlite_to_postgres.py --dry-run

# Then actually migrate (uses DATABASE_URL for the target by default):
python scripts/migrate_sqlite_to_postgres.py
```

The script preserves primary keys, timestamps, and foreign-key relationships, and is
idempotent (safe to re-run — already-migrated rows are skipped, not duplicated). Compare the
before/after row counts it prints, then manually spot-check a few representative relationships
(a study → its videos → screening decisions → coding records). Keep the SQLite file as an
archival backup until you're confident in the result.

If your existing SQLite data is only disposable development data, skip this — just run
`alembic upgrade head` against the new PostgreSQL database and start collecting real data
there directly.

## Production deployment

**Architecture:** Streamlit Community Cloud hosts the application UI; PostgreSQL (e.g.
Supabase) is the persistent source of truth for all research data. The app never falls back to
local SQLite in production — see the warning at the top of this README.

### Deployment sequence

1. Create a PostgreSQL database (e.g. a new [Supabase](https://supabase.com) project) and get
   its connection string. Prefer the provider's pooled connection endpoint for the deployed app.
2. Apply the schema: `DATABASE_URL="<your connection string>" alembic upgrade head`
3. Test locally against that database (see [above](#running-locally-against-postgresql-optional))
4. Push this code to GitHub (no secrets in the repo — see below)
5. Create a new app on [Streamlit Community Cloud](https://share.streamlit.io), pointing at
   this repository and `app.py` as the entrypoint
6. In the app's **Settings → Secrets**, configure:

   ```toml
   DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:PORT/postgres"
   YOUTUBE_API_KEY = "your production key"
   APP_ENV = "production"
   ```

7. Deploy
8. In **Settings → Sharing**, restrict the app to specific people/emails (see
   [Private access](#private-access) below) — do not leave it public
9. Run the [production smoke tests](#production-smoke-tests) below
10. Start the study

### Private access

Configure the deployed app as private/restricted in Streamlit Community Cloud's app **Settings
→ Sharing**, limited to the researchers on the study. This tool does not implement its own
authentication — access control is Streamlit Cloud's viewer-list feature. Do not deploy this
publicly with real study data.

### Production smoke tests

Before starting the real study, verify the deployed app end-to-end:

- **Persistence** — create a test study, refresh the page, confirm it remains; if practical,
  reboot the app from Streamlit Cloud's manage panel and confirm it's still there
- **Reviewer** — create a reviewer, refresh, confirm it persists
- **Pilot search** — run one small pilot query, rate one result, refresh, confirm the rating
  persists
- **Search approval** — approve a test strategy, confirm the publication-date filter and search
  order persist
- **Screening** — include/exclude a test video, refresh, confirm the decision persists
- **Coding** — code a test video, refresh, confirm the values persist
- **Accuracy** — add a test accuracy claim, refresh, confirm it persists
- **Export** — export test data, verify IDs and values look right
- **Database diagnostics** — check the Settings page shows "Connected (postgresql)"

Then a **multi-user smoke test**, which must pass before formal double coding begins:

1. Open two independent browser sessions (or two people, two machines)
2. Select different reviewer profiles in each
3. Open the same study in both
4. Code different videos simultaneously — confirm neither overwrites the other
5. Double-code one video under both reviewers — confirm both coding records remain available
   independently (check the Reliability page)

Delete any test studies/reviewers/data created during these checks before real data collection
begins.

## Tests

```bash
pytest
```

Tests mock the YouTube API and use SQLite (in-memory or a temp file) — no live API key,
network access, or PostgreSQL server is required for the main suite.

A small number of PostgreSQL integration tests in `tests/test_postgres_integration.py` are
skipped by default (no server available) and only run when `POSTGRES_TEST_URL` is set to a
reachable connection string:

```bash
# e.g. a throwaway local Postgres via Docker:
docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
POSTGRES_TEST_URL="postgresql+psycopg://postgres:postgres@localhost:5432/postgres" pytest tests/test_postgres_integration.py -v
```

## Project structure

```text
app.py                 # entry point / page router; shows a config error and stops if
                        # DATABASE_URL is missing in production rather than falling back
alembic/                # PostgreSQL schema migrations (source of truth for prod schema)
alembic.ini
pages/                  # one file per sidebar page
db/                     # SQLAlchemy models, session/engine management (SQLite + PostgreSQL), CRUD
services/               # business logic (YouTube API client, pilot/full search, reliability, ...)
components/             # shared Streamlit UI pieces (sidebar, video embed, forms)
utils/                  # constants (coding domains/vocabularies), validators, helpers
scripts/                # one-off ops scripts (SQLite -> PostgreSQL data migration)
tests/                  # pytest suite (mocked YouTube API, SQLite; PostgreSQL tests opt-in)
data/                   # local SQLite database file (git-ignored) -- dev/test only
```

Coding-domain vocabularies (transport modes, information-coverage domains, older-adult needs,
accuracy categories, etc.) live centrally in `utils/constants.py` so the research team can amend
the coding framework without touching UI code.

## License

MIT — see [LICENSE](LICENSE).
