from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db.database import get_session

db = get_session()
render_context_sidebar(db)

page_header("Video coding", "Code included videos for characteristics, information coverage, "
            "older-adult needs, and presentation.")
st.info(
    "This page is not built yet. It arrives in **Phase 5**, once videos have been screened "
    "and included (Phase 4).",
    icon="🚧",
)
db.close()
