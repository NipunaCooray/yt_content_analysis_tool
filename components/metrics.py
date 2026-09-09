"""Small helpers for rendering progress counters / metric rows."""

from __future__ import annotations

import streamlit as st


def metric_row(items: list[tuple[str, object]]) -> None:
    """items: list of (label, value) pairs, rendered as st.metric columns."""
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)
