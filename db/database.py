"""
Database connection/session management.

Uses a file-based SQLite database under data/ so results persist between
Streamlit reruns and sessions (handover doc section 33). The path can be
overridden with the DATABASE_PATH env var for tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from db.models import Base

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "research_tool.db"


def get_database_path() -> Path:
    override = os.getenv("DATABASE_PATH")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def get_engine_url() -> str:
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


_engine = create_engine(
    get_engine_url(),
    connect_args={"check_same_thread": False},
    # NullPool instead of the default QueuePool: each Streamlit page rerun opens
    # its own short-lived session, and Streamlit's frequent reruns (plus
    # st.stop() calls that can skip an explicit db.close()) make it easy to
    # exceed a fixed-size pool -- which then blocks every user with a
    # QueuePool timeout. NullPool opens/closes a real SQLite connection per
    # checkout instead of queuing a bounded set, so there's no shared limit to
    # exhaust. SQLite doesn't benefit from pooling the way a network database
    # does, so this has no real downside here.
    poolclass=NullPool,
)


@event.listens_for(_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    # Enforce FK constraints (SQLite has them off by default).
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


# Lightweight, additive-only migrations for columns added to an existing
# table after it may already have been created on someone's machine.
# Base.metadata.create_all() only creates *missing tables* -- it never alters
# an existing one -- so a brand new column on an existing model needs an
# explicit, idempotent ALTER TABLE here. Keyed by table name; each value is
# {column_name: column_ddl_fragment}. Safe to re-run on every startup.
_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "studies": {
        "publication_filter_type": "VARCHAR(20) DEFAULT 'all_time'",
        "published_after": "DATE",
        "published_before": "DATE",
    },
}


def _apply_column_migrations() -> None:
    with _engine.connect() as conn:
        for table, columns in _COLUMN_MIGRATIONS.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not existing:
                continue  # table doesn't exist yet -- create_all() will make it with all columns
            for column, ddl in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()


def init_db() -> None:
    """Create all tables if they don't already exist, and apply any pending
    additive column migrations to tables that already existed."""
    Base.metadata.create_all(_engine)
    _apply_column_migrations()


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    return SessionLocal()


def get_engine():
    return _engine
