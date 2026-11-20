"""
Thin wrapper around the YouTube Data API v3.

Responsible only for talking to the API and normalising responses into
plain dicts -- it knows nothing about pilot runs, studies, etc. See
handover doc section 10.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from utils.helpers import parse_iso8601_duration, parse_youtube_datetime, thumbnail_url_from_snippet, video_url
from utils.logging import get_logger

logger = get_logger(__name__)


class YouTubeAPIError(Exception):
    """Raised for any recoverable YouTube API failure, with a UI-friendly message."""


class YouTubeAPIKeyMissingError(YouTubeAPIError):
    pass


class YouTubeQuotaExceededError(YouTubeAPIError):
    """Daily quota hit. Enforcement is approximate near the limit, so a later
    call can still succeed -- don't abandon a run on the first one."""


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
    from db.database import get_secret  # local import: avoids a hard dependency for callers/tests

    return get_secret("YOUTUBE_API_KEY") or None


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


_QUOTA_REASONS = {"quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded", "userRateLimitExceeded"}


def _redact_api_key(text: str) -> str:
    """Strip the API key from text before it reaches the UI, the DB or the logs.

    googleapiclient's HttpError str() embeds the full request URL, key= included.
    """
    text = re.sub(r"([?&]key=)[^&\s\"'>]+", r"\1REDACTED", text)
    api_key = None
    try:
        api_key = get_api_key()
    except Exception:  # noqa: BLE001 - redaction must never raise
        api_key = None
    if api_key:
        text = text.replace(api_key, "REDACTED")
    return text


def _http_error_message(exc: Exception) -> str:
    """The API's own human-readable message, without the request URL."""
    message = ""
    try:
        message = exc._get_reason() or ""  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        message = getattr(exc, "reason", "") or ""
    return _redact_api_key(str(message).strip()) or "no details returned"


def _translate_http_error(exc: Exception) -> YouTubeAPIError:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:  # pragma: no cover
        return YouTubeAPIError(_redact_api_key(str(exc)))

    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", None)
        reason = ""
        try:
            reason = exc.error_details[0].get("reason", "") if exc.error_details else ""
        except Exception:
            reason = ""
        message = _http_error_message(exc)
        # Daily quota exhaustion arrives as 403 quotaExceeded for the units quota,
        # but as 429 rateLimitExceeded for search.list's own "Search Queries per
        # day" bucket (June 2026). Near the limit Google enforces it loosely, so
        # some calls still succeed after the first 429 -- callers must not stop.
        if status in (403, 429) and (reason in _QUOTA_REASONS or "quota" in message.lower()):
            return YouTubeQuotaExceededError(
                "YouTube API quota exceeded for today. Try again after the daily quota "
                "resets (midnight Pacific time), or use a different API key."
            )
        if status == 400:
            return YouTubeAPIError(f"Invalid YouTube API request: {message}")
        if status == 403:
            return YouTubeAPIError(
                "YouTube API request was refused (403). Check that your API key is valid "
                "and that the YouTube Data API v3 is enabled for it."
            )
        return YouTubeAPIError(f"YouTube API error ({status}): {message}")
    return YouTubeAPIError(f"Unexpected error calling YouTube API: {_redact_api_key(str(exc))}")


def search_videos(
    query: str,
    max_results: int = 10,
    order: str = "relevance",
    region_code: str | None = "AU",
    relevance_language: str | None = "en",
    published_after: str | None = None,
    published_before: str | None = None,
) -> list[SearchResultItem]:
    """Run search.list for a query and return normalised, ranked results.

    YouTube caps each search.list call at 50 results, so requests for more
    than that are paginated internally via nextPageToken (each page is a
    separate search call against the daily quota -- see estimate_search_calls()).

    published_after/published_before are full ISO-8601 UTC timestamps (e.g.
    "2020-01-01T00:00:00Z") matching the YouTube API's own parameter format --
    build them with utils.helpers.publication_date_api_params() rather than
    passing a bare date. This is a filter on publication date, not a sort;
    `order` is unaffected.
    """
    client = _build_client()
    results: list[SearchResultItem] = []
    page_token: str | None = None

    while len(results) < max_results:
        page_size = min(50, max_results - len(results))
        try:
            request_kwargs: dict[str, Any] = dict(
                part="snippet",
                q=query,
                type="video",
                maxResults=page_size,
                order=order,
            )
            if region_code:
                request_kwargs["regionCode"] = region_code
            if relevance_language:
                request_kwargs["relevanceLanguage"] = relevance_language
            if published_after:
                request_kwargs["publishedAfter"] = published_after
            if published_before:
                request_kwargs["publishedBefore"] = published_before
            if page_token:
                request_kwargs["pageToken"] = page_token

            response = client.search().list(**request_kwargs).execute()
        except Exception as exc:  # noqa: BLE001 - normalised below
            raise _translate_http_error(exc) from exc

        items = response.get("items", [])
        for item in items:
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
                    rank=len(results) + 1,
                    raw=item,
                )
            )

        page_token = response.get("nextPageToken")
        if not page_token or not items:
            break

    if not results:
        logger.info("Search for query %r returned no results.", query)
    return results


def summarise_quota_failures(query_texts: list[str]) -> str:
    """One line covering every query that hit the daily search quota."""
    listed = ", ".join(f"'{q}'" for q in query_texts)
    return (
        f"YouTube search quota exceeded for today: {len(query_texts)} quer(y/ies) failed "
        f"({listed}). The quota resets at midnight Pacific time; re-run these queries then."
    )


def estimate_search_calls(num_queries: int, max_results: int) -> int:
    """Number of search.list calls a run will use.

    Since June 2026 search.list has its own quota bucket (default 100 calls
    per day per project, 1 per call). Each page holds at most 50 results, so
    requesting more than 50 per query costs proportionally more calls.
    """
    pages_per_query = max(1, math.ceil(max_results / 50))
    return num_queries * pages_per_query


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
