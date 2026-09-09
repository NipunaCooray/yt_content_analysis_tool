"""Phase 5: video coding -- characteristics, and the three domain-coding
sections (information coverage, older-adult needs, presentation)."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import coding_service
from utils.constants import (
    COVERAGE_VALUES,
    INFORMATION_DOMAINS,
    NEED_VALUES,
    OLDER_ADULT_NEEDS,
    PRESENTATION_ITEMS,
    PRESENTATION_VALUES,
)


@pytest.fixture()
def study_with_included_video(db_session):
    study = crud.create_study(db_session, name="Coding test study")
    reviewer = crud.create_reviewer(db_session, name="Jane Doe", initials="JD")
    included = crud.create_video(
        db_session, study_id=study.id, video_id="vidIncluded", title="Included video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    excluded = crud.create_video(
        db_session, study_id=study.id, video_id="vidExcluded", title="Excluded video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    db_session.commit()
    db_session.refresh(included)
    db_session.refresh(excluded)

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=included.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=excluded.id, reviewer_id=reviewer.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )
    return study, reviewer, included, excluded


def _default_domain_values(names: list[str], values: list[str]) -> dict:
    return {name: (values[0], None) for name in names}


def test_list_included_videos_only_returns_included(db_session, study_with_included_video):
    study, reviewer, included, excluded = study_with_included_video
    videos = crud.list_included_videos(db_session, study.id)
    assert [v.id for v in videos] == [included.id]


def test_coding_status_defaults_to_not_started():
    assert coding_service.coding_status(None) == coding_service.STATUS_NOT_STARTED


def test_save_video_coding_creates_characteristics_and_subtables(
    db_session, study_with_included_video
):
    study, reviewer, included, excluded = study_with_included_video

    info_values = _default_domain_values(INFORMATION_DOMAINS, COVERAGE_VALUES)
    info_values["Fares/payment"] = ("Present", "Explained clearly with on-screen tap example.")
    need_values = _default_domain_values(OLDER_ADULT_NEEDS, NEED_VALUES)
    pres_values = _default_domain_values(PRESENTATION_ITEMS, PRESENTATION_VALUES)

    coding = coding_service.save_video_coding(
        db_session,
        study_id=study.id,
        video_pk=included.id,
        reviewer_id=reviewer.id,
        transport_modes=["Bus", "Train"],
        jurisdictions=["NSW"],
        uploader_type="Government / transport authority",
        intended_audience="Older adults",
        older_adult_targeted="Yes",
        notes="Clear and well-paced.",
        information_domain_values=info_values,
        older_adult_need_values=need_values,
        presentation_values=pres_values,
        mark_complete=False,
    )

    assert coding.status == coding_service.STATUS_IN_PROGRESS
    assert coding.transport_modes_json == ["Bus", "Train"]
    assert coding.coded_at is not None

    domain_codes = crud.list_information_domain_codes(db_session, coding.id)
    assert len(domain_codes) == len(INFORMATION_DOMAINS)
    assert domain_codes["Fares/payment"].value == "Present"
    assert domain_codes["Fares/payment"].notes == "Explained clearly with on-screen tap example."

    need_codes = crud.list_older_adult_need_codes(db_session, coding.id)
    assert len(need_codes) == len(OLDER_ADULT_NEEDS)

    presentation_codes = crud.list_presentation_codes(db_session, coding.id)
    assert len(presentation_codes) == len(PRESENTATION_ITEMS)


def test_save_video_coding_upserts_in_place_without_duplicating_rows(
    db_session, study_with_included_video
):
    study, reviewer, included, excluded = study_with_included_video
    info_values = _default_domain_values(INFORMATION_DOMAINS, COVERAGE_VALUES)
    need_values = _default_domain_values(OLDER_ADULT_NEEDS, NEED_VALUES)
    pres_values = _default_domain_values(PRESENTATION_ITEMS, PRESENTATION_VALUES)

    first = coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=included.id, reviewer_id=reviewer.id,
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type=None,
        intended_audience=None, older_adult_targeted=None, notes=None,
        information_domain_values=info_values, older_adult_need_values=need_values,
        presentation_values=pres_values, mark_complete=False,
    )

    info_values["Fares/payment"] = ("Absent", "Changed my mind")
    second = coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=included.id, reviewer_id=reviewer.id,
        transport_modes=["Bus", "Ferry"], jurisdictions=["NSW"], uploader_type=None,
        intended_audience=None, older_adult_targeted=None, notes=None,
        information_domain_values=info_values, older_adult_need_values=need_values,
        presentation_values=pres_values, mark_complete=True,
    )

    assert first.id == second.id  # same coding record, edited in place
    assert second.status == coding_service.STATUS_COMPLETE
    assert second.transport_modes_json == ["Bus", "Ferry"]

    domain_codes = crud.list_information_domain_codes(db_session, second.id)
    assert len(domain_codes) == len(INFORMATION_DOMAINS)  # no duplicates
    assert domain_codes["Fares/payment"].value == "Absent"

    assert len(crud.list_video_codings(db_session, study.id)) == 1


def test_compute_progress_counts_by_status(db_session, study_with_included_video):
    study, reviewer, included, excluded = study_with_included_video
    info_values = _default_domain_values(INFORMATION_DOMAINS, COVERAGE_VALUES)
    need_values = _default_domain_values(OLDER_ADULT_NEEDS, NEED_VALUES)
    pres_values = _default_domain_values(PRESENTATION_ITEMS, PRESENTATION_VALUES)

    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=included.id, reviewer_id=reviewer.id,
        transport_modes=[], jurisdictions=[], uploader_type=None, intended_audience=None,
        older_adult_targeted=None, notes=None, information_domain_values=info_values,
        older_adult_need_values=need_values, presentation_values=pres_values,
        mark_complete=True,
    )

    codings = crud.list_video_codings(db_session, study.id)
    progress = coding_service.compute_progress([included.id], codings)
    assert progress.total == 1
    assert progress.complete == 1
    assert progress.not_started == 0
