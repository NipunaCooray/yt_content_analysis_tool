from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db.database import get_session

db = get_session()
render_context_sidebar(db)

page_header("Accuracy assessment", "Assess factual/instructional claims at claim level.")
st.info(
    "This page is not built yet. It arrives in **Phase 6**, after coding (Phase 5) is in place.",
    icon="🚧",
)
db.close()
