"""Phase 8: reviewer-scoped double screening/coding and inter-rater
reliability (percentage agreement, Cohen's kappa)."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import coding_service, reliability_service


@pytest.fixture()
def study_with_two_reviewers_and_videos(db_session):
    study = crud.create_study(db_session, name="Reliability test study")
    r1 = crud.create_reviewer(db_session, name="Reviewer One", initials="R1")
    r2 = crud.create_reviewer(db_session, name="Reviewer Two", initials="R2")
    videos = []
    for i in range(4):
        v = crud.create_video(
            db_session, study_id=study.id, video_id=f"vid{i}", title=f"Video {i}",
            channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
        )
        videos.append(v)
    db_session.commit()
    for v in videos:
        db_session.refresh(v)
    return study, r1, r2, videos


# ---------------------------------------------------------------------------
# Reviewer-scoped upsert never overwrites another reviewer's record
# ---------------------------------------------------------------------------


def test_second_reviewer_screening_does_not_overwrite_first(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    v = videos[0]

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r1.id,
        decision="Include", exclusion_reason=None, notes="R1's call",
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r2.id,
        decision="Exclude", exclusion_reason="News/media", notes="R2's call",
    )

    all_decisions = crud.list_screening_decisions_for_video(db_session, v.id)
    assert len(all_decisions) == 2  # both preserved, not one overwriting the other
    assert {d.reviewer_id for d in all_decisions} == {r1.id, r2.id}

    r1_own = crud.get_screening_decision(db_session, v.id, r1.id)
    assert r1_own.decision == "Include"
    r2_own = crud.get_screening_decision(db_session, v.id, r2.id)
    assert r2_own.decision == "Exclude"


def test_canonical_screening_decision_is_earliest_reviewer(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    v = videos[0]

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r1.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r2.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )

    canonical = crud.list_screening_decisions(db_session, study.id)
    assert canonical[v.id].reviewer_id == r1.id
    assert canonical[v.id].decision == "Include"


def test_list_included_videos_uses_canonical_decision_only(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    v = videos[0]

    # R1 (earlier/canonical) says Exclude; R2 (later) says Include.
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r1.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r2.id,
        decision="Include", exclusion_reason=None, notes=None,
    )

    included = crud.list_included_videos(db_session, study.id)
    assert included == []  # canonical (R1) says Exclude, so it's not included
    # And no duplicate rows even though 2 screening_decisions rows exist for it.


def test_second_reviewer_coding_does_not_overwrite_first(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    v = videos[0]
    empty = {}

    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r1.id,
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type="Media",
        intended_audience="General public", older_adult_targeted="No", notes=None,
        information_domain_values=empty, older_adult_need_values=empty,
        presentation_values=empty, mark_complete=True,
    )
    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r2.id,
        transport_modes=["Train"], jurisdictions=["VIC"], uploader_type="Government / transport authority",
        intended_audience="Older adults", older_adult_targeted="Yes", notes=None,
        information_domain_values=empty, older_adult_need_values=empty,
        presentation_values=empty, mark_complete=True,
    )

    all_codings = crud.list_video_codings_for_video(db_session, v.id)
    assert len(all_codings) == 2
    assert all_codings[0].reviewer_id == r1.id
    assert all_codings[0].transport_modes_json == ["Bus"]
    assert all_codings[1].reviewer_id == r2.id
    assert all_codings[1].transport_modes_json == ["Train"]


# ---------------------------------------------------------------------------
# Double-coding sample selection
# ---------------------------------------------------------------------------


def test_select_random_double_coding_sample_respects_target_percentage(
    db_session, study_with_two_reviewers_and_videos
):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    video_ids = [v.id for v in videos]  # 4 videos

    added = crud.select_random_double_coding_sample(db_session, study.id, "screening", video_ids, 50)
    assert added == 2  # 50% of 4

    sample = crud.list_double_coding_sample_video_ids(db_session, study.id, "screening")
    assert len(sample) == 2
    assert sample.issubset(set(video_ids))


def test_select_random_double_coding_sample_does_not_shrink_existing_sample(
    db_session, study_with_two_reviewers_and_videos
):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    video_ids = [v.id for v in videos]

    crud.select_random_double_coding_sample(db_session, study.id, "screening", video_ids, 25)
    first_sample = crud.list_double_coding_sample_video_ids(db_session, study.id, "screening")
    assert len(first_sample) == 1

    crud.select_random_double_coding_sample(db_session, study.id, "screening", video_ids, 75)
    second_sample = crud.list_double_coding_sample_video_ids(db_session, study.id, "screening")
    assert first_sample.issubset(second_sample)
    assert len(second_sample) == 3


# ---------------------------------------------------------------------------
# Agreement statistics
# ---------------------------------------------------------------------------


def test_percentage_agreement_and_kappa_perfect_agreement():
    pairs = [("Include", "Include"), ("Exclude", "Exclude"), ("Unsure", "Unsure")]
    assert reliability_service.percentage_agreement(pairs) == 100.0
    assert reliability_service.cohens_kappa(pairs) == 1.0


def test_percentage_agreement_and_kappa_no_agreement():
    pairs = [("Include", "Exclude"), ("Exclude", "Include")]
    assert reliability_service.percentage_agreement(pairs) == 0.0
    # Chance-corrected agreement should be <= observed (0) for this symmetric case.
    kappa = reliability_service.cohens_kappa(pairs)
    assert kappa is not None
    assert kappa <= 0


def test_kappa_known_worked_example():
    # 10 items, 2 raters. Rater A: 6 Yes, 4 No. Rater B: 5 Yes, 5 No.
    pairs = [
        ("Yes", "Yes"), ("Yes", "Yes"), ("Yes", "Yes"), ("Yes", "No"),
        ("Yes", "Yes"), ("Yes", "No"), ("No", "No"), ("No", "No"),
        ("No", "Yes"), ("No", "No"),
    ]
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n  # 7/10 agreements
    pe = (6 / n) * (5 / n) + (4 / n) * (5 / n)  # chance agreement from each rater's marginals
    expected_kappa = round((po - pe) / (1 - pe), 3)
    assert expected_kappa == 0.4  # sanity-check the hand worked example itself
    assert reliability_service.cohens_kappa(pairs) == expected_kappa


def test_kappa_undefined_with_no_variation():
    pairs = [("Include", "Include"), ("Include", "Include")]
    assert reliability_service.cohens_kappa(pairs) is None


def test_kappa_and_agreement_empty_pairs():
    assert reliability_service.percentage_agreement([]) is None
    assert reliability_service.cohens_kappa([]) is None


def test_jaccard_similarity():
    pairs = [
        (frozenset({"Bus", "Train"}), frozenset({"Bus", "Train"})),  # identical -> 1.0
        (frozenset({"Bus"}), frozenset({"Bus", "Ferry"})),  # 1/2 overlap -> 0.5
    ]
    result = reliability_service.jaccard_similarity(pairs)
    assert result == 75.0  # average of 100% and 50%


def test_jaccard_similarity_both_empty_counts_as_full_agreement():
    pairs = [(frozenset(), frozenset())]
    assert reliability_service.jaccard_similarity(pairs) == 100.0


# ---------------------------------------------------------------------------
# End-to-end reliability computation with real double-screened data
# ---------------------------------------------------------------------------


def test_screening_reliability_end_to_end(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos

    # Video 0: both say Include (agree). Video 1: disagree.
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=videos[0].id, reviewer_id=r1.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=videos[0].id, reviewer_id=r2.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=videos[1].id, reviewer_id=r1.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=videos[1].id, reviewer_id=r2.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )
    # Video 2: only one reviewer -- not double-screened, excluded from stats.
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=videos[2].id, reviewer_id=r1.id,
        decision="Unsure", exclusion_reason=None, notes=None,
    )

    all_videos = crud.list_videos(db_session, study.id)
    double_screened = reliability_service.double_coded_videos(db_session, study.id, all_videos, "screening")
    assert len(double_screened) == 2  # videos 0 and 1 only

    stat, disagreements = reliability_service.screening_reliability(db_session, study.id, double_screened)
    assert stat.n_pairs == 2
    assert stat.percentage_agreement == 50.0
    assert len(disagreements) == 1
    assert disagreements[0].video_pk == videos[1].id
    assert disagreements[0].reviewer_a_value == "Include"
    assert disagreements[0].reviewer_b_value == "Exclude"


def test_coding_characteristics_reliability_end_to_end(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    v = videos[0]
    empty = {}

    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r1.id,
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type="Media",
        intended_audience="General public", older_adult_targeted="No", notes=None,
        information_domain_values=empty, older_adult_need_values=empty,
        presentation_values=empty, mark_complete=True,
    )
    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r2.id,
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type="Media",
        intended_audience="Older adults", older_adult_targeted="Yes", notes=None,
        information_domain_values=empty, older_adult_need_values=empty,
        presentation_values=empty, mark_complete=True,
    )

    double_coded = reliability_service.double_coded_videos(db_session, study.id, [v], "coding")
    assert len(double_coded) == 1

    stats, disagreements = reliability_service.coding_characteristics_reliability(
        db_session, study.id, double_coded
    )
    by_field = {s.field_name: s for s in stats}
    assert by_field["Uploader type"].percentage_agreement == 100.0
    assert by_field["Audience"].percentage_agreement == 0.0
    assert by_field["Aimed at older adults?"].percentage_agreement == 0.0
    assert by_field["Transport mode(s)"].percentage_agreement == 100.0  # jaccard, identical sets

    disagreement_fields = {d.field_name for d in disagreements}
    assert "Audience" in disagreement_fields
    assert "Aimed at older adults?" in disagreement_fields
    assert "Uploader type" not in disagreement_fields


def test_domain_code_reliability_end_to_end(db_session, study_with_two_reviewers_and_videos):
    study, r1, r2, videos = study_with_two_reviewers_and_videos
    v = videos[0]

    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r1.id,
        transport_modes=[], jurisdictions=[], uploader_type=None, intended_audience=None,
        older_adult_targeted=None, notes=None,
        information_domain_values={"Fares/payment": ("Present", None)},
        older_adult_need_values={}, presentation_values={}, mark_complete=True,
    )
    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=v.id, reviewer_id=r2.id,
        transport_modes=[], jurisdictions=[], uploader_type=None, intended_audience=None,
        older_adult_targeted=None, notes=None,
        information_domain_values={"Fares/payment": ("Absent", None)},
        older_adult_need_values={}, presentation_values={}, mark_complete=True,
    )

    double_coded = reliability_service.double_coded_videos(db_session, study.id, [v], "coding")
    stats = reliability_service.information_domain_reliability(db_session, double_coded)
    fares_stat = next(s for s in stats if s.field_name == "Fares/payment")
    assert fares_stat.n_pairs == 1
    assert fares_stat.percentage_agreement == 0.0
