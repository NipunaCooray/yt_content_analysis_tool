"""
Shared sidebar elements: current-study and current-reviewer selectors.

Streamlit's built-in multipage nav (the pages/ folder) handles page-to-page
navigation; this module renders the context selectors that every page needs
so the researcher doesn't re-pick their study/reviewer on every screen.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from db import crud
from db.models import Reviewer, Study


def render_context_sidebar(db: Session) -> tuple[Study | None, Reviewer | None]:
    """Render study + reviewer pickers in the sidebar and return the current selections."""
    st.sidebar.markdown("### Study")
    studies = crud.list_studies(db)
    current_study = None
    if not studies:
        st.sidebar.info("No studies yet. Create one on the Study Setup page.")
    else:
        options = {s.id: f"{s.name} ({s.search_status})" for s in studies}
        default_id = st.session_state.get("current_study_id", studies[0].id)
        if default_id not in options:
            default_id = studies[0].id
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
    reviewers = crud.list_reviewers(db)
    current_reviewer = None
    if not reviewers:
        st.sidebar.info("No reviewers yet. Add one on the Settings page.")
    else:
        options = {r.id: f"{r.name} ({r.initials})" for r in reviewers}
        default_id = st.session_state.get("current_reviewer_id", reviewers[0].id)
        if default_id not in options:
            default_id = reviewers[0].id
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
