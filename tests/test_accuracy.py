"""Phase 6: claim-level accuracy assessment."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import accuracy_service


@pytest.fixture()
def study_with_included_video(db_session):
    study = crud.create_study(db_session, name="Accuracy test study")
    reviewer = crud.create_reviewer(db_session, name="Jane Doe", initials="JD")
    video = crud.create_video(
        db_session, study_id=study.id, video_id="vidA", title="Bus video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    db_session.commit()
    db_session.refresh(video)
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    return study, reviewer, video


def test_accuracy_status_not_started_with_no_claims():
    assert accuracy_service.accuracy_status(None, 0) == accuracy_service.STATUS_NOT_STARTED


def test_accuracy_status_in_progress_with_claims_but_not_marked_complete():
    assert accuracy_service.accuracy_status(None, 2) == accuracy_service.STATUS_IN_PROGRESS


def test_create_list_update_delete_claim(db_session, study_with_included_video):
    study, reviewer, video = study_with_included_video

    claim = crud.create_accuracy_claim(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        claim_text="You need an Opal card to catch the bus.", category="Payment",
        official_source_url="https://transportnsw.info", assessment="Correct", notes=None,
    )
    assert claim.id is not None

    claims = crud.list_accuracy_claims(db_session, study.id, video.id)
    assert len(claims) == 1

    updated = crud.update_accuracy_claim(db_session, claim.id, assessment="Outdated")
    assert updated.assessment == "Outdated"

    assert crud.delete_accuracy_claim(db_session, claim.id) is True
    assert crud.list_accuracy_claims(db_session, study.id, video.id) == []
    assert crud.delete_accuracy_claim(db_session, claim.id) is False  # already gone


def test_multiple_claims_per_video_all_preserved(db_session, study_with_included_video):
    study, reviewer, video = study_with_included_video

    crud.create_accuracy_claim(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        claim_text="Claim 1", category="Payment", official_source_url=None,
        assessment="Correct", notes=None,
    )
    crud.create_accuracy_claim(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        claim_text="Claim 2", category="Concessions", official_source_url=None,
        assessment="Incorrect", notes=None,
    )

    claims = crud.list_accuracy_claims(db_session, study.id, video.id)
    assert len(claims) == 2

    counts = crud.count_accuracy_claims(db_session, study.id)
    assert counts[video.id] == 2


def test_set_accuracy_review_complete_and_reopen(db_session, study_with_included_video):
    study, reviewer, video = study_with_included_video

    status = crud.set_accuracy_review_complete(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        is_complete=True,
    )
    assert status.is_complete is True
    assert status.completed_at is not None

    reopened = crud.set_accuracy_review_complete(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        is_complete=False,
    )
    assert reopened.id == status.id  # same row, edited in place
    assert reopened.is_complete is False
    assert reopened.completed_at is None

    assert len(crud.list_accuracy_review_statuses(db_session, study.id)) == 1


def test_compute_progress_reflects_claims_and_completion(db_session, study_with_included_video):
    study, reviewer, video = study_with_included_video

    # Not started.
    progress = accuracy_service.compute_progress([video.id], {}, {})
    assert progress.not_started == 1

    # In progress once a claim exists.
    crud.create_accuracy_claim(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        claim_text="Claim", category="Other", official_source_url=None,
        assessment="Unverifiable", notes=None,
    )
    claim_counts = crud.count_accuracy_claims(db_session, study.id)
    progress = accuracy_service.compute_progress([video.id], {}, claim_counts)
    assert progress.in_progress == 1

    # Complete once marked.
    crud.set_accuracy_review_complete(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        is_complete=True,
    )
    review_statuses = crud.list_accuracy_review_statuses(db_session, study.id)
    progress = accuracy_service.compute_progress([video.id], review_statuses, claim_counts)
    assert progress.complete == 1
