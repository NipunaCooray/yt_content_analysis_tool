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


def init_db() -> None:
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    return SessionLocal()


def get_engine():
    return _engine
