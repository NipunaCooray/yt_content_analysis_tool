"""Reusable form widgets shared across pages."""

from __future__ import annotations

import streamlit as st

from utils.constants import IRRELEVANCE_REASONS


def relevance_rating_widget(key_prefix: str, current_rating: str, current_reason: str | None):
    """Renders relevance radio + conditional irrelevance-reason dropdown.

    Returns (rating, reason).
    """
    options = ["Relevant", "Potentially relevant", "Irrelevant"]
    index = options.index(current_rating) if current_rating in options else 0
    rating = st.radio(
        "Relevance",
        options,
        index=index,
        key=f"{key_prefix}_rating",
        horizontal=True,
    )
    reason = None
    if rating == "Irrelevant":
        reason_index = (
            IRRELEVANCE_REASONS.index(current_reason) if current_reason in IRRELEVANCE_REASONS else 0
        )
        reason = st.selectbox(
            "Irrelevance reason",
            IRRELEVANCE_REASONS,
            index=reason_index,
            key=f"{key_prefix}_reason",
        )
    return rating, reason
