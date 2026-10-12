"""Shared builders for coding_service.save_video_coding() inputs."""

from __future__ import annotations

from utils.constants import INFORMATION_COVERAGE_ITEMS, OLDER_ADULT_NEED_ITEMS


def full_information_coverage(value: str = "Absent", **overrides) -> dict:
    """Every revised information-coverage item coded `value`; keyword
    overrides map item_key -> (value, notes)."""
    values = {item.key: (value, None) for item in INFORMATION_COVERAGE_ITEMS}
    values.update(overrides)
    return values


def full_older_adult_needs(value: str = "No", **overrides) -> dict:
    """All four older-adult needs answered `value`; keyword overrides map
    need_key -> (value, notes)."""
    values = {item.key: (value, None) for item in OLDER_ADULT_NEED_ITEMS}
    values.update(overrides)
    return values
