"""Phase 3: full-search execution, raw-result preservation across runs, and
automatic deduplication. YouTube API is mocked throughout."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import deduplication, search_service
from services.youtube_api import SearchResultItem, YouTubeAPIError


@pytest.fixture()
def study_with_queries(db_session):
    study = crud.create_study(db_session, name="Full search test study")
    q1 = crud.create_search_query(db_session, study_id=study.id, query_text="how to catch a bus")
    q2 = crud.create_search_query(db_session, study_id=study.id, query_text="how to use trains")
    return study, [q1, q2]


def _fake_search(query, max_results, order, region_code, relevance_language):
    # Use the last word of the query (e.g. "bus"/"trains") so ids don't
    # collide across queries that happen to share a prefix ("how to...").
    query_tag = query.split()[-1]
    return [
        SearchResultItem(
            video_id=f"vid_{query_tag}_{i}",
            title=f"{query} result {i}",
            description="desc",
            channel_title="Chan",
            published_at=datetime.datetime(2024, 1, 1),
            thumbnail_url="https://example.com/t.jpg",
            video_url=f"https://www.youtube.com/watch?v=vid_{query_tag}_{i}",
            rank=i,
            raw={},
        )
        for i in range(1, max_results + 1)
    ]


def _fake_details(video_ids):
    return {
        vid: {
            "video_id": vid,
            "title": f"{vid} enriched",
            "description": "",
            "channel_id": "c1",
            "channel_title": "Chan",
            "published_at": datetime.datetime(2024, 1, 1),
            "duration_seconds": 120,
            "view_count": 10,
            "like_count": 1,
            "tags": [],
            "thumbnail_url": None,
            "video_url": f"https://www.youtube.com/watch?v={vid}",
            "raw": {},
        }
        for vid in video_ids
    }


def test_run_full_search_persists_raw_results_and_dedupes(
    db_session, study_with_queries, monkeypatch
):
    study, queries = study_with_queries
    monkeypatch.setattr(search_service.youtube_api, "search_videos", _fake_search)
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _fake_details)

    outcome = search_service.run_full_search(
        db_session,
        study_id=study.id,
        queries=queries,
        results_per_query=5,
        search_order="relevance",
        approval_id=None,
    )

    assert outcome.raw_results_saved == 10
    assert outcome.errors == []
    assert outcome.dedup.unique_count == 10  # distinct ids per query prefix, no overlap
    assert outcome.dedup.newly_created == 10

    raw = crud.list_search_results_raw(db_session, study.id)
    assert len(raw) == 10
    videos = crud.list_videos(db_session, study.id)
    assert len(videos) == 10

    updated_study = crud.get_study(db_session, study.id)
    assert updated_study.search_status == "Full search completed"


def test_run_full_search_preserves_history_across_runs(
    db_session, study_with_queries, monkeypatch
):
    study, queries = study_with_queries
    monkeypatch.setattr(search_service.youtube_api, "search_videos", _fake_search)
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _fake_details)

    outcome1 = search_service.run_full_search(
        db_session, study_id=study.id, queries=queries, results_per_query=5,
        search_order="relevance", approval_id=None,
    )
    outcome2 = search_service.run_full_search(
        db_session, study_id=study.id, queries=queries, results_per_query=5,
        search_order="relevance", approval_id=None,
    )

    assert outcome1.run_id != outcome2.run_id
    # Raw results from run 1 must still exist -- never overwritten.
    all_raw = crud.list_search_results_raw(db_session, study.id)
    assert len(all_raw) == 20  # 10 + 10, both runs preserved

    run1_raw = crud.list_search_results_raw(db_session, study.id, outcome1.run_id)
    assert len(run1_raw) == 10

    # But the video master list stays deduplicated -- same video_ids both runs.
    videos = crud.list_videos(db_session, study.id)
    assert len(videos) == 10
    assert outcome2.dedup.newly_created == 0


def test_run_full_search_continues_after_one_query_fails(
    db_session, study_with_queries, monkeypatch
):
    study, queries = study_with_queries

    def flaky_search(query, max_results, order, region_code, relevance_language):
        if "bus" in query:
            raise YouTubeAPIError("simulated failure")
        return _fake_search(query, max_results, order, region_code, relevance_language)

    monkeypatch.setattr(search_service.youtube_api, "search_videos", flaky_search)
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _fake_details)

    outcome = search_service.run_full_search(
        db_session, study_id=study.id, queries=queries, results_per_query=5,
        search_order="relevance", approval_id=None,
    )

    assert len(outcome.errors) == 1
    assert outcome.raw_results_saved == 5  # only the working query's results
