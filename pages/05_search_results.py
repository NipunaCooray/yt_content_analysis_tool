from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db.database import get_session

db = get_session()
render_context_sidebar(db)

page_header("Full search results", "Run the approved search strategy and preserve all results.")
st.info(
    "This page is not built yet. It arrives in **Phase 3**, after the pilot-search workflow "
    "(Phases 1–2) is in place. It will run the approved active queries, store raw results, "
    "fetch metadata, and deduplicate into the master video list.",
    icon="🚧",
)
db.close()
