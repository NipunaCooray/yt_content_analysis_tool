"""scripts/migrate_sqlite_to_postgres.py -- tested structurally against two
SQLite files (no live PostgreSQL server available in CI), since the
migration logic (row copying, FK-order, id preservation, idempotent skip)
is dialect-agnostic SQLAlchemy Core. The one PostgreSQL-only step (resetting
the identity/serial sequence) is guarded by dialect name and simply doesn't
run against a SQLite target -- see test_migrate_postgres_integration.py for
a real-Postgres smoke test that runs when a server is available.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from db import crud
from db.database import get_session
from db.models import Base, utcnow
from scripts.migrate_sqlite_to_postgres import migrate


@pytest.fixture()
def seeded_source_db(tmp_path, monkeypatch):
    """A real SQLite file (not :memory:) seeded via the app's normal CRUD
    path, since the migration script opens its own connection to the file."""
    src_path = tmp_path / "source.db"
    monkeypatch.setenv("DATABASE_PATH", str(src_path))

    # db.database caches its engine/session as module globals; reset them so
    # get_session() picks up the DATABASE_PATH set above rather than a
    # previously-resolved engine from an earlier test.
    import db.database as database_module
    database_module._engine = None
    database_module._backend = None
    database_module._SessionLocal = None

    engine = create_engine(f"sqlite:///{src_path}")
    Base.metadata.create_all(engine)

    db = get_session()
    study = crud.create_study(db, name="Migration test study")
    reviewer = crud.create_reviewer(db, name="Test Reviewer", initials="TR")
    query = crud.create_search_query(db, study_id=study.id, query_text="how to catch a bus")
    video = crud.create_video(db, study_id=study.id, video_id="v1", title="Test video")
    db.commit()
    db.refresh(video)
    crud.upsert_screening_decision(
        db, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.create_pilot_search_run(
        db, study_id=study.id, status="completed",
        started_at=utcnow(), completed_at=utcnow(),
    )
    db.close()

    # Reset the cached engine again so later tests (and get_database_path())
    # aren't left pointed at this temp file.
    database_module._engine = None
    database_module._backend = None
    database_module._SessionLocal = None

    return src_path


def test_dry_run_reports_counts_without_writing(seeded_source_db, tmp_path):
    target_path = tmp_path / "target.db"
    report = migrate(
        f"sqlite:///{seeded_source_db}", f"sqlite:///{target_path}", dry_run=True
    )
    by_table = {row[0]: row for row in report}

    assert by_table["studies"][1] == 1
    assert by_table["videos"][1] == 1
    assert by_table["screening_decisions"][1] == 1
    assert all(row[3] == "dry run -- not written" for row in report)
    # SQLite creates the file on connect regardless of writes, but dry run
    # must create no tables/rows in it.
    if target_path.exists():
        import sqlite3

        conn = sqlite3.connect(target_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        assert tables == []


def test_migration_copies_all_rows_and_preserves_relationships(seeded_source_db, tmp_path):
    target_path = tmp_path / "target.db"
    report = migrate(f"sqlite:///{seeded_source_db}", f"sqlite:///{target_path}", dry_run=False)

    by_table = {row[0]: row for row in report}
    assert by_table["studies"] == ("studies", 1, 1, "+1 inserted")
    assert by_table["videos"] == ("videos", 1, 1, "+1 inserted")
    assert by_table["screening_decisions"] == ("screening_decisions", 1, 1, "+1 inserted")

    # Relationships survive because ids are preserved verbatim.
    target_engine = create_engine(f"sqlite:///{target_path}")
    from sqlalchemy.orm import sessionmaker

    TargetSession = sessionmaker(bind=target_engine, expire_on_commit=False)
    tdb = TargetSession()
    study = crud.get_study(tdb, 1)
    assert study.name == "Migration test study"
    videos = crud.list_videos(tdb, study.id)
    assert len(videos) == 1
    decisions = crud.list_screening_decisions(tdb, study.id)
    assert decisions[videos[0].id].decision == "Include"
    tdb.close()


def test_migration_is_idempotent_on_rerun(seeded_source_db, tmp_path):
    target_path = tmp_path / "target.db"
    migrate(f"sqlite:///{seeded_source_db}", f"sqlite:///{target_path}", dry_run=False)

    # Re-running must not duplicate rows -- everything should be skipped.
    second_report = migrate(f"sqlite:///{seeded_source_db}", f"sqlite:///{target_path}", dry_run=False)
    by_table = {row[0]: row for row in second_report}

    assert by_table["studies"][3] == "0 already present (skipped)" or "already present" in by_table["studies"][3]
    assert by_table["studies"][2] == 1  # still exactly 1 row, not 2

    target_engine = create_engine(f"sqlite:///{target_path}")
    from sqlalchemy.orm import sessionmaker

    TargetSession = sessionmaker(bind=target_engine, expire_on_commit=False)
    tdb = TargetSession()
    assert len(crud.list_studies(tdb)) == 1
    tdb.close()


def test_migration_adds_new_rows_added_to_source_after_first_run(seeded_source_db, tmp_path):
    """A second source row (e.g. the team kept using SQLite briefly after a
    first migration attempt) is picked up on re-run without touching the
    already-migrated row."""
    target_path = tmp_path / "target.db"
    migrate(f"sqlite:///{seeded_source_db}", f"sqlite:///{target_path}", dry_run=False)

    src_engine = create_engine(f"sqlite:///{seeded_source_db}")
    from sqlalchemy.orm import sessionmaker

    SrcSession = sessionmaker(bind=src_engine, expire_on_commit=False)
    sdb = SrcSession()
    crud.create_reviewer(sdb, name="Second Reviewer", initials="SR")
    sdb.close()

    report = migrate(f"sqlite:///{seeded_source_db}", f"sqlite:///{target_path}", dry_run=False)
    by_table = {row[0]: row for row in report}
    assert by_table["reviewers"] == (
        "reviewers", 2, 2, "+1 inserted, 1 already present (skipped)"
    )
