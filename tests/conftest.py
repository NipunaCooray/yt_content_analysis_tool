"""Shared pytest fixtures. Uses an in-memory SQLite DB per test, never the
real data/research_tool.db file."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from db.models import Base


@pytest.fixture(autouse=True)
def _no_streamlit_secrets(monkeypatch):
    """The whole suite must be hermetic -- no test's outcome should depend on
    whatever a developer happens to have in their local .streamlit/secrets.toml
    (e.g. a real or placeholder DATABASE_URL). get_secret() tries st.secrets
    first, so this makes it behave as if no secrets.toml exists at all,
    isolating every test to the environment-variable/SQLite-fallback path
    unless a test explicitly sets an env var itself."""
    import streamlit as st

    class _NoSecrets:
        def __contains__(self, _key):
            raise FileNotFoundError("no secrets.toml in this test")

    monkeypatch.setattr(st, "secrets", _NoSecrets())


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # Match db/database.py's real SQLite engine: FK constraints (and the
    # ON DELETE CASCADE/SET NULL behavior declared in db/models.py) are only
    # enforced when this pragma is on -- SQLite defaults it off. Without
    # this, tests wouldn't actually exercise the same cascade/set-null
    # behavior the app relies on in production.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
