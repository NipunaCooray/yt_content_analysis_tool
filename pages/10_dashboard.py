from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from db import crud
from db.database import get_session
from services import accuracy_service, coding_service, export_service, pilot_service, reliability_service, screening_service

# Single consistent hue for plain magnitude bars (dataviz skill: sequential
# blue, categorical slot 1) -- color isn't encoding a second variable here,
# so one hue throughout is correct rather than a rainbow per bar.
BAR_COLOR = "#2a78d6"

# Accuracy assessment is a genuine correctness status, so it gets the
# reserved status palette instead of the plain bar color.
ACCURACY_COLORS = {
    "Correct": "#0ca30c",           # good
    "Correct but incomplete": "#fab219",  # warning
    "Outdated": "#ec835a",          # serious
    "Incorrect": "#d03b3b",         # critical
    "Unverifiable": "#898781",      # muted
}

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
review_statuses = crud.list_accuracy_review_statuses(db, study_id)
claim_counts = crud.count_accuracy_claims(db, study_id)
accuracy_progress = accuracy_service.compute_progress(
    [v.id for v in included_videos], review_statuses, claim_counts
)
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
r2[2].metric("Accuracy reviews completed", accuracy_progress.complete)
r2[3].metric("Pilot searches completed", len(pilot_runs))

st.markdown("---")

# ---------------------------------------------------------------------------
# Descriptive charts
# ---------------------------------------------------------------------------

st.subheader("Coded video characteristics")

char_df = export_service.video_characteristics_df(db, study_id)

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

col3, col4 = st.columns(2)
with col3:
    st.caption("Information domains marked 'Present'")
    info_df = export_service.information_domains_df(db, study_id)
    if info_df.empty:
        st.caption("No information-coverage coding yet.")
    else:
        present = info_df[info_df["value"] == "Present"]["domain_name"].value_counts()
        _bar_chart(present, "Videos", height=420)

with col4:
    st.caption("Older-adult needs marked 'Addressed'")
    needs_df = export_service.older_adult_needs_df(db, study_id)
    if needs_df.empty:
        st.caption("No older-adult-needs coding yet.")
    else:
        addressed = needs_df[needs_df["value"] == "Addressed"]["need_name"].value_counts()
        _bar_chart(addressed, "Videos", height=380)

st.markdown("---")
st.subheader("Accuracy & screening")

col5, col6 = st.columns(2)
with col5:
    st.caption("Accuracy assessment distribution (claims)")
    claims_df = export_service.accuracy_claims_df(db, study_id)
    if claims_df.empty:
        st.caption("No accuracy claims recorded yet.")
    else:
        _bar_chart(claims_df["assessment"].value_counts(), "Claims", color=ACCURACY_COLORS)

with col6:
    st.caption("Screening exclusion reasons")
    screening_df = export_service.screening_df(db, study_id)
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

st.markdown("---")

# ---------------------------------------------------------------------------
# Reliability (double-coding)
# ---------------------------------------------------------------------------

st.subheader("Reliability")

double_screened = reliability_service.double_coded_videos(db, study_id, unique_videos, "screening")
double_coded = reliability_service.double_coded_videos(db, study_id, included_videos, "coding")

if not double_screened and not double_coded:
    st.caption(
        "No videos have been double-screened or double-coded yet. See the Reliability page "
        "to select a random sample."
    )
else:
    rc1, rc2 = st.columns(2)
    if double_screened:
        screening_stat, _ = reliability_service.screening_reliability(db, study_id, double_screened)
        rc1.metric(
            "Screening agreement (κ)",
            screening_stat.kappa if screening_stat.kappa is not None else "—",
            help=f"{screening_stat.percentage_agreement}% agreement across {screening_stat.n_pairs} "
                 "double-screened video(s).",
        )
    else:
        rc1.metric("Screening agreement (κ)", "—")

    if double_coded:
        char_stats, _ = reliability_service.coding_characteristics_reliability(db, study_id, double_coded)
        kappas = [s.kappa for s in char_stats if s.kappa is not None]
        avg_kappa = round(sum(kappas) / len(kappas), 3) if kappas else None
        rc2.metric(
            "Coding characteristics agreement (avg κ)",
            avg_kappa if avg_kappa is not None else "—",
            help=f"Averaged across {len(kappas)} characteristic field(s) for "
                 f"{len(double_coded)} double-coded video(s). Full breakdown on the "
                 "Reliability page.",
        )
    else:
        rc2.metric("Coding characteristics agreement (avg κ)", "—")

    st.caption("See the Reliability page for full field-by-field agreement and disagreements.")

db.close()
