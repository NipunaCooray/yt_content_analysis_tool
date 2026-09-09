"""Phase 2: YouTube metadata normalisation helpers (no live API calls)."""

from __future__ import annotations

from utils.helpers import parse_iso8601_duration, parse_youtube_datetime, thumbnail_url_from_snippet


def test_parse_iso8601_duration_minutes_seconds():
    assert parse_iso8601_duration("PT4M13S") == 4 * 60 + 13


def test_parse_iso8601_duration_hours():
    assert parse_iso8601_duration("PT1H2M3S") == 3600 + 120 + 3


def test_parse_iso8601_duration_none():
    assert parse_iso8601_duration(None) is None
    assert parse_iso8601_duration("") is None


def test_parse_youtube_datetime():
    dt = parse_youtube_datetime("2024-03-15T10:30:00Z")
    assert dt is not None
    assert dt.year == 2024 and dt.month == 3 and dt.day == 15


def test_thumbnail_url_prefers_medium():
    snippet = {
        "thumbnails": {
            "default": {"url": "default.jpg"},
            "medium": {"url": "medium.jpg"},
            "high": {"url": "high.jpg"},
        }
    }
    assert thumbnail_url_from_snippet(snippet) == "medium.jpg"


def test_thumbnail_url_falls_back_to_default():
    snippet = {"thumbnails": {"default": {"url": "default.jpg"}}}
    assert thumbnail_url_from_snippet(snippet) == "default.jpg"


def test_thumbnail_url_missing():
    assert thumbnail_url_from_snippet({}) is None
