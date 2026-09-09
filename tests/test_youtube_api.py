"""Phase 2/3: YouTube metadata normalisation and search-pagination helpers
(no live API calls -- the client is mocked)."""

from __future__ import annotations

from services import youtube_api
from services.youtube_api import estimate_search_calls
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


def test_estimate_search_calls_single_page():
    assert estimate_search_calls(num_queries=3, max_results=10) == 3


def test_estimate_search_calls_multiple_pages():
    # 120 results needs ceil(120/50) = 3 pages per query.
    assert estimate_search_calls(num_queries=2, max_results=120) == 6


def test_estimate_search_calls_exact_page_boundary():
    assert estimate_search_calls(num_queries=1, max_results=50) == 1
    assert estimate_search_calls(num_queries=1, max_results=51) == 2


class _FakeYouTubeClient:
    """Stands in for the googleapiclient discovery resource."""

    def __init__(self, pages: list[tuple[list[dict], str | None]]):
        self._pages = pages
        self.call_count = 0
        self.last_kwargs: dict | None = None

    def search(self):
        return self

    def list(self, **kwargs):
        self.last_kwargs = kwargs
        return self

    def execute(self):
        items, next_token = self._pages[self.call_count]
        self.call_count += 1
        response = {"items": items}
        if next_token:
            response["nextPageToken"] = next_token
        return response


def _snippet_item(video_id: str) -> dict:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": f"Title {video_id}",
            "description": "desc",
            "channelTitle": "Chan",
            "publishedAt": "2024-01-01T00:00:00Z",
            "thumbnails": {"medium": {"url": "https://example.com/t.jpg"}},
        },
    }


def test_search_videos_paginates_beyond_50_results(monkeypatch):
    page1_items = [_snippet_item(f"v{i}") for i in range(50)]
    page2_items = [_snippet_item(f"v{i}") for i in range(50, 70)]
    fake_client = _FakeYouTubeClient([(page1_items, "TOKEN_2"), (page2_items, None)])

    monkeypatch.setattr(youtube_api, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(youtube_api, "_build_client", lambda: fake_client)

    results = youtube_api.search_videos("test query", max_results=70)

    assert len(results) == 70
    assert fake_client.call_count == 2  # one call per 50-result page
    assert results[0].rank == 1
    assert results[-1].rank == 70
    assert results[0].video_id == "v0"
    assert results[-1].video_id == "v69"


def test_search_videos_stops_when_api_has_no_more_pages(monkeypatch):
    # API returns fewer results than requested and no nextPageToken.
    page1_items = [_snippet_item(f"v{i}") for i in range(5)]
    fake_client = _FakeYouTubeClient([(page1_items, None)])

    monkeypatch.setattr(youtube_api, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(youtube_api, "_build_client", lambda: fake_client)

    results = youtube_api.search_videos("test query", max_results=50)

    assert len(results) == 5
    assert fake_client.call_count == 1
