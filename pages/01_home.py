from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db import crud
from db.database import get_session
from services.youtube_api import api_key_configured

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header(
    "🚌 Transport Information Analysis Tool",
    "Research data collection, screening, coding, accuracy-assessment, and export tool for a "
    "content analysis of Australian public/alternative transport videos on YouTube.",
)

if not api_key_configured():
    st.warning(
        "No YouTube API key found. Copy `.env.example` to `.env` and set `YOUTUBE_API_KEY` "
        "before running a pilot or full search. See the Settings page for details.",
        icon="🔑",
    )

st.markdown("---")

if current_study is None:
    st.info(
        "**Get started:** open **Study setup** in the sidebar to create your first study, "
        "then add search queries under **Search strategy**."
    )
else:
    st.subheader(f"Current study: {current_study.name}")
    cols = st.columns(4)
    cols[0].metric("Status", current_study.search_status)
    query_count = len(crud.list_search_queries(db, current_study.id))
    active_count = len(crud.list_search_queries(db, current_study.id, active_only=True))
    cols[1].metric("Search queries", query_count)
    cols[2].metric("Active queries", active_count)
    pilot_runs = crud.list_pilot_search_runs(db, current_study.id)
    cols[3].metric("Pilot runs", len(pilot_runs))

    if current_study.description:
        st.write(current_study.description)

st.markdown("#### Research workflow")
st.markdown(
    """
1. **Study setup** — define the study and its defaults.
2. **Search strategy** — build the reproducible query set.
3. **Pilot search** — test queries on a small sample, rate relevance, refine, approve.
4. *Full search results* — run the approved strategy at scale (coming in Phase 3).
5. *Screening → Video coding → Accuracy assessment → Dashboard → Export* — later phases.
    """
)

db.close()
