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


ONE_PER_VIDEO_CONSTRAINTS = {"uq_screening_study_video", "uq_video_coding_study_video"}


def create_pre_single_record_schema(engine) -> None:
    """The schema as it was before one-record-per-video was enforced, so
    tests can hold the legacy per-reviewer duplicate rows an older database
    may still contain (the current models forbid creating them)."""
    from sqlalchemy import MetaData

    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        copy = table.to_metadata(legacy)
        for constraint in list(copy.constraints):
            if constraint.name in ONE_PER_VIDEO_CONSTRAINTS:
                copy.constraints.discard(constraint)
    legacy.create_all(engine)


@pytest.fixture()
def legacy_db_session():
    """Like db_session, but on the pre-single-record schema."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    create_pre_single_record_schema(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
