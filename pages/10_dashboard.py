from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.caching import cached_export_dataframe
from components.navigation import page_header, render_context_sidebar, require_study
from db import crud
from db.database import get_session
from services import coding_service, export_service, pilot_service, screening_service

# Single consistent hue for plain magnitude bars (dataviz skill: sequential
# blue, categorical slot 1) -- color isn't encoding a second variable here,
# so one hue throughout is correct rather than a rainbow per bar.
BAR_COLOR = "#2a78d6"

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Dashboard", "Study progress counters and descriptive charts.")

if not require_study(current_study):
    db.close()
    st.stop()

study_id = current_study.id


def _bar_chart(counts: pd.Series, x_title: str, color=BAR_COLOR, height: int = 360):
    if counts.empty:
        st.caption("No data yet.")
        return
    counts = counts.sort_values(ascending=True)
    colors = [color.get(cat, BAR_COLOR) for cat in counts.index] if isinstance(color, dict) else color
    fig = go.Figure(
        go.Bar(
            x=counts.values, y=counts.index, orientation="h",
            marker_color=colors,
            text=counts.values, textposition="outside",
        )
    )
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=x_title,
        yaxis_title=None,
        showlegend=False,
    )
    st.plotly_chart(fig, theme="streamlit")


# ---------------------------------------------------------------------------
# Study overview counters
# ---------------------------------------------------------------------------

raw_results = crud.list_search_results_raw(db, study_id)
unique_videos = crud.list_videos(db, study_id)
decisions = crud.list_screening_decisions(db, study_id)
screening_progress = screening_service.compute_progress(unique_videos, decisions)
included_videos = crud.list_included_videos(db, study_id)
codings = crud.list_video_codings(db, study_id)
coding_progress = coding_service.compute_progress([v.id for v in included_videos], codings)
pilot_runs = crud.list_pilot_search_runs(db, study_id)

st.subheader("Study overview")
r1 = st.columns(4)
r1[0].metric("Raw results", len(raw_results))
r1[1].metric("Unique videos", len(unique_videos))
r1[2].metric("Screened", screening_progress.total - screening_progress.not_screened)
r1[3].metric("Included", screening_progress.included)
r2 = st.columns(4)
r2[0].metric("Excluded", screening_progress.excluded)
r2[1].metric("Coded (started)", coding_progress.in_progress + coding_progress.complete)
r2[2].metric("Coding complete", coding_progress.complete)
r2[3].metric("Pilot searches completed", len(pilot_runs))

st.markdown("---")

# ---------------------------------------------------------------------------
# Descriptive charts
# ---------------------------------------------------------------------------

st.subheader("Coded video characteristics")

char_df = cached_export_dataframe(db, study_id, "video_characteristics")

col1, col2 = st.columns(2)
with col1:
    st.caption("Videos by transport mode")
    if char_df.empty:
        st.caption("No coded videos yet.")
    else:
        modes = char_df["transport_modes"].str.split(", ").explode()
        modes = modes[modes != ""]
        _bar_chart(modes.value_counts(), "Videos")

with col2:
    st.caption("Videos by jurisdiction")
    if char_df.empty:
        st.caption("No coded videos yet.")
    else:
        jurisdictions = char_df["jurisdictions"].str.split(", ").explode()
        jurisdictions = jurisdictions[jurisdictions != ""]
        _bar_chart(jurisdictions.value_counts(), "Videos")

st.caption("Videos by uploader type")
if char_df.empty or char_df["uploader_type"].dropna().empty:
    st.caption("No coded videos yet.")
else:
    _bar_chart(char_df["uploader_type"].dropna().value_counts(), "Videos")

st.markdown("---")
st.subheader("Information coverage & older-adult needs")


# One coding record per video, so these count videos directly.
info_df = cached_export_dataframe(db, study_id, "information_domains")
needs_df = cached_export_dataframe(db, study_id, "older_adult_needs")
present_df = info_df[info_df["value"] == "Present"] if not info_df.empty else info_df

col3, col4 = st.columns(2)
with col3:
    st.caption("Videos covering each information category (at least one item 'Present')")
    if info_df.empty:
        st.caption("No information-coverage coding yet.")
    else:
        _bar_chart(present_df.groupby("category")["video_pk"].nunique(), "Videos")

with col4:
    st.caption("% of coded videos mentioning each older-adult need")
    answered = needs_df[needs_df["mentioned"].isin(["Yes", "No"])] if not needs_df.empty else needs_df
    if answered.empty:
        st.caption("No older-adult-needs coding yet.")
    else:
        pct = (
            answered.assign(yes=answered["mentioned"] == "Yes")
            .groupby("need_label")["yes"].mean().mul(100).round(1)
        )
        _bar_chart(pct, "% of coded videos")

if not info_df.empty:
    with st.expander("Information coverage by item"):
        _bar_chart(
            present_df.groupby("item_label")["video_pk"].nunique(), "Videos marked 'Present'",
            height=760,
        )

st.markdown("---")
st.subheader("Screening")

col5, _ = st.columns(2)
with col5:
    st.caption("Screening exclusion reasons")
    screening_df = cached_export_dataframe(db, study_id, "screening")
    if screening_df.empty or screening_df["exclusion_reason"].dropna().empty:
        st.caption("No excluded videos yet.")
    else:
        _bar_chart(screening_df["exclusion_reason"].dropna().value_counts(), "Videos")

st.markdown("---")

# ---------------------------------------------------------------------------
# Pilot search dashboard
# ---------------------------------------------------------------------------

st.subheader("Pilot search")

approvals = crud.list_search_strategy_approvals(db, study_id)
active_queries = crud.list_search_queries(db, study_id, active_only=True)

pp1, pp2, pp3 = st.columns(3)
pp1.metric("Pilot iterations", len(pilot_runs))
pp2.metric("Approved query count", len(approvals[0].query_snapshot_json) if approvals else 0)
pp3.metric("Active queries now", len(active_queries))

if not pilot_runs:
    st.caption("No pilot runs yet.")
else:
    latest_run = pilot_runs[0]
    st.caption(f"Showing the latest pilot run (#{latest_run.id}, {latest_run.run_timestamp:%Y-%m-%d %H:%M}).")

    performance = pilot_service.compute_query_performance(db, latest_run.id)
    diagnostics = pilot_service.compute_diagnostics(db, latest_run.id)

    col7, col8 = st.columns(2)
    with col7:
        st.caption("Relevant + potentially relevant rate by query")
        if performance:
            rates = pd.Series(
                {p.query_text: p.broad_relevance_rate or 0 for p in performance}
            )
            _bar_chart(rates, "Broad relevance %")
        else:
            st.caption("No results reviewed yet.")

    with col8:
        st.caption("Irrelevance reasons (latest run)")
        if diagnostics.irrelevance_reason_counts:
            _bar_chart(pd.Series(diagnostics.irrelevance_reason_counts), "Results")
        else:
            st.caption("No irrelevant results recorded.")

    dup_rate = (
        len(diagnostics.duplicate_video_ids) / diagnostics.unique_videos * 100
        if diagnostics.unique_videos else 0
    )
    st.caption(
        f"Duplicate rate: {dup_rate:.0f}% of unique videos in this run were found by more than "
        f"one query ({len(diagnostics.duplicate_video_ids)} of {diagnostics.unique_videos})."
    )

db.close()
