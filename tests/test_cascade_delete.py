"""Foreign-key delete behavior (Streamlit Cloud + PostgreSQL migration): this
was a real bug found while testing against a live Supabase database, where
PostgreSQL actually enforces foreign keys (unlike the SQLite fixture before
this test file existed, which never had PRAGMA foreign_keys=ON either --
see conftest.py). Deleting a study/video/reviewer must cascade correctly:
- Deleting a study or video removes everything owned by it (ownership).
- Deleting a reviewer only clears the attribution (reviewer_id -> NULL) on
  their past work -- it must never delete real collected research data.
"""

from __future__ import annotations

import pytest

from db import crud
from services import coding_service


@pytest.fixture()
def fully_populated_study(db_session):
    """A study with one video carrying data in every dependent table."""
    study = crud.create_study(db_session, name="Cascade test study")
    reviewer = crud.create_reviewer(db_session, name="Test Reviewer", initials="TR")
    query = crud.create_search_query(db_session, study_id=study.id, query_text="test query")
    video = crud.create_video(db_session, study_id=study.id, video_id="v1", title="Test video")
    db_session.commit()
    db_session.refresh(video)

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type="Media",
        intended_audience="General public", older_adult_targeted="No", notes=None,
        information_domain_values={"Fares/payment": ("Present", None)},
        older_adult_need_values={"Seating/rest": ("Addressed", None)},
        presentation_values={"Captions available": ("Yes", None)},
        mark_complete=True,
    )
    crud.create_accuracy_claim(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        claim_text="test claim", category="Payment", official_source_url=None,
        assessment="Correct", notes=None,
    )
    crud.set_accuracy_review_complete(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id, is_complete=True,
    )
    crud.select_random_double_coding_sample(db_session, study.id, "screening", [video.id], 100)
    run = crud.create_pilot_search_run(db_session, study_id=study.id, reviewer_id=reviewer.id)
    crud.add_pilot_search_result(
        db_session, pilot_search_run_id=run.id, query_id=query.id, video_id="v1", result_rank=1,
    )
    db_session.commit()

    return study, reviewer, video, query


def test_deleting_a_study_cascades_through_every_dependent_table(db_session, fully_populated_study):
    """The actual bug: this used to raise IntegrityError on PostgreSQL."""
    study, reviewer, video, query = fully_populated_study

    crud.delete_study(db_session, study.id)

    assert crud.get_study(db_session, study.id) is None
    assert crud.list_videos(db_session, study.id) == []
    assert crud.list_screening_decisions(db_session, study.id) == {}
    assert crud.list_video_codings(db_session, study.id) == {}
    assert crud.list_accuracy_claims(db_session, study.id, video.id) == []
    assert crud.get_accuracy_review_status(db_session, video.id) is None
    assert crud.list_double_coding_sample_video_ids(db_session, study.id, "screening") == set()
    assert crud.list_pilot_search_runs(db_session, study.id) == []
    assert crud.list_audit_log(db_session, study_id=study.id) == []
    # Search queries belong to (are owned by) the study, so they cascade too.
    assert crud.get_search_query(db_session, query.id) is None

    # The reviewer is independent of any one study -- untouched.
    assert crud.get_reviewer(db_session, reviewer.id) is not None


def test_deleting_a_video_cascades_but_leaves_the_study_and_other_videos(db_session, fully_populated_study):
    study, reviewer, video, query = fully_populated_study
    other_video = crud.create_video(db_session, study_id=study.id, video_id="v2", title="Other video")
    db_session.commit()
    db_session.refresh(other_video)
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=other_video.id, reviewer_id=reviewer.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )

    from sqlalchemy import delete as sa_delete

    from db.models import Video
    db_session.execute(sa_delete(Video).where(Video.id == video.id))
    db_session.commit()

    assert crud.get_study(db_session, study.id) is not None  # study itself untouched
    remaining_videos = crud.list_videos(db_session, study.id)
    assert [v.id for v in remaining_videos] == [other_video.id]  # only the other video survives
    assert crud.list_screening_decisions(db_session, study.id) == {
        other_video.id: crud.list_screening_decisions(db_session, study.id)[other_video.id]
    }


def test_deleting_a_reviewer_preserves_data_and_only_clears_attribution(db_session, fully_populated_study):
    """Core research-integrity requirement: removing a reviewer record must
    never discard real collected screening/coding/accuracy data."""
    study, reviewer, video, query = fully_populated_study

    crud.delete_reviewer(db_session, reviewer.id)

    decisions = crud.list_screening_decisions(db_session, study.id)
    assert decisions[video.id].decision == "Include"  # data preserved
    assert decisions[video.id].reviewer_id is None  # attribution cleared

    codings = crud.list_video_codings(db_session, study.id)
    assert codings[video.id].transport_modes_json == ["Bus"]
    assert codings[video.id].reviewer_id is None

    claims = crud.list_accuracy_claims(db_session, study.id, video.id)
    assert len(claims) == 1
    assert claims[0].claim_text == "test claim"
    assert claims[0].reviewer_id is None


def test_deleting_a_search_query_preserves_pilot_results(db_session, fully_populated_study):
    """Never discard raw/pilot search data just because a query was edited
    or removed later -- only the query attribution is lost."""
    study, reviewer, video, query = fully_populated_study
    run = crud.list_pilot_search_runs(db_session, study.id)[0]

    crud.delete_search_query(db_session, query.id)

    results = crud.list_pilot_search_results(db_session, run.id)
    assert len(results) == 1  # the pilot result survives
    assert results[0].video_id == "v1"
    assert results[0].query_id is None  # attribution cleared, not the row


def test_deleting_an_approval_preserves_full_search_runs(db_session):
    """FullSearchRun.approval_id -> SET NULL: losing the approval record
    (not currently exposed for deletion in the UI, but defensive) must not
    delete the full-search run itself."""
    study = crud.create_study(db_session, name="Approval cascade test")
    approval = crud.create_search_strategy_approval(
        db_session, study_id=study.id, query_snapshot_json=[], parameters_json={},
    )
    run = crud.create_full_search_run(db_session, study_id=study.id, approval_id=approval.id)

    from sqlalchemy import delete as sa_delete

    from db.models import SearchStrategyApproval
    db_session.execute(sa_delete(SearchStrategyApproval).where(SearchStrategyApproval.id == approval.id))
    db_session.commit()
    db_session.expire_all()  # the raw Core delete bypasses the ORM identity map

    fetched_run = crud.get_full_search_run(db_session, run.id)
    assert fetched_run is not None
    assert fetched_run.approval_id is None
