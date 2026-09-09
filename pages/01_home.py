from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar
from db import crud
from db.database import get_session
from services import accuracy_service, coding_service, screening_service
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

    unique_videos = crud.list_videos(db, current_study.id)
    decisions = crud.list_screening_decisions(db, current_study.id)
    screening_progress = screening_service.compute_progress(unique_videos, decisions)
    cols2 = st.columns(4)
    cols2[0].metric("Unique videos", screening_progress.total)
    cols2[1].metric("Screened", screening_progress.total - screening_progress.not_screened)
    cols2[2].metric("Included", screening_progress.included)
    cols2[3].metric("Excluded", screening_progress.excluded)

    included_videos = crud.list_included_videos(db, current_study.id)
    codings = crud.list_video_codings(db, current_study.id)
    coding_progress = coding_service.compute_progress([v.id for v in included_videos], codings)
    cols3 = st.columns(4)
    cols3[0].metric("Included videos", coding_progress.total)
    cols3[1].metric("Coding not started", coding_progress.not_started)
    cols3[2].metric("Coding in progress", coding_progress.in_progress)
    cols3[3].metric("Coding complete", coding_progress.complete)

    review_statuses = crud.list_accuracy_review_statuses(db, current_study.id)
    claim_counts = crud.count_accuracy_claims(db, current_study.id)
    accuracy_progress = accuracy_service.compute_progress(
        [v.id for v in included_videos], review_statuses, claim_counts
    )
    cols4 = st.columns(4)
    cols4[0].metric("Total claims", sum(claim_counts.values()))
    cols4[1].metric("Accuracy not started", accuracy_progress.not_started)
    cols4[2].metric("Accuracy in progress", accuracy_progress.in_progress)
    cols4[3].metric("Accuracy complete", accuracy_progress.complete)

    if current_study.description:
        st.write(current_study.description)

st.markdown("#### Research workflow")
st.markdown(
    """
1. **Study setup** — define the study and its defaults.
2. **Search strategy** — build the reproducible query set.
3. **Pilot search** — test queries on a small sample, rate relevance, refine, approve.
4. **Full search results** — run the approved strategy at scale, deduplicate into the master video list.
5. **Screening** — include/exclude/unsure each unique video, with reasons and notes.
6. **Video coding** — characteristics, information coverage, older-adult needs, presentation.
7. **Accuracy assessment** — claim-level fact-checking against official sources.
8. **Dashboard** — study-wide progress and descriptive charts.
9. **Export** — all datasets as CSV/JSON, individually or as one ZIP.
    """
)

db.close()
