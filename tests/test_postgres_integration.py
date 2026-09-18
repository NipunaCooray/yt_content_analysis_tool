"""Real PostgreSQL integration test (Streamlit Cloud + PostgreSQL migration,
section 37: "add at least one PostgreSQL integration-test path if
practical"). Everything else in this suite runs against SQLite, which is
enough to verify application logic, but this test actually exercises the
psycopg driver and PostgreSQL-specific DDL/DML against a real server.

Skipped by default -- no CI/dev machine here has a Postgres server. To run
it for real:

    docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
    POSTGRES_TEST_URL="postgresql+psycopg://postgres:postgres@localhost:5432/postgres" \\
        pytest tests/test_postgres_integration.py -v

Or point it at a real Supabase project's connection string before starting
the actual study, as a one-time pre-flight check.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db import crud
from db.models import Base

POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="Set POSTGRES_TEST_URL to a reachable PostgreSQL connection string to run this test.",
)


@pytest.fixture()
def postgres_session():
    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"POSTGRES_TEST_URL is set but not reachable: {exc}")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        # Leave the test database clean for the next run.
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_create_study_and_read_it_back_from_postgres(postgres_session):
    study = crud.create_study(postgres_session, name="Postgres integration test study")
    assert study.id is not None

    fetched = crud.get_study(postgres_session, study.id)
    assert fetched.name == "Postgres integration test study"
    assert fetched.publication_filter_type == "all_time"  # server-applied default


def test_json_column_round_trips_through_postgres(postgres_session):
    """SQLAlchemy's generic JSON type maps to PostgreSQL's native json --
    verify a dict with nested structure survives a real round trip (not just
    SQLite's TEXT-backed JSON)."""
    study = crud.create_study(postgres_session, name="JSON test study")
    reviewer = crud.create_reviewer(postgres_session, name="R1", initials="R1")
    query = crud.create_search_query(postgres_session, study_id=study.id, query_text="q")

    run = crud.create_pilot_search_run(
        postgres_session, study_id=study.id, reviewer_id=reviewer.id,
        parameters_json={"query_ids": [query.id], "nested": {"a": [1, 2, 3]}},
    )

    fetched = crud.get_pilot_search_run(postgres_session, run.id)
    assert fetched.parameters_json == {"query_ids": [query.id], "nested": {"a": [1, 2, 3]}}


def test_foreign_key_and_unique_constraints_enforced_by_postgres(postgres_session):
    study = crud.create_study(postgres_session, name="Constraint test study")
    video = crud.create_video(postgres_session, study_id=study.id, video_id="dup", title="A video")
    postgres_session.commit()

    # (study_id, video_id) unique constraint -- a second video with the same
    # pair should fail exactly as it does on SQLite.
    from sqlalchemy.exc import IntegrityError

    crud.create_video(postgres_session, study_id=study.id, video_id="dup", title="Duplicate")
    with pytest.raises(IntegrityError):
        postgres_session.commit()
    postgres_session.rollback()


def test_reviewer_scoped_double_coding_on_postgres(postgres_session):
    """The core multi-user correctness property from Phase 8: two reviewers'
    screening decisions on the same video must both survive independently."""
    study = crud.create_study(postgres_session, name="Double coding test study")
    r1 = crud.create_reviewer(postgres_session, name="Reviewer One", initials="R1")
    r2 = crud.create_reviewer(postgres_session, name="Reviewer Two", initials="R2")
    video = crud.create_video(postgres_session, study_id=study.id, video_id="v1", title="Video")
    postgres_session.commit()
    postgres_session.refresh(video)

    crud.upsert_screening_decision(
        postgres_session, study_id=study.id, video_pk=video.id, reviewer_id=r1.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        postgres_session, study_id=study.id, video_pk=video.id, reviewer_id=r2.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )

    all_decisions = crud.list_screening_decisions_for_video(postgres_session, video.id)
    assert len(all_decisions) == 2
    assert {d.reviewer_id for d in all_decisions} == {r1.id, r2.id}
