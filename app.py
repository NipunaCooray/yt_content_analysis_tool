"""
Transport Information Analysis Tool - entry point / page router.

Run with: streamlit run app.py

Uses Streamlit's st.navigation/st.Page API so the sidebar shows the exact
workflow pages from the handover doc (section 6), in order, regardless of
underlying filenames.
"""

from __future__ import annotations

import streamlit as st

from db.database import ConfigurationError, init_db

st.set_page_config(
    page_title="Transport Information Analysis Tool",
    page_icon="🚌",
    layout="wide",
)

try:
    init_db()
except ConfigurationError as exc:
    # Production with no DATABASE_URL configured: stop here with a clean
    # message rather than falling back to local SQLite (Streamlit Cloud's
    # local disk isn't persistent) or showing a raw traceback.
    st.error(f"⚠️ Configuration error: {exc}", icon="🚨")
    st.stop()

PAGES = [
    st.Page("pages/01_home.py", title="Home", icon="🏠", default=True),
    st.Page("pages/02_study_setup.py", title="Study setup", icon="🗂️"),
    st.Page("pages/03_search_strategy.py", title="Search strategy", icon="🔍"),
    st.Page("pages/04_pilot_search.py", title="Pilot search", icon="🧪"),
    st.Page("pages/05_search_results.py", title="Full search results", icon="📥"),
    st.Page("pages/06_screening.py", title="Screening", icon="✅"),
    st.Page("pages/07_video_coding.py", title="Video coding", icon="🏷️"),
    st.Page("pages/08_accuracy_assessment.py", title="Accuracy assessment", icon="🔎"),
    st.Page("pages/09_reliability.py", title="Reliability", icon="🎯"),
    st.Page("pages/10_dashboard.py", title="Dashboard", icon="📊"),
    st.Page("pages/11_export.py", title="Export", icon="⬇️"),
    st.Page("pages/12_settings.py", title="Settings", icon="⚙️"),
]

nav = st.navigation(PAGES)
nav.run()
