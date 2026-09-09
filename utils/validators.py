"""Lightweight validation helpers for form input."""

from __future__ import annotations


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
