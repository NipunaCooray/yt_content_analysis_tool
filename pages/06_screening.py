from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db.database import get_session

db = get_session()
render_context_sidebar(db)

page_header("Screening", "Determine which unique videos are eligible for content analysis.")
st.info(
    "This page is not built yet. It arrives in **Phase 4**, once deduplicated videos exist "
    "from the full search (Phase 3).",
    icon="🚧",
)
db.close()
