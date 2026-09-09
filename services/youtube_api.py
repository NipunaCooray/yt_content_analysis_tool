"""
Thin wrapper around the YouTube Data API v3.

Responsible only for talking to the API and normalising responses into
plain dicts -- it knows nothing about pilot runs, studies, etc. See
handover doc section 10.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from utils.helpers import parse_iso8601_duration, parse_youtube_datetime, thumbnail_url_from_snippet, video_url
from utils.logging import get_logger

load_dotenv()
logger = get_logger(__name__)


class YouTubeAPIError(Exception):
    """Raised for any recoverable YouTube API failure, with a UI-friendly message."""


class YouTubeAPIKeyMissingError(YouTubeAPIError):
    pass


class YouTubeQuotaExceededError(YouTubeAPIError):
    pass


@dataclass
class SearchResultItem:
    video_id: str
    title: str
    description: str
    channel_title: str
    published_at: Any
    thumbnail_url: str | None
    video_url: str
    rank: int
    raw: dict = field(default_factory=dict)


def get_api_key() -> str | None:
    return os.getenv("YOUTUBE_API_KEY") or None


def api_key_configured() -> bool:
    return bool(get_api_key())


def _build_client():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise YouTubeAPIError(
            "google-api-python-client is not installed. Run: pip install -r requirements.txt"
        ) from exc

    api_key = get_api_key()
    if not api_key:
        raise YouTubeAPIKeyMissingError(
            "No YouTube API key configured. Add YOUTUBE_API_KEY to your .env file "
            "(see .env.example) and restart the app."
        )
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _translate_http_error(exc: Exception) -> YouTubeAPIError:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:  # pragma: no cover
        return YouTubeAPIError(str(exc))

    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", None)
        reason = ""
        try:
            reason = exc.error_details[0].get("reason", "") if exc.error_details else ""
        except Exception:
            reason = ""
        if status == 403 and ("quota" in str(exc).lower() or reason == "quotaExceeded"):
            return YouTubeQuotaExceededError(
                "YouTube API quota exceeded for today. Try again after the daily quota "
                "resets (midnight Pacific time), or use a different API key."
            )
        if status == 400:
            return YouTubeAPIError(f"Invalid YouTube API request: {exc}")
        if status == 403:
            return YouTubeAPIError(
                "YouTube API request was refused (403). Check that your API key is valid "
                "and that the YouTube Data API v3 is enabled for it."
            )
        return YouTubeAPIError(f"YouTube API error ({status}): {exc}")
    return YouTubeAPIError(f"Unexpected error calling YouTube API: {exc}")


def search_videos(
    query: str,
    max_results: int = 10,
    order: str = "relevance",
    region_code: str | None = "AU",
    relevance_language: str | None = "en",
) -> list[SearchResultItem]:
    """Run a single search.list call and return normalised results, ranked."""
    client = _build_client()
    try:
        request_kwargs: dict[str, Any] = dict(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
            order=order,
        )
        if region_code:
            request_kwargs["regionCode"] = region_code
        if relevance_language:
            request_kwargs["relevanceLanguage"] = relevance_language

        response = client.search().list(**request_kwargs).execute()
    except Exception as exc:  # noqa: BLE001 - normalised below
        raise _translate_http_error(exc) from exc

    items = response.get("items", [])
    results: list[SearchResultItem] = []
    for rank, item in enumerate(items, start=1):
        vid = item.get("id", {}).get("videoId")
        if not vid:
            continue
        snippet = item.get("snippet", {})
        results.append(
            SearchResultItem(
                video_id=vid,
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                channel_title=snippet.get("channelTitle", ""),
                published_at=parse_youtube_datetime(snippet.get("publishedAt")),
                thumbnail_url=thumbnail_url_from_snippet(snippet),
                video_url=video_url(vid),
                rank=rank,
                raw=item,
            )
        )
    if not results:
        logger.info("Search for query %r returned no results.", query)
    return results


def get_video_details(video_ids: list[str]) -> dict[str, dict]:
    """Batch-fetch metadata for up to 50 video IDs at a time via videos.list."""
    if not video_ids:
        return {}
    client = _build_client()
    details: dict[str, dict] = {}
    batch_size = 50
    for start in range(0, len(video_ids), batch_size):
        batch = video_ids[start : start + batch_size]
        try:
            response = client.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(batch),
            ).execute()
        except Exception as exc:  # noqa: BLE001
            raise _translate_http_error(exc) from exc

        for item in response.get("items", []):
            vid = item.get("id")
            snippet = item.get("snippet", {}) or {}
            content_details = item.get("contentDetails", {}) or {}
            statistics = item.get("statistics", {}) or {}
            details[vid] = {
                "video_id": vid,
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "published_at": parse_youtube_datetime(snippet.get("publishedAt")),
                "duration_seconds": parse_iso8601_duration(content_details.get("duration")),
                "view_count": int(statistics["viewCount"]) if "viewCount" in statistics else None,
                "like_count": int(statistics["likeCount"]) if "likeCount" in statistics else None,
                "tags": snippet.get("tags", []),
                "thumbnail_url": thumbnail_url_from_snippet(snippet),
                "video_url": video_url(vid),
                "raw": item,
            }

        missing = set(batch) - set(details.keys())
        if missing:
            logger.warning("No metadata returned for %d video(s): %s", len(missing), missing)

    return details
