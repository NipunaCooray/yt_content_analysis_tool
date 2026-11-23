"""Daily search-quota tracking, repeat detection, and extending a pilot run
with more queries. YouTube API is mocked throughout."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from db.models import utcnow
from services import deduplication, pilot_service, search_runs, search_service
from services.youtube_api import SearchResultItem, YouTubeQuotaExceededError


def _fake_search(query, max_results, order, region_code, relevance_language, **_dates):
    tag = query.replace(" ", "_")
    return [
        SearchResultItem(
            video_id=f"{tag}_{i}", title=f"{query} {i}", description="", channel_title="C",
            published_at=datetime.datetime(2024, 1, 1), thumbnail_url=None,
            video_url=f"https://www.youtube.com/watch?v={tag}_{i}", rank=i, raw={},
        )
        for i in range(1, max_results + 1)
    ]


def _details(video_ids):
    return {
        vid: {"video_id": vid, "title": vid, "description": "", "channel_id": "c", "channel_title": "C",
              "published_at": None, "duration_seconds": 1, "view_count": 1, "like_count": 1, "tags": [],
              "thumbnail_url": None, "video_url": "", "raw": {}}
        for vid in video_ids
    }


@pytest.fixture()
def study(db_session):
    study = crud.create_study(db_session, name="Quota study")
    queries = [
        crud.create_search_query(db_session, study_id=study.id, query_text=f"query {n}")
        for n in range(1, 6)
    ]
    return study, queries


@pytest.fixture()
def calls(monkeypatch):
    """Record every search sent to the (fake) API."""
    sent: list[str] = []

    def search(query, **kwargs):
        sent.append(query)
        return _fake_search(query, **kwargs)

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", search)
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _details)
    return sent


def _pilot(db, study, queries, **kw):
    return pilot_service.run_pilot_search(
        db, study_id=study.id, queries=queries, results_per_query=kw.pop("rpq", 10),
        search_order="relevance", reviewer_id=None, **kw,
    )


# --- Extending a pilot run ---------------------------------------------------


def test_add_queries_searches_only_the_new_ones(db_session, study, calls):
    s, qs = study
    run_id = _pilot(db_session, s, qs[:3]).run_id
    calls.clear()

    outcome = pilot_service.add_queries_to_pilot_run(db_session, run_id, qs, reviewer_id=None)

    assert calls == ["query 4", "query 5"]  # the 3 already in the run were not re-searched
    assert outcome.queries_run == 2
    run = crud.get_pilot_search_run(db_session, run_id)
    assert sorted(run.parameters_json["query_ids"]) == sorted(q.id for q in qs)
    assert run.status == "completed"
    perf = pilot_service.compute_query_performance(db_session, run_id)
    assert len(perf) == 5  # the run's performance table now covers all queries


def test_add_queries_keeps_existing_relevance_ratings(db_session, study, calls):
    s, qs = study
    run_id = _pilot(db_session, s, qs[:1]).run_id
    first = crud.list_pilot_search_results(db_session, run_id)[0]
    crud.update_pilot_result_relevance(
        db_session, first.id, relevance_rating="Relevant", irrelevance_reason=None,
        reviewer_notes=None, reviewer_id=None,
    )

    pilot_service.add_queries_to_pilot_run(db_session, run_id, qs[1:2], reviewer_id=None)

    assert crud.get_pilot_search_result(db_session, first.id).relevance_rating == "Relevant"


def test_add_queries_retries_failed_ones_and_clears_the_error(db_session, study, monkeypatch, calls):
    s, qs = study

    def quota_on_query_2(query, **kwargs):
        calls.append(query)
        if query == "query 2":
            raise YouTubeQuotaExceededError("quota")
        return _fake_search(query, **kwargs)

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", quota_on_query_2)
    run_id = _pilot(db_session, s, qs[:3]).run_id
    run = crud.get_pilot_search_run(db_session, run_id)
    assert run.status == "partial" and "query 2" in run.error_message
    assert search_runs.failed_query_ids(db_session, run) == [qs[1].id]

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", lambda query, **kw: _fake_search(query, **kw))
    pilot_service.add_queries_to_pilot_run(db_session, run_id, qs[:3], reviewer_id=None)

    run = crud.get_pilot_search_run(db_session, run_id)
    assert run.status == "completed"
    assert run.error_message is None
    assert search_runs.failed_query_ids(db_session, run) == []


def test_add_queries_when_nothing_new_makes_no_calls(db_session, study, calls):
    s, qs = study
    run_id = _pilot(db_session, s, qs[:2]).run_id
    calls.clear()
    outcome = pilot_service.add_queries_to_pilot_run(db_session, run_id, qs[:2], reviewer_id=None)
    assert calls == [] and outcome.queries_run == 0


def test_add_queries_uses_the_runs_own_settings(db_session, study, monkeypatch):
    s, qs = study
    seen = []

    def search(query, **kwargs):
        seen.append(kwargs)
        return _fake_search(query, **kwargs)

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", search)
    run_id = _pilot(
        db_session, s, qs[:1], rpq=5,
        publication_filter_type="after", published_after=datetime.date(2022, 1, 1),
    ).run_id
    pilot_service.add_queries_to_pilot_run(db_session, run_id, qs[1:2], reviewer_id=None)

    assert seen[0] == seen[1]
    assert seen[1]["max_results"] == 5 and seen[1]["published_after"].startswith("2022-01-01")


# --- Quota day and usage -----------------------------------------------------


def test_quota_day_starts_at_midnight_pacific_standard_time():
    start, reset = search_runs.quota_day_bounds(datetime.datetime(2026, 11, 23, 3, 43))
    assert start == datetime.datetime(2026, 11, 22, 8, 0)
    assert reset == datetime.datetime(2026, 11, 23, 8, 0)


def test_quota_day_follows_daylight_saving():
    start, reset = search_runs.quota_day_bounds(datetime.datetime(2026, 7, 1, 12, 0))
    assert start == datetime.datetime(2026, 7, 1, 7, 0)  # midnight PDT = 07:00 UTC
    assert reset == datetime.datetime(2026, 7, 2, 7, 0)


def test_quota_usage_counts_both_kinds_of_run_across_studies(db_session, study, calls):
    s, qs = study
    other = crud.create_study(db_session, name="Other study")
    other_q = crud.create_search_query(db_session, study_id=other.id, query_text="other query")

    _pilot(db_session, s, qs[:3])                      # 3 searches
    _pilot(db_session, other, [other_q], rpq=20)       # 1
    search_service.run_full_search(                   # 2 queries x 2 pages (60 results) = 4
        db_session, study_id=s.id, queries=qs[:2], results_per_query=60,
        search_order="relevance", approval_id=None,
    )
    assert search_runs.quota_status(db_session).used == 8


def test_quota_usage_skips_quota_rejected_calls(db_session, study, monkeypatch):
    s, qs = study

    def always_quota(query, **kwargs):
        raise YouTubeQuotaExceededError("quota")

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", always_quota)
    _pilot(db_session, s, qs)
    assert search_runs.quota_status(db_session).used == 0


def test_quota_usage_counts_an_extension_on_the_day_it_ran(db_session, study, calls):
    s, qs = study
    run_id = _pilot(db_session, s, qs[:2]).run_id
    # Pretend the original run happened yesterday.
    run = crud.get_pilot_search_run(db_session, run_id)
    yesterday = (utcnow() - datetime.timedelta(days=2)).isoformat()
    params = dict(run.parameters_json)
    params["search_batches"] = [dict(params["search_batches"][0], at=yesterday)]
    crud.update_pilot_search_run(
        db_session, run_id, parameters_json=params,
        started_at=utcnow() - datetime.timedelta(days=2),
    )

    pilot_service.add_queries_to_pilot_run(db_session, run_id, qs[2:5], reviewer_id=None)
    assert search_runs.quota_status(db_session).used == 3


def test_quota_usage_for_runs_recorded_before_batches(db_session, study):
    s, qs = study
    crud.create_pilot_search_run(
        db_session, study_id=s.id, results_per_query=10, search_order="relevance",
        status="completed", started_at=utcnow(), completed_at=utcnow(),
        parameters_json={"query_ids": [q.id for q in qs]},
    )
    assert search_runs.quota_status(db_session).used == 5


def test_quota_limit_can_be_raised_by_setting(monkeypatch, db_session):
    monkeypatch.setenv("YOUTUBE_SEARCH_QUOTA_PER_DAY", "1000")
    assert search_runs.quota_status(db_session).limit == 1000


# --- Repeat detection --------------------------------------------------------


def _settings(rpq=10, **kw):
    return search_runs.SearchSettings(results_per_query=rpq, search_order="relevance", **kw)


def test_pilot_repeats_are_same_settings_today(db_session, study, calls):
    s, qs = study
    run_id = _pilot(db_session, s, qs[:2]).run_id
    ids = [q.id for q in qs[:3]]

    assert search_runs.find_repeats(db_session, s.id, search_runs.PILOT, ids, _settings()) == {
        qs[0].id: run_id, qs[1].id: run_id,
    }
    # Different settings return different results: not a repeat.
    assert search_runs.find_repeats(db_session, s.id, search_runs.PILOT, ids, _settings(rpq=20)) == {}
    # Tomorrow it's a legitimate re-check, not a repeat.
    tomorrow = utcnow() + datetime.timedelta(days=1)
    assert search_runs.find_repeats(db_session, s.id, search_runs.PILOT, ids, _settings(), now=tomorrow) == {}


def test_pilot_repeats_ignore_failed_queries(db_session, study, monkeypatch):
    s, qs = study

    def quota(query, **kwargs):
        raise YouTubeQuotaExceededError("quota")

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", quota)
    _pilot(db_session, s, qs[:2])
    assert search_runs.find_repeats(db_session, s.id, search_runs.PILOT, [qs[0].id], _settings()) == {}


def test_full_search_repeats_span_days(db_session, study, calls):
    s, qs = study
    run_id = search_service.run_full_search(
        db_session, study_id=s.id, queries=qs[:1], results_per_query=10,
        search_order="relevance", approval_id=None,
    ).run_id
    next_week = utcnow() + datetime.timedelta(days=7)
    assert search_runs.find_repeats(
        db_session, s.id, search_runs.FULL, [qs[0].id, qs[1].id], _settings(), now=next_week
    ) == {qs[0].id: run_id}


# --- Failed queries (full search retry button) ------------------------------


def test_full_search_records_failed_query_ids(db_session, study, monkeypatch):
    s, qs = study

    def quota_after_two(query, **kwargs):
        if query in ("query 3", "query 4", "query 5"):
            raise YouTubeQuotaExceededError("quota")
        return _fake_search(query, **kwargs)

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", quota_after_two)
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _details)
    outcome = search_service.run_full_search(
        db_session, study_id=s.id, queries=qs, results_per_query=10,
        search_order="relevance", approval_id=None,
    )
    run = crud.get_full_search_run(db_session, outcome.run_id)
    assert search_runs.failed_query_ids(db_session, run) == [q.id for q in qs[2:]]
    assert outcome.queries_failed == 3


def test_failed_query_ids_for_runs_recorded_before_bookkeeping(db_session, study, calls):
    s, qs = study
    run_id = search_service.run_full_search(
        db_session, study_id=s.id, queries=qs[:2], results_per_query=5,
        search_order="relevance", approval_id=None,
    ).run_id
    # Rewrite as an old-style partial run: 3 queries listed, only 2 with results.
    crud.update_full_search_run(
        db_session, run_id, status="partial",
        parameters_json={"results_per_query": 5, "search_order": "relevance",
                         "query_ids": [q.id for q in qs[:3]]},
    )
    run = crud.get_full_search_run(db_session, run_id)
    assert search_runs.failed_query_ids(db_session, run) == [qs[2].id]
