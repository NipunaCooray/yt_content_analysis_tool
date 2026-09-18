from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db import crud
from db.database import get_database_info, get_database_path, get_session, is_production
from services.youtube_api import api_key_configured
from utils.validators import validate_reviewer_fields

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Settings", "API configuration, reviewers, and the audit trail.")

st.subheader("Database")
db_info = get_database_info()
col_db1, col_db2 = st.columns(2)
if db_info["connected"]:
    col_db1.success(f"Connected ({db_info['backend']})", icon="✅")
else:
    col_db1.error("Not connected", icon="🚨")
    if db_info["error"]:
        st.caption(db_info["error"])
col_db2.caption(f"Environment: **{'production' if is_production() else 'development'}**")
if db_info["backend"] == "sqlite":
    st.caption(f"Local SQLite file: `{get_database_path()}`")
    if is_production():
        st.warning(
            "Running in production with SQLite. Research data on Streamlit Community Cloud's "
            "local disk is not persistent -- set DATABASE_URL to a PostgreSQL connection "
            "string before collecting real study data.",
            icon="⚠️",
        )
# Never display the connection string, host, username, or password here --
# only whether the connection works and which database backend it is.

st.markdown("---")
st.subheader("YouTube API key")
if api_key_configured():
    st.success("YOUTUBE_API_KEY is configured.", icon="✅")
else:
    st.error(
        "No YouTube API key found. Locally, create a `.env` file in the project root (copy "
        "from `.env.example`) with:\n\n```\nYOUTUBE_API_KEY=your_key_here\n```\n\nThen "
        "restart the app. In Streamlit Community Cloud, set it under App -> Settings -> "
        "Secrets instead. Get a key from the Google Cloud Console (APIs & Services -> "
        "Credentials) with the YouTube Data API v3 enabled.",
        icon="🔑",
    )

st.markdown("---")
st.subheader("Reviewers")

tab_list, tab_add = st.tabs(["Existing reviewers", "Add reviewer"])

with tab_add:
    with st.form("add_reviewer_form", clear_on_submit=True):
        name = st.text_input("Name*")
        initials = st.text_input("Initials*", max_chars=10)
        email = st.text_input("Email (optional)")
        submitted = st.form_submit_button("Add reviewer", type="primary")
        if submitted:
            errors = validate_reviewer_fields(name, initials)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                crud.create_reviewer(
                    db, name=name.strip(), initials=initials.strip(), email=email or None
                )
                st.success(f"Reviewer '{name}' added.")
                st.rerun()

with tab_list:
    reviewers = crud.list_reviewers(db)
    if not reviewers:
        st.info("No reviewers yet. Add one in the 'Add reviewer' tab.")
    else:
        for reviewer in reviewers:
            with st.expander(f"{reviewer.name} ({reviewer.initials})"):
                with st.form(f"edit_reviewer_{reviewer.id}"):
                    name = st.text_input("Name*", value=reviewer.name, key=f"rn_{reviewer.id}")
                    initials = st.text_input(
                        "Initials*", value=reviewer.initials, key=f"ri_{reviewer.id}"
                    )
                    email = st.text_input(
                        "Email (optional)", value=reviewer.email or "", key=f"re_{reviewer.id}"
                    )
                    b1, b2 = st.columns(2)
                    save = b1.form_submit_button("Save", type="primary")
                    delete = b2.form_submit_button("Delete")
                    if save:
                        errors = validate_reviewer_fields(name, initials)
                        if errors:
                            for e in errors:
                                st.error(e)
                        else:
                            crud.update_reviewer(
                                db,
                                reviewer.id,
                                name=name.strip(),
                                initials=initials.strip(),
                                email=email or None,
                            )
                            st.success("Reviewer updated.")
                            st.rerun()
                    if delete:
                        crud.delete_reviewer(db, reviewer.id)
                        st.warning("Reviewer deleted.")
                        st.rerun()

st.markdown("---")
st.subheader("Audit log")
if current_study:
    scope = st.radio(
        "Scope", ["Current study", "All studies"], horizontal=True, key="audit_scope"
    )
    log_entries = crud.list_audit_log(
        db, study_id=current_study.id if scope == "Current study" else None
    )
else:
    log_entries = crud.list_audit_log(db)

if not log_entries:
    st.caption("No audit events recorded yet.")
else:
    df = pd.DataFrame(
        [
            {
                "Time": e.created_at,
                "Action": e.action_type,
                "Entity": f"{e.entity_type or ''} #{e.entity_id}" if e.entity_id else e.entity_type,
                "Details": e.details_json,
            }
            for e in log_entries[:200]
        ]
    )
    st.dataframe(df, width='stretch', hide_index=True)
    if len(log_entries) > 200:
        st.caption(f"Showing 200 of {len(log_entries)} events.")

db.close()
