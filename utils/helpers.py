"""Small shared helpers used across services and pages."""

from __future__ import annotations

import re
from datetime import datetime


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
