"""Small shared helpers used across services and pages."""

from __future__ import annotations

import re
from datetime import date, datetime

from utils.constants import (
    PUBLICATION_FILTER_AFTER,
    PUBLICATION_FILTER_BEFORE,
    PUBLICATION_FILTER_BETWEEN,
    PUBLICATION_PERIOD_LABELS,
)


def parse_iso8601_duration(duration: str | None) -> int | None:
    """Convert a YouTube API ISO-8601 duration (e.g. 'PT4M13S') to seconds."""
    if not duration:
        return None
    pattern = re.compile(
        r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
    )
    match = pattern.match(duration)
    if not match:
        return None
    parts = match.groupdict()
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_youtube_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def thumbnail_url_from_snippet(snippet: dict) -> str | None:
    thumbnails = snippet.get("thumbnails", {}) if snippet else {}
    for key in ("medium", "high", "default"):
        if key in thumbnails:
            return thumbnails[key].get("url")
    return None


def study_export_code(study_id: int) -> str:
    """e.g. study_001 -- used as an export filename prefix."""
    return f"study_{study_id:03d}"


def safe_percentage(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round((numerator / denominator) * 100, 1)


def publication_date_api_params(
    filter_type: str, published_after: date | None, published_before: date | None
) -> dict[str, str]:
    """Build the publishedAfter/publishedBefore kwargs for search.list from a
    publication-date filter selection. Returns {} for "all time" or when a
    required date is missing (validation is the caller's job -- see
    utils.validators.validate_publication_date_filter)."""
    params: dict[str, str] = {}
    if filter_type == PUBLICATION_FILTER_AFTER and published_after:
        params["published_after"] = f"{published_after.isoformat()}T00:00:00Z"
    elif filter_type == PUBLICATION_FILTER_BEFORE and published_before:
        params["published_before"] = f"{published_before.isoformat()}T23:59:59Z"
    elif filter_type == PUBLICATION_FILTER_BETWEEN and published_after and published_before:
        params["published_after"] = f"{published_after.isoformat()}T00:00:00Z"
        params["published_before"] = f"{published_before.isoformat()}T23:59:59Z"
    return params


def _format_date(d: date) -> str:
    # Portable day-of-month without a leading zero (strftime's "%-d"/"%e"
    # aren't consistent across platforms).
    return d.strftime("%d %b %Y").lstrip("0")


def format_publication_period_label(
    filter_type: str, published_after: date | None, published_before: date | None
) -> str:
    """e.g. 'All time' / 'After 1 Jan 2020' / '1 Jan 2020 - 31 Dec 2025'."""
    if filter_type == PUBLICATION_FILTER_AFTER and published_after:
        return f"After {_format_date(published_after)}"
    if filter_type == PUBLICATION_FILTER_BEFORE and published_before:
        return f"Before {_format_date(published_before)}"
    if filter_type == PUBLICATION_FILTER_BETWEEN and published_after and published_before:
        return f"{_format_date(published_after)} - {_format_date(published_before)}"
    return PUBLICATION_PERIOD_LABELS.get(filter_type, "All time")
