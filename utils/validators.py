"""Lightweight validation helpers for form input."""

from __future__ import annotations

from datetime import date

from utils.constants import (
    PUBLICATION_FILTER_AFTER,
    PUBLICATION_FILTER_BEFORE,
    PUBLICATION_FILTER_BETWEEN,
)


def require_non_empty(value: str | None, field_name: str) -> str | None:
    """Return an error message if value is empty/whitespace, else None."""
    if not value or not value.strip():
        return f"{field_name} is required."
    return None


def validate_study_fields(name: str, default_results_per_query: int) -> list[str]:
    errors = []
    err = require_non_empty(name, "Study name")
    if err:
        errors.append(err)
    if default_results_per_query is None or default_results_per_query < 1:
        errors.append("Default results per query must be at least 1.")
    return errors


def validate_query_fields(query_text: str) -> list[str]:
    errors = []
    err = require_non_empty(query_text, "Query text")
    if err:
        errors.append(err)
    return errors


def validate_reviewer_fields(name: str, initials: str) -> list[str]:
    errors = []
    err = require_non_empty(name, "Reviewer name")
    if err:
        errors.append(err)
    err = require_non_empty(initials, "Initials")
    if err:
        errors.append(err)
    return errors


def validate_publication_date_filter(
    filter_type: str, published_after: date | None, published_before: date | None
) -> list[str]:
    errors = []
    if filter_type == PUBLICATION_FILTER_AFTER and not published_after:
        errors.append("A 'published after' date is required.")
    elif filter_type == PUBLICATION_FILTER_BEFORE and not published_before:
        errors.append("A 'published before' date is required.")
    elif filter_type == PUBLICATION_FILTER_BETWEEN:
        if not published_after or not published_before:
            errors.append("Both start and end dates are required.")
        elif published_after > published_before:
            errors.append("The start date must be earlier than or equal to the end date.")
    return errors
