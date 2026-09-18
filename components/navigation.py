"""
Shared sidebar elements: current-study and current-reviewer selectors.

Streamlit's built-in multipage nav (the pages/ folder) handles page-to-page
navigation; this module renders the context selectors that every page needs
so the researcher doesn't re-pick their study/reviewer on every screen.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from components.caching import cached_reviewer_options, cached_study_options
from db import crud
from db.models import Reviewer, Study


def render_context_sidebar(db: Session) -> tuple[Study | None, Reviewer | None]:
    """Render study + reviewer pickers in the sidebar and return the current
    selections.

    Builds each dropdown's labels from a short-TTL cache (see
    components/caching.py) instead of re-listing every study/reviewer on
    every single page load, then does exactly one fresh, uncached
    primary-key lookup for whichever one is actually selected -- never a
    second full list-then-refetch round trip for the same data.
    """
    st.sidebar.markdown("### Study")
    study_rows = cached_study_options(db)
    current_study = None
    if not study_rows:
        st.sidebar.info("No studies yet. Create one on the Study Setup page.")
    else:
        options = {row["id"]: f"{row['name']} ({row['search_status']})" for row in study_rows}
        default_id = st.session_state.get("current_study_id", study_rows[0]["id"])
        if default_id not in options:
            default_id = study_rows[0]["id"]
        selected_id = st.sidebar.selectbox(
            "Current study",
            options=list(options.keys()),
            format_func=lambda sid: options[sid],
            index=list(options.keys()).index(default_id),
            label_visibility="collapsed",
        )
        st.session_state["current_study_id"] = selected_id
        current_study = crud.get_study(db, selected_id)

    st.sidebar.markdown("### Reviewer")
    reviewer_rows = cached_reviewer_options(db)
    current_reviewer = None
    if not reviewer_rows:
        st.sidebar.info("No reviewers yet. Add one on the Settings page.")
    else:
        options = {row["id"]: f"{row['name']} ({row['initials']})" for row in reviewer_rows}
        default_id = st.session_state.get("current_reviewer_id", reviewer_rows[0]["id"])
        if default_id not in options:
            default_id = reviewer_rows[0]["id"]
        selected_id = st.sidebar.selectbox(
            "Current reviewer",
            options=list(options.keys()),
            format_func=lambda rid: options[rid],
            index=list(options.keys()).index(default_id),
            label_visibility="collapsed",
        )
        st.session_state["current_reviewer_id"] = selected_id
        current_reviewer = crud.get_reviewer(db, selected_id)

    return current_study, current_reviewer


def require_study(study: Study | None) -> bool:
    if study is None:
        st.warning("Create or select a study first (see Study Setup in the sidebar).")
        return False
    return True


def page_header(title: str, caption: str | None = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)
