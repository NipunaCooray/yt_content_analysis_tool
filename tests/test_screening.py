"""Phase 4: screening decisions and status derivation."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import screening_service


@pytest.fixture()
def study_with_videos(db_session):
    study = crud.create_study(db_session, name="Screening test study")
    reviewer = crud.create_reviewer(db_session, name="Jane Doe", initials="JD")
    v1 = crud.create_video(
        db_session, study_id=study.id, video_id="vidA", title="Bus video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    v2 = crud.create_video(
        db_session, study_id=study.id, video_id="vidB", title="Train video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    db_session.commit()
    db_session.refresh(v1)
    db_session.refresh(v2)
    return study, reviewer, [v1, v2]


def test_screening_status_defaults_to_not_screened():
    assert screening_service.screening_status(None) == screening_service.STATUS_NOT_SCREENED


def test_upsert_screening_decision_creates_then_edits(db_session, study_with_videos):
    study, reviewer, videos = study_with_videos
    v1 = videos[0]

    created = crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Unsure", exclusion_reason=None, notes="need a second look",
    )
    assert created.decision == "Unsure"
    assert created.screened_at is not None
    first_screened_at = created.screened_at

    edited = crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Exclude", exclusion_reason="Not Australian", notes="confirmed not AU content",
    )

    # Same row edited in place, not a second row.
    assert edited.id == created.id
    assert edited.decision == "Exclude"
    assert edited.exclusion_reason == "Not Australian"
    assert edited.screened_at == first_screened_at  # preserved from first save

    all_decisions = crud.list_screening_decisions(db_session, study.id)
    assert len(all_decisions) == 1


def test_exclusion_reason_cleared_when_decision_changes_away_from_exclude(
    db_session, study_with_videos
):
    study, reviewer, videos = study_with_videos
    v1 = videos[0]

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Exclude", exclusion_reason="News/media", notes=None,
    )
    updated = crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason="News/media", notes=None,
    )
    assert updated.decision == "Include"
    assert updated.exclusion_reason is None


def test_compute_progress_counts_each_status(db_session, study_with_videos):
    study, reviewer, videos = study_with_videos
    v1, v2 = videos

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    # v2 left unscreened.

    decisions = crud.list_screening_decisions(db_session, study.id)
    progress = screening_service.compute_progress(videos, decisions)

    assert progress.total == 2
    assert progress.included == 1
    assert progress.not_screened == 1
    assert progress.excluded == 0
    assert progress.unsure == 0


def test_screening_decision_audit_events_logged(db_session, study_with_videos):
    study, reviewer, videos = study_with_videos
    v1 = videos[0]

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v1.id, reviewer_id=reviewer.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )

    events = crud.list_audit_log(db_session, study_id=study.id)
    action_types = [e.action_type for e in events]
    assert "screening_decision_created" in action_types
    assert "screening_decision_edited" in action_types
