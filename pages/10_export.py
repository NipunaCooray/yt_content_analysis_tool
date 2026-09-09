from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db.database import get_session

db = get_session()
render_context_sidebar(db)

page_header("Export", "Export analysis-ready CSV datasets.")
st.info(
    "This page is not built yet. It arrives in **Phase 7**, providing CSV exports for every "
    "dataset listed in the handover doc (studies, queries, pilot results, screening, coding, "
    "accuracy claims, reviewers, etc.).",
    icon="🚧",
)
db.close()
