"""Publication-date filtering for pilot/full search."""

from __future__ import annotations

import datetime

import pytest

from db import crud
from services import pilot_service, search_service
from services.youtube_api import SearchResultItem
from utils.constants import (
    PUBLICATION_FILTER_AFTER,
    PUBLICATION_FILTER_ALL_TIME,
    PUBLICATION_FILTER_BEFORE,
    PUBLICATION_FILTER_BETWEEN,
)
from utils.helpers import format_publication_period_label, publication_date_api_params
from utils.validators import validate_publication_date_filter

D1 = datetime.date(2020, 1, 1)
D2 = datetime.date(2025, 12, 31)


# ---------------------------------------------------------------------------
# publication_date_api_params
# ---------------------------------------------------------------------------


def test_all_time_sends_no_params():
    assert publication_date_api_params(PUBLICATION_FILTER_ALL_TIME, None, None) == {}


def test_after_sends_published_after_only():
    params = publication_date_api_params(PUBLICATION_FILTER_AFTER, D1, None)
    assert params == {"published_after": "2020-01-01T00:00:00Z"}


def test_before_sends_published_before_only():
    params = publication_date_api_params(PUBLICATION_FILTER_BEFORE, None, D2)
    assert params == {"published_before": "2025-12-31T23:59:59Z"}


def test_between_sends_both_params():
    params = publication_date_api_params(PUBLICATION_FILTER_BETWEEN, D1, D2)
    assert params == {
        "published_after": "2020-01-01T00:00:00Z",
        "published_before": "2025-12-31T23:59:59Z",
    }


def test_after_with_missing_date_sends_nothing():
    assert publication_date_api_params(PUBLICATION_FILTER_AFTER, None, None) == {}


def test_between_with_only_one_date_sends_nothing():
    assert publication_date_api_params(PUBLICATION_FILTER_BETWEEN, D1, None) == {}


# ---------------------------------------------------------------------------
# validate_publication_date_filter
# ---------------------------------------------------------------------------


def test_all_time_never_errors():
    assert validate_publication_date_filter(PUBLICATION_FILTER_ALL_TIME, None, None) == []


def test_after_requires_date():
    errors = validate_publication_date_filter(PUBLICATION_FILTER_AFTER, None, None)
    assert len(errors) == 1
    assert validate_publication_date_filter(PUBLICATION_FILTER_AFTER, D1, None) == []


def test_before_requires_date():
    errors = validate_publication_date_filter(PUBLICATION_FILTER_BEFORE, None, None)
    assert len(errors) == 1
    assert validate_publication_date_filter(PUBLICATION_FILTER_BEFORE, None, D2) == []


def test_between_requires_both_dates():
    errors = validate_publication_date_filter(PUBLICATION_FILTER_BETWEEN, D1, None)
    assert len(errors) == 1
    errors = validate_publication_date_filter(PUBLICATION_FILTER_BETWEEN, None, D2)
    assert len(errors) == 1


def test_between_rejects_start_after_end():
    errors = validate_publication_date_filter(PUBLICATION_FILTER_BETWEEN, D2, D1)
    assert len(errors) == 1
    assert "earlier than or equal to" in errors[0]


def test_between_allows_equal_start_and_end():
    assert validate_publication_date_filter(PUBLICATION_FILTER_BETWEEN, D1, D1) == []


def test_between_valid_range_has_no_errors():
    assert validate_publication_date_filter(PUBLICATION_FILTER_BETWEEN, D1, D2) == []


# ---------------------------------------------------------------------------
# format_publication_period_label
# ---------------------------------------------------------------------------


def test_label_all_time():
    assert format_publication_period_label(PUBLICATION_FILTER_ALL_TIME, None, None) == "All time"


def test_label_after():
    assert format_publication_period_label(PUBLICATION_FILTER_AFTER, D1, None) == "After 1 Jan 2020"


def test_label_before():
    assert format_publication_period_label(PUBLICATION_FILTER_BEFORE, None, D2) == "Before 31 Dec 2025"


def test_label_between():
    label = format_publication_period_label(PUBLICATION_FILTER_BETWEEN, D1, D2)
    assert label == "1 Jan 2020 - 31 Dec 2025"


# ---------------------------------------------------------------------------
# search_videos passes date params through to the API request
# ---------------------------------------------------------------------------


class _FakeYouTubeClient:
    def __init__(self):
        self.last_kwargs: dict | None = None

    def search(self):
        return self

    def list(self, **kwargs):
        self.last_kwargs = kwargs
        return self

    def execute(self):
        return {"items": []}


def test_search_videos_sends_published_after_and_before(monkeypatch):
    from services import youtube_api

    fake_client = _FakeYouTubeClient()
    monkeypatch.setattr(youtube_api, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(youtube_api, "_build_client", lambda: fake_client)

    youtube_api.search_videos(
        "test query", max_results=5,
        published_after="2020-01-01T00:00:00Z", published_before="2025-12-31T23:59:59Z",
    )

    assert fake_client.last_kwargs["publishedAfter"] == "2020-01-01T00:00:00Z"
    assert fake_client.last_kwargs["publishedBefore"] == "2025-12-31T23:59:59Z"


def test_search_videos_omits_date_params_when_not_given(monkeypatch):
    from services import youtube_api

    fake_client = _FakeYouTubeClient()
    monkeypatch.setattr(youtube_api, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(youtube_api, "_build_client", lambda: fake_client)

    youtube_api.search_videos("test query", max_results=5)

    assert "publishedAfter" not in fake_client.last_kwargs
    assert "publishedBefore" not in fake_client.last_kwargs


# ---------------------------------------------------------------------------
# Pilot/full search persistence and approval snapshot
# ---------------------------------------------------------------------------


@pytest.fixture()
def study_with_query(db_session):
    study = crud.create_study(db_session, name="Date filter test study")
    query = crud.create_search_query(db_session, study_id=study.id, query_text="how to catch a bus")
    return study, query


def _fake_search(query, max_results, order, region_code, relevance_language, published_after=None, published_before=None):
    return [
        SearchResultItem(
            video_id=f"vid_{i}", title=f"{query} result {i}", description="d", channel_title="Chan",
            published_at=datetime.datetime(2024, 1, 1), thumbnail_url=None,
            video_url=f"https://www.youtube.com/watch?v=vid_{i}", rank=i, raw={},
        )
        for i in range(1, max_results + 1)
    ]


def test_pilot_search_stores_and_uses_date_filter(db_session, study_with_query, monkeypatch):
    study, query = study_with_query
    captured = {}

    def spy_search(query_text, max_results, order, region_code, relevance_language, **kwargs):
        captured.update(kwargs)
        return _fake_search(query_text, max_results, order, region_code, relevance_language)

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", spy_search)

    outcome = pilot_service.run_pilot_search(
        db_session, study_id=study.id, queries=[query], results_per_query=3,
        search_order="relevance", reviewer_id=None,
        publication_filter_type=PUBLICATION_FILTER_AFTER, published_after=D1,
    )

    assert captured["published_after"] == "2020-01-01T00:00:00Z"

    run = crud.get_pilot_search_run(db_session, outcome.run_id)
    assert run.parameters_json["publication_filter_type"] == PUBLICATION_FILTER_AFTER
    assert run.parameters_json["published_after"] == "2020-01-01"
    assert run.parameters_json["published_before"] is None


def test_pilot_search_defaults_to_all_time_backward_compatible(db_session, study_with_query, monkeypatch):
    """Existing callers that don't pass a date filter behave exactly as before."""
    study, query = study_with_query
    captured = {}

    def spy_search(query_text, max_results, order, region_code, relevance_language, **kwargs):
        captured.update(kwargs)
        return _fake_search(query_text, max_results, order, region_code, relevance_language)

    monkeypatch.setattr(pilot_service.youtube_api, "search_videos", spy_search)

    outcome = pilot_service.run_pilot_search(
        db_session, study_id=study.id, queries=[query], results_per_query=3,
        search_order="relevance", reviewer_id=None,
    )

    assert captured == {}  # no publishedAfter/publishedBefore sent
    run = crud.get_pilot_search_run(db_session, outcome.run_id)
    assert run.parameters_json["publication_filter_type"] == PUBLICATION_FILTER_ALL_TIME


def test_full_search_stores_and_uses_date_filter(db_session, study_with_query, monkeypatch):
    study, query = study_with_query
    captured = {}

    def spy_search(query_text, max_results, order, region_code, relevance_language, **kwargs):
        captured.update(kwargs)
        return _fake_search(query_text, max_results, order, region_code, relevance_language)

    def fake_details(video_ids):
        return {}

    monkeypatch.setattr(search_service.youtube_api, "search_videos", spy_search)
    from services import deduplication
    monkeypatch.setattr(deduplication.youtube_api, "get_video_details", fake_details)

    outcome = search_service.run_full_search(
        db_session, study_id=study.id, queries=[query], results_per_query=3,
        search_order="relevance", approval_id=None,
        publication_filter_type=PUBLICATION_FILTER_BETWEEN, published_after=D1, published_before=D2,
    )

    assert captured["published_after"] == "2020-01-01T00:00:00Z"
    assert captured["published_before"] == "2025-12-31T23:59:59Z"

    run = crud.get_full_search_run(db_session, outcome.run_id)
    assert run.parameters_json["publication_filter_type"] == PUBLICATION_FILTER_BETWEEN
    assert run.parameters_json["published_after"] == "2020-01-01"
    assert run.parameters_json["published_before"] == "2025-12-31"


def test_approve_search_strategy_snapshots_date_filter(db_session, study_with_query):
    study, query = study_with_query

    pilot_service.approve_search_strategy(
        db_session, study_id=study.id, reviewer_id=None, results_per_query=10,
        search_order="relevance", publication_filter_type=PUBLICATION_FILTER_BEFORE,
        published_before=D2,
    )

    approval = crud.get_latest_approval(db_session, study.id)
    assert approval.parameters_json["publication_filter_type"] == PUBLICATION_FILTER_BEFORE
    assert approval.parameters_json["published_before"] == "2025-12-31"
    assert approval.parameters_json["published_after"] is None


def test_new_study_defaults_to_all_time(db_session):
    study = crud.create_study(db_session, name="Default filter study")
    assert study.publication_filter_type == PUBLICATION_FILTER_ALL_TIME
    assert study.published_after is None
    assert study.published_before is None


def test_study_publication_filter_can_be_updated(db_session):
    study = crud.create_study(db_session, name="Updatable study")
    updated = crud.update_study(
        db_session, study.id,
        publication_filter_type=PUBLICATION_FILTER_AFTER, published_after=D1,
    )
    assert updated.publication_filter_type == PUBLICATION_FILTER_AFTER
    assert updated.published_after == D1


def test_update_study_with_date_field_does_not_crash_audit_log(db_session):
    """Regression test: update_study logs its kwargs to the audit trail, and
    a raw `date` value there previously crashed the JSON serializer, which
    would have broken every pilot/full search run that syncs a date filter
    back onto the study."""
    study = crud.create_study(db_session, name="Audit log date study")
    crud.update_study(
        db_session, study.id,
        publication_filter_type=PUBLICATION_FILTER_BETWEEN,
        published_after=D1, published_before=D2,
    )
    events = crud.list_audit_log(db_session, study_id=study.id)
    updated_event = next(e for e in events if e.action_type == "study_updated")
    assert updated_event.details_json["published_after"] == "2020-01-01"
    assert updated_event.details_json["published_before"] == "2025-12-31"


# ---------------------------------------------------------------------------
# Additive column migration (existing local DBs without the new columns)
# ---------------------------------------------------------------------------


def test_column_migration_adds_missing_columns_to_existing_table(tmp_path):
    import sqlite3

    from db.database import _COLUMN_MIGRATIONS
    from sqlalchemy import create_engine

    db_path = tmp_path / "legacy.db"

    # Simulate a pre-feature database: a studies table without the 3 new columns.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE studies (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, "
        "search_status VARCHAR(50))"
    )
    conn.execute("INSERT INTO studies (id, name, search_status) VALUES (1, 'Legacy study', 'Draft')")
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        for table, columns in _COLUMN_MIGRATIONS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()

    with engine.connect() as conn:
        columns_after = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(studies)")}
        assert "publication_filter_type" in columns_after
        assert "published_after" in columns_after
        assert "published_before" in columns_after

        # Existing data survives the migration untouched.
        row = conn.exec_driver_sql("SELECT name, search_status, publication_filter_type FROM studies WHERE id=1").fetchone()
        assert row[0] == "Legacy study"
        assert row[1] == "Draft"
        assert row[2] == "all_time"  # DEFAULT applied by the ALTER TABLE
    engine.dispose()
