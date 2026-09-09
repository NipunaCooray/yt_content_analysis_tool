"""Phase 1: database creation and CRUD tests."""

from __future__ import annotations

from db import crud


def test_create_and_list_study(db_session):
    study = crud.create_study(db_session, name="Pilot study", search_status="Draft")
    assert study.id is not None
    assert study.country == "Australia"  # SQLAlchemy default applies on flush
    assert study.language == "English"

    studies = crud.list_studies(db_session)
    assert len(studies) == 1
    assert studies[0].name == "Pilot study"


def test_update_study(db_session):
    study = crud.create_study(db_session, name="Original name")
    updated = crud.update_study(db_session, study.id, name="Renamed", search_status="Pilot testing")
    assert updated.name == "Renamed"
    assert updated.search_status == "Pilot testing"


def test_delete_study(db_session):
    study = crud.create_study(db_session, name="To delete")
    assert crud.delete_study(db_session, study.id) is True
    assert crud.get_study(db_session, study.id) is None
    assert crud.delete_study(db_session, study.id) is False


def test_reviewer_crud(db_session):
    reviewer = crud.create_reviewer(db_session, name="Jane Doe", initials="JD")
    assert reviewer.id is not None

    updated = crud.update_reviewer(db_session, reviewer.id, initials="JD2")
    assert updated.initials == "JD2"

    assert crud.delete_reviewer(db_session, reviewer.id) is True
    assert crud.list_reviewers(db_session) == []


def test_search_query_crud(db_session):
    study = crud.create_study(db_session, name="Study")
    query = crud.create_search_query(
        db_session, study_id=study.id, query_text="how to catch a bus Australia", category="Bus"
    )
    assert query.is_active is True

    queries = crud.list_search_queries(db_session, study.id)
    assert len(queries) == 1

    crud.set_query_active(db_session, query.id, False)
    active = crud.list_search_queries(db_session, study.id, active_only=True)
    assert active == []

    dup = crud.duplicate_search_query(db_session, query.id)
    assert dup.query_text.endswith("(copy)")
    assert dup.is_active is True

    assert crud.delete_search_query(db_session, query.id) is True


def test_audit_log_records_events(db_session):
    study = crud.create_study(db_session, name="Study")
    crud.create_search_query(db_session, study_id=study.id, query_text="test query")

    events = crud.list_audit_log(db_session, study_id=study.id)
    action_types = {e.action_type for e in events}
    assert "study_created" in action_types
    assert "query_added" in action_types
