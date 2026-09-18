"""
Database connection/session management.

Production: PostgreSQL (e.g. Supabase), configured via DATABASE_URL in
Streamlit secrets or an environment variable. Local development/testing:
falls back to a file-based SQLite database under data/ when DATABASE_URL
isn't set -- but ONLY when not running in production (APP_ENV=production),
per the Streamlit Cloud + PostgreSQL migration: production must never
silently fall back to local SQLite.

Engine creation is lazy (first call to get_engine()/get_session()/init_db())
so a missing DATABASE_URL in production raises ConfigurationError at a point
the caller (app.py) can catch and show a clean st.error() instead of a raw
traceback on import.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from db.models import Base

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "research_tool.db"


class ConfigurationError(RuntimeError):
    """Required production configuration (e.g. DATABASE_URL) is missing."""


# ---------------------------------------------------------------------------
# Secret / config resolution: Streamlit secrets -> environment variable
# ---------------------------------------------------------------------------


def get_secret(name: str, default: str | None = None) -> str | None:
    """Resolve a config value from Streamlit secrets first, then an
    environment variable, then `default`. Works both inside `streamlit run`
    and in a plain script (e.g. scripts/migrate_sqlite_to_postgres.py) --
    st.secrets just reads .streamlit/secrets.toml directly when there's no
    Streamlit server running, and raises if the file doesn't exist, which we
    treat the same as "not set"."""
    try:
        import streamlit as st

        if name in st.secrets:
            value = st.secrets[name]
            if value:
                return value
    except Exception:
        pass
    return os.getenv(name, default)


def is_production() -> bool:
    """True only when explicitly configured (APP_ENV=production in Streamlit
    Community Cloud secrets). Defaults to development, which is what allows
    the local SQLite fallback below."""
    return (get_secret("APP_ENV", "development") or "development").strip().lower() == "production"


# ---------------------------------------------------------------------------
# SQLite fallback path (local dev/testing only)
# ---------------------------------------------------------------------------


def get_database_path() -> Path:
    override = os.getenv("DATABASE_PATH")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def resolve_database_url() -> str:
    """DATABASE_URL from secrets/env if set; otherwise a local SQLite file --
    but only outside production. In production, a missing DATABASE_URL is a
    configuration error, not a silent SQLite fallback (research data must
    live in PostgreSQL -- Streamlit Cloud's local disk is not persistent)."""
    url = get_secret("DATABASE_URL")
    if url:
        return url

    if is_production():
        raise ConfigurationError(
            "DATABASE_URL is not configured. In production (APP_ENV=production) the app "
            "will not fall back to a local SQLite file, because Streamlit Community Cloud's "
            "local storage is not persistent. Set DATABASE_URL in the app's Streamlit Cloud "
            "Settings -> Secrets to your PostgreSQL/Supabase connection string."
        )

    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


# ---------------------------------------------------------------------------
# Engine (lazy singleton -- built on first use, not at import time, so a
# ConfigurationError surfaces where the caller can show a clean UI error)
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_backend: str | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine(url: str) -> tuple[Engine, str]:
    backend = make_url(url).get_backend_name()  # "sqlite" | "postgresql" | ...

    if backend == "sqlite":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            # NullPool: each Streamlit page rerun opens its own short-lived
            # session, and SQLite gets no real benefit from a bounded
            # connection pool -- see the QueuePool-exhaustion fix this
            # replaced. Not used for PostgreSQL below, which handles a real
            # connection pool well and is what production actually uses.
            poolclass=NullPool,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        engine = create_engine(
            url,
            # Recycles connections that Supabase/the network has silently
            # dropped, rather than handing the caller a dead connection.
            pool_pre_ping=True,
        )

    return engine, backend


def get_engine() -> Engine:
    global _engine, _backend
    if _engine is None:
        url = resolve_database_url()
        _engine, _backend = _build_engine(url)
    return _engine


def get_backend_name() -> str:
    """'sqlite' or 'postgresql' -- never the connection string itself."""
    get_engine()
    assert _backend is not None
    return _backend


def get_database_info() -> dict:
    """Non-secret connection diagnostics for a Settings-page health check.
    Never returns the connection string, host, or password -- only whether a
    trivial query succeeded and the exception *type* (not message) if not,
    since some driver error messages can embed connection details."""
    try:
        engine = get_engine()
    except ConfigurationError as exc:
        return {"connected": False, "backend": None, "error": str(exc)}

    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"connected": True, "backend": _backend, "error": None}
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a health check
        return {
            "connected": False,
            "backend": _backend,
            "error": f"{type(exc).__name__} (see server logs for detail)",
        }


# ---------------------------------------------------------------------------
# Additive-only column migrations for SQLite dev/test databases
# ---------------------------------------------------------------------------
#
# Base.metadata.create_all() only creates *missing tables* -- it never alters
# an existing one -- so a brand new column on an existing model needs an
# explicit, idempotent ALTER TABLE for anyone with an existing local SQLite
# file. This only applies to the SQLite fallback: production PostgreSQL
# schema changes go through Alembic (see alembic/), which is the real
# migration tool -- this is just a small convenience for local dev/test
# databases that predate a given column.
_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "studies": {
        "publication_filter_type": "VARCHAR(20) DEFAULT 'all_time'",
        "published_after": "DATE",
        "published_before": "DATE",
    },
    "pilot_search_runs": {
        "status": "VARCHAR(20) DEFAULT 'completed'",
        "started_at": "DATETIME",
        "completed_at": "DATETIME",
        "error_message": "TEXT",
    },
    "full_search_runs": {
        "status": "VARCHAR(20) DEFAULT 'completed'",
        "started_at": "DATETIME",
        "completed_at": "DATETIME",
        "error_message": "TEXT",
    },
}


def _apply_sqlite_column_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        for table, columns in _COLUMN_MIGRATIONS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue  # table doesn't exist yet -- create_all() will make it with all columns
            for column, ddl in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()


def init_db() -> None:
    """Create all tables if they don't already exist.

    For SQLite (dev/test), also applies the additive column migrations above.
    For PostgreSQL (production), schema changes beyond the very first deploy
    should go through `alembic upgrade head` instead -- see alembic/ and the
    README's deployment section. create_all() remains safe to call here too
    (it only creates missing tables, never alters existing ones), which is
    useful for bootstrapping a brand new, empty Postgres database.
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    if get_backend_name() == "sqlite":
        _apply_sqlite_column_migrations(engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it.
    Never share one Session across requests/users (see handover doc's
    Postgres migration notes, section 7) -- each Streamlit page rerun should
    open its own via this function."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _SessionLocal()
