"""Search-run durability (PostgreSQL migration section 14-15): a run row
exists as soon as it starts, results are committed incrementally per query
(not batched until the end), and the run's status reflects what actually
happened -- completed / partial / failed."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import pilot_service, search_service
from services.youtube_api import SearchResultItem, YouTubeAPIError
from utils.constants import RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_PARTIAL


@pytest.fixture()
def study_with_two_queries(db_session):
    study = crud.create_study(db_session, name="Durability test study")
    q1 = crud.create_search_query(db_session, study_id=study.id, query_text="how to catch a bus")
    q2 = crud.create_search_query(db_session, study_id=study.id, query_text="how to use trains")
    return study, [q1, q2]


def _fake_search(query, max_results, order, region_code, relevance_language, **kwargs):
    return [
        SearchResultItem(
            video_id=f"vid_{query.split()[-1]}_{i}", title=f"{query} {i}", description="d",
            channel_title="Chan", published_at=datetime.datetime(2024, 1, 1), thumbnail_url=None,
            video_url=f"https://www.youtube.com/watch?v=vid_{i}", rank=i, raw={},
        )
        for i in range(1, max_results + 1)
    ]


# ---------------------------------------------------------------------------
# Pilot search
# ---------------------------------------------------------------------------


def test_pilot_run_status_completed_when_all_queries_succeed(db_session, study_with_two_queries, monkeypatch):
    study, queries = study_with_two_queries
    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", _fake_search)

    outcome = pilot_service.run_pilot_search(
        db_session, study_id=study.id, queries=queries, results_per_query=3,
        search_order="relevance", reviewer_id=None,
    )

    run = crud.get_pilot_search_run(db_session, outcome.run_id)
    assert run.status == RUN_STATUS_COMPLETED
    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.error_message is None


def test_pilot_run_status_partial_when_one_query_fails(db_session, study_with_two_queries, monkeypatch):
    study, queries = study_with_two_queries

    def flaky(query, max_results, order, region_code, relevance_language, **kwargs):
        if "bus" in query:
            raise YouTubeAPIError("simulated failure")
        return _fake_search(query, max_results, order, region_code, relevance_language)

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", flaky)

    outcome = pilot_service.run_pilot_search(
        db_session, study_id=study.id, queries=queries, results_per_query=3,
        search_order="relevance", reviewer_id=None,
    )

    run = crud.get_pilot_search_run(db_session, outcome.run_id)
    assert run.status == RUN_STATUS_PARTIAL
    assert "bus" in run.error_message
    # The query that succeeded is still saved despite the other failing.
    assert outcome.results_saved == 3


def test_pilot_run_status_failed_when_all_queries_fail(db_session, study_with_two_queries, monkeypatch):
    study, queries = study_with_two_queries

    def always_fails(query, max_results, order, region_code, relevance_language, **kwargs):
        raise YouTubeAPIError("simulated total failure")

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", always_fails)

    outcome = pilot_service.run_pilot_search(
        db_session, study_id=study.id, queries=queries, results_per_query=3,
        search_order="relevance", reviewer_id=None,
    )

    run = crud.get_pilot_search_run(db_session, outcome.run_id)
    assert run.status == RUN_STATUS_FAILED
    assert outcome.results_saved == 0


def test_pilot_results_are_committed_incrementally_per_query(db_session, study_with_two_queries, monkeypatch):
    """If the second query blows up with an unexpected (non-API) error, the
    first query's results must already be durably committed, not lost with
    an uncommitted transaction."""
    study, queries = study_with_two_queries
    call_count = {"n": 0}

    def crash_on_second_call(query, max_results, order, region_code, relevance_language, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated unhandled crash (e.g. process killed)")
        return _fake_search(query, max_results, order, region_code, relevance_language)

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", crash_on_second_call)

    with pytest.raises(RuntimeError):
        pilot_service.run_pilot_search(
            db_session, study_id=study.id, queries=queries, results_per_query=3,
            search_order="relevance", reviewer_id=None,
        )

    # The run row and the first query's results survive even though the
    # function itself never reached its normal return.
    runs = crud.list_pilot_search_runs(db_session, study.id)
    assert len(runs) == 1
    results = crud.list_pilot_search_results(db_session, runs[0].id)
    assert len(results) == 3  # first query's results, committed before the crash


# ---------------------------------------------------------------------------
# Full search
# ---------------------------------------------------------------------------


def test_full_search_run_status_completed(db_session, study_with_two_queries, monkeypatch):
    study, queries = study_with_two_queries
    monkeypatch.setattr(search_service.youtube_api, "search_videos", _fake_search)

    def fake_details(video_ids):
        return {}

    from services import deduplication
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", fake_details)

    outcome = search_service.run_full_search(
        db_session, study_id=study.id, queries=queries, results_per_query=3,
        search_order="relevance", approval_id=None,
    )

    run = crud.get_full_search_run(db_session, outcome.run_id)
    assert run.status == RUN_STATUS_COMPLETED
    assert run.started_at is not None
    assert run.completed_at is not None


def test_full_search_does_not_mark_study_complete_when_run_fails(db_session, study_with_two_queries, monkeypatch):
    study, queries = study_with_two_queries

    def always_fails(query, max_results, order, region_code, relevance_language, **kwargs):
        raise YouTubeAPIError("simulated total failure")

    monkeypatch.setattr(search_service.youtube_api, "search_videos", always_fails)

    search_service.run_full_search(
        db_session, study_id=study.id, queries=queries, results_per_query=3,
        search_order="relevance", approval_id=None,
    )

    updated_study = crud.get_study(db_session, study.id)
    assert updated_study.search_status != "Full search completed"


def test_full_search_results_committed_incrementally(db_session, study_with_two_queries, monkeypatch):
    study, queries = study_with_two_queries
    call_count = {"n": 0}

    def crash_on_second_call(query, max_results, order, region_code, relevance_language, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated unhandled crash")
        return _fake_search(query, max_results, order, region_code, relevance_language)

    monkeypatch.setattr(search_service.youtube_api, "search_videos", crash_on_second_call)

    with pytest.raises(RuntimeError):
        search_service.run_full_search(
            db_session, study_id=study.id, queries=queries, results_per_query=3,
            search_order="relevance", approval_id=None,
        )

    runs = crud.list_full_search_runs(db_session, study.id)
    assert len(runs) == 1
    raw = crud.list_search_results_raw(db_session, study.id, runs[0].id)
    assert len(raw) == 3  # first query's raw results survived the crash
