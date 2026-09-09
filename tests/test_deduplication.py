"""Phase 3: deduplication of raw full-search results into the videos master
list. The YouTube metadata API is mocked throughout (handover doc section 36)."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import deduplication
from services.youtube_api import YouTubeAPIError


@pytest.fixture()
def study_with_run_and_raw_results(db_session):
    study = crud.create_study(db_session, name="Dedup test study")
    q1 = crud.create_search_query(db_session, study_id=study.id, query_text="how to catch a bus")
    q2 = crud.create_search_query(db_session, study_id=study.id, query_text="how to use trains")
    run = crud.create_full_search_run(db_session, study_id=study.id, parameters_json={})

    # video A is found by both queries (a duplicate occurrence); B and C are unique.
    rows = [
        (q1.id, "video_A", 1, "Bus video (from q1)"),
        (q1.id, "video_B", 2, "Another bus video"),
        (q2.id, "video_A", 1, "Bus video (from q2, same video)"),
        (q2.id, "video_C", 2, "Train video"),
    ]
    for query_id, video_id, rank, title in rows:
        crud.add_search_result_raw(
            db_session,
            full_search_run_id=run.id,
            query_id=query_id,
            video_id=video_id,
            result_rank=rank,
            title=title,
            channel_title="Some Channel",
            published_at=datetime.datetime(2024, 1, 1),
            thumbnail_url=f"https://example.com/{video_id}.jpg",
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            raw_json={},
        )
    db_session.commit()
    return study, run


def _fake_details(video_ids: list[str]) -> dict[str, dict]:
    return {
        vid: {
            "video_id": vid,
            "title": f"{vid} (enriched)",
            "description": "Full description.",
            "channel_id": "chan1",
            "channel_title": "Some Channel",
            "published_at": datetime.datetime(2024, 1, 1),
            "duration_seconds": 300,
            "view_count": 1000,
            "like_count": 50,
            "tags": ["bus", "australia"],
            "thumbnail_url": f"https://example.com/{vid}.jpg",
            "video_url": f"https://www.youtube.com/watch?v={vid}",
            "raw": {},
        }
        for vid in video_ids
    }


def test_deduplicate_creates_one_video_per_unique_id(
    db_session, study_with_run_and_raw_results, monkeypatch
):
    study, run = study_with_run_and_raw_results
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _fake_details)

    outcome = deduplication.deduplicate_and_enrich(db_session, study.id)

    assert outcome.raw_count == 4
    assert outcome.unique_count == 3  # video_A, video_B, video_C
    assert outcome.newly_created == 3
    assert outcome.metadata_unavailable == []

    videos = crud.list_videos(db_session, study.id)
    assert len(videos) == 3
    video_a = crud.get_video_by_youtube_id(db_session, study.id, "video_A")
    assert video_a.title == "video_A (enriched)"
    assert video_a.view_count == 1000


def test_deduplicate_is_idempotent(db_session, study_with_run_and_raw_results, monkeypatch):
    study, run = study_with_run_and_raw_results
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _fake_details)

    first = deduplication.deduplicate_and_enrich(db_session, study.id)
    second = deduplication.deduplicate_and_enrich(db_session, study.id)

    assert first.newly_created == 3
    assert second.newly_created == 0  # nothing new to add
    assert second.unique_count == 3
    assert len(crud.list_videos(db_session, study.id)) == 3


def test_deduplicate_falls_back_when_metadata_missing_for_some_videos(
    db_session, study_with_run_and_raw_results, monkeypatch
):
    study, run = study_with_run_and_raw_results

    def partial_details(video_ids: list[str]) -> dict[str, dict]:
        full = _fake_details(video_ids)
        full.pop("video_C", None)  # simulate a deleted/private video
        return full

    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", partial_details)

    outcome = deduplication.deduplicate_and_enrich(db_session, study.id)

    assert outcome.metadata_unavailable == ["video_C"]
    video_c = crud.get_video_by_youtube_id(db_session, study.id, "video_C")
    assert video_c is not None
    assert video_c.title == "Train video"  # fell back to the raw search-result title
    assert video_c.metadata_json == {"metadata_unavailable": True}


def test_deduplicate_survives_metadata_api_failure(
    db_session, study_with_run_and_raw_results, monkeypatch
):
    study, run = study_with_run_and_raw_results

    def failing_details(video_ids: list[str]):
        raise YouTubeAPIError("simulated quota exceeded")

    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", failing_details)

    outcome = deduplication.deduplicate_and_enrich(db_session, study.id)

    # The workflow must not crash -- every video gets a fallback row.
    assert outcome.newly_created == 3
    assert set(outcome.metadata_unavailable) == {"video_A", "video_B", "video_C"}
    assert len(crud.list_videos(db_session, study.id)) == 3


def test_queries_per_video_and_best_rank(db_session, study_with_run_and_raw_results):
    study, run = study_with_run_and_raw_results
    raw_results = crud.list_search_results_raw(db_session, study.id)

    per_video = deduplication.queries_per_video(raw_results)
    assert len(per_video["video_A"]) == 2  # found by both queries
    assert len(per_video["video_B"]) == 1
    assert len(per_video["video_C"]) == 1

    best_rank = deduplication.best_rank_per_video(raw_results)
    assert best_rank["video_A"] == 1
    assert best_rank["video_B"] == 2
