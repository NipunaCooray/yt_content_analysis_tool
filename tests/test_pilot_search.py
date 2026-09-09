"""Phase 2: pilot-search persistence and relevance-rate calculations.

The YouTube API is mocked throughout -- no test depends on a live API key
(handover doc section 36).
"""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import pilot_service
from services.youtube_api import SearchResultItem


def _fake_search_results(query_text: str, count: int) -> list[SearchResultItem]:
    return [
        SearchResultItem(
            video_id=f"vid_{query_text[:3]}_{i}",
            title=f"{query_text} result {i}",
            description="A test video description.",
            channel_title="Test Channel",
            published_at=datetime.datetime(2024, 1, 1),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url=f"https://www.youtube.com/watch?v=vid_{query_text[:3]}_{i}",
            rank=i,
            raw={"id": {"videoId": f"vid_{query_text[:3]}_{i}"}},
        )
        for i in range(1, count + 1)
    ]


@pytest.fixture()
def study_with_queries(db_session):
    study = crud.create_study(db_session, name="Test study")
    q1 = crud.create_search_query(db_session, study_id=study.id, query_text="how to catch a bus")
    q2 = crud.create_search_query(db_session, study_id=study.id, query_text="how to use trains")
    return study, [q1, q2]


def test_run_pilot_search_persists_results(db_session, study_with_queries, monkeypatch):
    study, queries = study_with_queries

    monkeypatch.setattr(
        pilot_service.youtube_api,
        "search_videos",
        lambda query, max_results, order, region_code, relevance_language: _fake_search_results(
            query, max_results
        ),
    )

    outcome = pilot_service.run_pilot_search(
        db_session,
        study_id=study.id,
        queries=queries,
        results_per_query=10,
        search_order="relevance",
        reviewer_id=None,
    )

    assert outcome.results_saved == 20
    assert outcome.errors == []

    results = crud.list_pilot_search_results(db_session, outcome.run_id)
    assert len(results) == 20
    assert all(r.relevance_rating == "Not yet reviewed" for r in results)

    # A second run must not overwrite the first (pilot history is an audit trail).
    outcome2 = pilot_service.run_pilot_search(
        db_session,
        study_id=study.id,
        queries=queries,
        results_per_query=5,
        search_order="relevance",
        reviewer_id=None,
    )
    assert outcome2.run_id != outcome.run_id
    assert len(crud.list_pilot_search_results(db_session, outcome.run_id)) == 20
    assert len(crud.list_pilot_search_results(db_session, outcome2.run_id)) == 10


def test_run_pilot_search_continues_after_one_query_fails(db_session, study_with_queries, monkeypatch):
    study, queries = study_with_queries
    from services.youtube_api import YouTubeAPIError

    def flaky_search(query, max_results, order, region_code, relevance_language):
        if "bus" in query:
            raise YouTubeAPIError("simulated failure")
        return _fake_search_results(query, max_results)

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", flaky_search)

    outcome = pilot_service.run_pilot_search(
        db_session,
        study_id=study.id,
        queries=queries,
        results_per_query=10,
        search_order="relevance",
        reviewer_id=None,
    )

    assert len(outcome.errors) == 1
    assert outcome.results_saved == 10  # only the working query's results were saved


def test_compute_query_performance_matches_spec_example(db_session, study_with_queries, monkeypatch):
    """Handover doc section 37: reviewed=10, relevant=7, potential=2, irrelevant=1
    -> strict_relevance_rate=70%, broad_relevance_rate=90%."""
    study, queries = study_with_queries
    query = queries[0]

    monkeypatch.setattr(
        pilot_service.youtube_api,
        "search_videos",
        lambda query, max_results, order, region_code, relevance_language: _fake_search_results(
            query, max_results
        ),
    )
    outcome = pilot_service.run_pilot_search(
        db_session,
        study_id=study.id,
        queries=[query],
        results_per_query=10,
        search_order="relevance",
        reviewer_id=None,
    )

    results = crud.list_pilot_search_results(db_session, outcome.run_id)
    ratings = ["Relevant"] * 7 + ["Potentially relevant"] * 2 + ["Irrelevant"]
    for result, rating in zip(results, ratings):
        crud.update_pilot_result_relevance(
            db_session,
            result.id,
            relevance_rating=rating,
            irrelevance_reason="Other" if rating == "Irrelevant" else None,
            reviewer_notes=None,
            reviewer_id=None,
        )

    performance = pilot_service.compute_query_performance(db_session, outcome.run_id)
    assert len(performance) == 1
    p = performance[0]
    assert p.reviewed == 10
    assert p.relevant == 7
    assert p.potentially_relevant == 2
    assert p.irrelevant == 1
    assert p.strict_relevance_rate == 70.0
    assert p.broad_relevance_rate == 90.0


def test_diagnostics_duplicates(db_session, study_with_queries, monkeypatch):
    study, queries = study_with_queries

    # Both queries "discover" the same single video id.
    def same_video_search(query, max_results, order, region_code, relevance_language):
        return [
            SearchResultItem(
                video_id="shared_video",
                title="Shared video",
                description="",
                channel_title="Channel",
                published_at=None,
                thumbnail_url=None,
                video_url="https://www.youtube.com/watch?v=shared_video",
                rank=1,
                raw={},
            )
        ]

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", same_video_search)

    outcome = pilot_service.run_pilot_search(
        db_session,
        study_id=study.id,
        queries=queries,
        results_per_query=1,
        search_order="relevance",
        reviewer_id=None,
    )

    diagnostics = pilot_service.compute_diagnostics(db_session, outcome.run_id)
    assert diagnostics.unique_videos == 1
    assert diagnostics.duplicate_video_ids == {"shared_video": 2}


def test_approve_search_strategy_snapshots_active_queries(db_session, study_with_queries):
    study, queries = study_with_queries
    crud.set_query_active(db_session, queries[1].id, False)  # deactivate one query

    pilot_service.approve_search_strategy(
        db_session,
        study_id=study.id,
        reviewer_id=None,
        results_per_query=10,
        search_order="relevance",
        notes="Approved after two pilot rounds.",
    )

    approvals = crud.list_search_strategy_approvals(db_session, study.id)
    assert len(approvals) == 1
    assert len(approvals[0].query_snapshot_json) == 1  # only the active query
    assert approvals[0].query_snapshot_json[0]["query_text"] == queries[0].query_text

    updated_study = crud.get_study(db_session, study.id)
    assert updated_study.search_status == "Ready for full search"
