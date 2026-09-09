from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db.database import get_session

db = get_session()
render_context_sidebar(db)

page_header("Dashboard", "Study progress counters and descriptive charts.")
st.info(
    "This page is not built yet. It arrives in **Phase 7**, once screening, coding, and "
    "accuracy data exist to summarise. Pilot-run relevance stats are already available on "
    "the Pilot search page.",
    icon="🚧",
)
db.close()
