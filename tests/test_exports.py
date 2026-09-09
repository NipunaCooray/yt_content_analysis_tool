"""Phase 7: CSV/JSON export generation -- one flat table per required
dataset (handover doc section 22), with filenames matching section 41."""

from __future__ import annotations

import datetime
import io
import json
import zipfile

import pytest

from db import crud
from services import coding_service, export_service, pilot_service, search_service
from services.youtube_api import SearchResultItem


@pytest.fixture()
def fully_populated_study(db_session, monkeypatch):
    study = crud.create_study(db_session, name="Export test study")
    reviewer = crud.create_reviewer(db_session, name="Jane Doe", initials="JD")
    query = crud.create_search_query(db_session, study_id=study.id, query_text="how to catch a bus")

    def fake_search(q, max_results, order, region_code, relevance_language):
        return [
            SearchResultItem(
                video_id="vidA", title="Bus video", description="d", channel_title="Chan",
                published_at=datetime.datetime(2024, 1, 1), thumbnail_url=None,
                video_url="https://www.youtube.com/watch?v=vidA", rank=1, raw={},
            )
        ]

    def fake_details(video_ids):
        return {
            vid: {
                "video_id": vid, "title": "Bus video", "description": "d", "channel_id": "c1",
                "channel_title": "Chan", "published_at": datetime.datetime(2024, 1, 1),
                "duration_seconds": 180, "view_count": 100, "like_count": 5, "tags": ["bus"],
                "thumbnail_url": None, "video_url": f"https://www.youtube.com/watch?v={vid}",
                "raw": {},
            }
            for vid in video_ids
        }

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", fake_search)
    pilot_service.run_pilot_search(
        db_session, study_id=study.id, queries=[query], results_per_query=1,
        search_order="relevance", reviewer_id=reviewer.id,
    )
    pilot_service.approve_search_strategy(
        db_session, study_id=study.id, reviewer_id=reviewer.id,
        results_per_query=10, search_order="relevance",
    )

    monkeypatch.setattr(search_service.youtube_api, "search_videos", fake_search)
    from services import deduplication
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", fake_details)
    search_service.run_full_search(
        db_session, study_id=study.id, queries=[query], results_per_query=1,
        search_order="relevance", approval_id=None,
    )

    video = crud.list_videos(db_session, study.id)[0]
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes="looks good",
    )
    coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type="Media",
        intended_audience="General public", older_adult_targeted="No", notes=None,
        information_domain_values={"Fares/payment": ("Present", "clear")},
        older_adult_need_values={"Seating/rest": ("Addressed", None)},
        presentation_values={"Captions available": ("Yes", None)},
        mark_complete=True,
    )
    crud.create_accuracy_claim(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer.id,
        claim_text="You need an Opal card.", category="Payment",
        official_source_url="https://transportnsw.info", assessment="Correct", notes=None,
    )
    return study


def test_export_filename_matches_spec_naming_convention(db_session):
    dataset = next(d for d in export_service.EXPORT_DATASETS if d.key == "search_queries")
    assert export_service.export_filename(1, dataset, "csv") == "study_001_search_queries.csv"

    dataset = next(d for d in export_service.EXPORT_DATASETS if d.key == "pilot_search_results")
    assert export_service.export_filename(7, dataset, "csv") == "study_007_pilot_results.csv"


def test_all_fourteen_datasets_registered():
    required = [d for d in export_service.EXPORT_DATASETS if d.required]
    assert len(required) == 14  # handover doc section 22
    # Plus reliability datasets (Phase 8), additive beyond the required 14.
    assert len(export_service.EXPORT_DATASETS) == 17
    assert len({d.key for d in export_service.EXPORT_DATASETS}) == 17  # no duplicate keys


def test_all_datasets_populated_for_a_fully_worked_study(db_session, fully_populated_study):
    study = fully_populated_study
    row_counts = {}
    for dataset in export_service.EXPORT_DATASETS:
        df = export_service.build_dataframe(db_session, study.id, dataset)
        row_counts[dataset.key] = len(df)

    assert row_counts["studies"] == 1
    assert row_counts["search_queries"] == 1
    assert row_counts["pilot_search_runs"] == 1
    assert row_counts["pilot_search_results"] == 1
    assert row_counts["full_search_runs"] == 1
    assert row_counts["raw_search_results"] == 1
    assert row_counts["unique_videos"] == 1
    assert row_counts["screening"] == 1
    assert row_counts["video_characteristics"] == 1
    assert row_counts["information_domains"] == 1
    assert row_counts["older_adult_needs"] == 1
    assert row_counts["presentation_coding"] == 1
    assert row_counts["accuracy_claims"] == 1
    assert row_counts["reviewers"] == 1


def test_unique_videos_df_includes_derived_statuses(db_session, fully_populated_study):
    study = fully_populated_study
    df = export_service.unique_videos_df(db_session, study.id)
    row = df.iloc[0]
    assert row["screening_status"] == "Included"
    assert row["coding_status"] == "Complete"
    assert row["accuracy_status"] == "In progress"  # claim exists, review not marked complete


def test_information_domains_df_flattens_with_video_context(db_session, fully_populated_study):
    study = fully_populated_study
    df = export_service.information_domains_df(db_session, study.id)
    row = df[df["domain_name"] == "Fares/payment"].iloc[0]
    assert row["value"] == "Present"
    assert row["notes"] == "clear"
    assert row["video_id"] == "vidA"


def test_csv_bytes_are_valid_and_include_header(db_session, fully_populated_study):
    study = fully_populated_study
    df = export_service.screening_df(db_session, study.id)
    csv_bytes = export_service.to_csv_bytes(df)
    text = csv_bytes.decode("utf-8")
    assert "decision" in text.splitlines()[0]
    assert "Include" in text


def test_json_bytes_are_valid_json(db_session, fully_populated_study):
    study = fully_populated_study
    df = export_service.accuracy_claims_df(db_session, study.id)
    json_bytes = export_service.to_json_bytes(df)
    parsed = json.loads(json_bytes)
    assert isinstance(parsed, list)
    assert parsed[0]["claim_text"] == "You need an Opal card."


def test_empty_dataset_still_produces_valid_csv_header_only(db_session):
    study = crud.create_study(db_session, name="Empty study")
    dataset = next(d for d in export_service.EXPORT_DATASETS if d.key == "accuracy_claims")
    df = export_service.build_dataframe(db_session, study.id, dataset)
    assert df.empty
    csv_bytes = export_service.to_csv_bytes(df)
    assert csv_bytes == b"\n"  # pandas emits just a blank line for a columnless empty frame


def test_build_zip_export_contains_all_seventeen_csvs(db_session, fully_populated_study):
    study = fully_populated_study
    zip_bytes = export_service.build_zip_export(db_session, study.id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert len(names) == 17
        assert "study_001_search_queries.csv" in names
        assert "study_001_accuracy_claims.csv" in names
        assert "study_001_reliability_summary.csv" in names
        # Spot-check one file actually has real content.
        content = zf.read("study_001_screening.csv").decode("utf-8")
        assert "Include" in content


def test_reviewers_df_exports_full_roster_not_study_scoped(db_session):
    study1 = crud.create_study(db_session, name="Study 1")
    study2 = crud.create_study(db_session, name="Study 2")
    crud.create_reviewer(db_session, name="Reviewer A", initials="RA")
    crud.create_reviewer(db_session, name="Reviewer B", initials="RB")

    df1 = export_service.reviewers_df(db_session, study1.id)
    df2 = export_service.reviewers_df(db_session, study2.id)
    assert len(df1) == 2
    assert len(df2) == 2  # reviewers table has no study_id -- same roster everywhere
