"""Page-level checks for the quota counter, repeat warning, adding queries to
an existing pilot run, and the full-search 'retry failed queries' button.
Backed by a temp SQLite database; the YouTube API is mocked."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from db import crud
from services import deduplication, pilot_service, search_runs, search_service
from services.youtube_api import SearchResultItem, YouTubeQuotaExceededError

ROOT = Path(__file__).resolve().parent.parent
PILOT_PAGE = str(ROOT / "pages" / "04_pilot_search.py")
FULL_PAGE = str(ROOT / "pages" / "05_search_results.py")


def _fake_search(query, max_results=10, **_):
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
def seeded(monkeypatch, tmp_path):
    """Temp DB with 3 active queries; a pilot run today covering the first 2;
    an approved strategy; and a full search where the third hit the quota."""
    import db.database as database

    saved = (database._engine, database._backend, database._SessionLocal, database._schema_ready)
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_backend", None)
    monkeypatch.setattr(database, "_SessionLocal", None)
    monkeypatch.setattr(database, "_schema_ready", False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "quota.db"))
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key-not-used")
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", _details)

    def quota_on_third(query, **kwargs):
        if query == "query 3":
            raise YouTubeQuotaExceededError("quota")
        return _fake_search(query, **kwargs)

    monkeypatch.setattr(search_runs.youtube_api, "search_videos", quota_on_third)

    database.init_db()
    db = database.get_session()
    study = crud.create_study(db, name="Quota page study")
    crud.create_reviewer(db, name="Rev", initials="RV")
    qs = [crud.create_search_query(db, study_id=study.id, query_text=f"query {n}") for n in (1, 2, 3)]
    pilot_run = pilot_service.run_pilot_search(
        db, study_id=study.id, queries=qs[:2], results_per_query=10,
        search_order="relevance", reviewer_id=None,
    ).run_id
    pilot_service.approve_search_strategy(
        db, study_id=study.id, reviewer_id=None, results_per_query=10, search_order="relevance",
    )
    search_service.run_full_search(
        db, study_id=study.id, queries=qs, results_per_query=10,
        search_order="relevance", approval_id=None,
    )
    ids = [q.id for q in qs]
    db.close()

    # Searches after seeding succeed.
    monkeypatch.setattr(search_runs.youtube_api, "search_videos", lambda query, **kw: _fake_search(query, **kw))

    yield {"query_ids": ids, "pilot_run_id": pilot_run}

    (database._engine, database._backend, database._SessionLocal, database._schema_ready) = saved


def _app(path):
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(path, default_timeout=60)


def _ok(at):
    assert not at.exception, [str(e) for e in at.exception]


def test_pilot_page_shows_quota_and_removes_repeats(seeded):
    at = _app(PILOT_PAGE)
    at.run()
    _ok(at)
    # 2 pilot searches + 2 successful full searches today (the quota-failed one isn't counted).
    assert any("searches used today: ~4 of 100" in c.value for c in at.caption)
    assert any("already searched today" in w.value for w in at.warning)

    next(b for b in at.button if b.label.startswith("Remove repeated")).click().run()
    _ok(at)
    q1, q2, q3 = seeded["query_ids"]
    assert at.multiselect(key="pilot_new_selection").value == [q3]
    assert not any("already searched today" in w.value for w in at.warning)


def test_pilot_page_adds_only_new_queries_to_an_existing_run(seeded):
    at = _app(PILOT_PAGE)
    at.session_state["pilot_run_mode"] = "Add queries to an existing run"
    at.run()
    _ok(at)
    run_id = seeded["pilot_run_id"]
    q1, q2, q3 = seeded["query_ids"]
    selection = at.multiselect(key=f"pilot_add_selection_{run_id}")
    assert selection.options == ["query 3"]  # queries already in the run aren't offered

    next(b for b in at.button if b.label == "Add to run").click().run()
    _ok(at)

    import db.database as database

    db = database.get_session()
    run = crud.get_pilot_search_run(db, run_id)
    assert sorted(run.parameters_json["query_ids"]) == [q1, q2, q3]
    assert len(crud.list_pilot_search_results(db, run_id)) == 30
    db.close()


def test_full_search_page_selects_only_failed_queries(seeded):
    at = _app(FULL_PAGE)
    at.run()
    _ok(at)
    retry = next(b for b in at.button if b.label.startswith("Select only the 1 failed"))
    retry.click().run()
    _ok(at)
    assert at.multiselect(key="full_search_selection").value == [seeded["query_ids"][2]]
    # The remaining selection is not a repeat, so no repeat warning.
    assert not any("earlier full search run" in w.value for w in at.warning)
