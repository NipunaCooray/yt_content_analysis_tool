from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from db import crud
from db.database import get_session
from services import reliability_service

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header(
    "Reliability",
    "Double-screening/coding sample selection and inter-rater agreement (percentage agreement, "
    "Cohen's kappa).",
)

if not require_study(current_study):
    st.stop()

study_id = current_study.id
reviewers = crud.list_reviewers(db)

if len(reviewers) < 2:
    st.info(
        "Add a second reviewer on the Settings page to use double screening/coding. With only "
        "one reviewer there's nothing to compare.",
        icon="👥",
    )
    db.close()
    st.stop()


def _stat_row(stat: reliability_service.FieldReliability) -> dict:
    return {
        "Field": stat.field_name,
        "Pairs": stat.n_pairs,
        "Agreement %": stat.percentage_agreement,
        "Cohen's kappa": stat.kappa,
    }


def _disagreements_df(disagreements: list[reliability_service.Disagreement]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Video": d.video_title,
        "Field": d.field_name,
        d.reviewer_a_name: d.reviewer_a_value,
        d.reviewer_b_name: d.reviewer_b_value,
    } for d in disagreements])


# ---------------------------------------------------------------------------
# Double-coding sample selection
# ---------------------------------------------------------------------------

st.subheader("Double-coding sample")
st.caption(
    "Randomly select a subset of videos for a second reviewer to independently screen/code "
    "(study-initiation guide recommends 20-30%). Selecting more never removes a video already "
    "in the sample."
)

tab_screening_sample, tab_coding_sample = st.tabs(["Screening sample", "Coding sample"])

with tab_screening_sample:
    all_videos = crud.list_videos(db, study_id)
    sample = crud.list_double_coding_sample_video_ids(db, study_id, "screening")
    col1, col2 = st.columns([1, 2])
    pct = col1.number_input("Target %", min_value=1, max_value=100, value=25, key="screening_pct")
    if col1.button("Select random sample", key="select_screening_sample", disabled=not all_videos):
        added = crud.select_random_double_coding_sample(
            db, study_id, "screening", [v.id for v in all_videos], pct
        )
        st.success(f"Added {added} video(s) to the screening double-coding sample.")
        st.rerun()
    col2.metric("Videos in sample", len(sample))
    col2.caption(f"Of {len(all_videos)} unique videos ({pct}% target).")

with tab_coding_sample:
    included_videos = crud.list_included_videos(db, study_id)
    sample = crud.list_double_coding_sample_video_ids(db, study_id, "coding")
    col1, col2 = st.columns([1, 2])
    pct = col1.number_input("Target %", min_value=1, max_value=100, value=25, key="coding_pct")
    if col1.button("Select random sample", key="select_coding_sample", disabled=not included_videos):
        added = crud.select_random_double_coding_sample(
            db, study_id, "coding", [v.id for v in included_videos], pct
        )
        st.success(f"Added {added} video(s) to the coding double-coding sample.")
        st.rerun()
    col2.metric("Videos in sample", len(sample))
    col2.caption(f"Of {len(included_videos)} included videos ({pct}% target).")

st.markdown("---")

# ---------------------------------------------------------------------------
# Screening reliability
# ---------------------------------------------------------------------------

st.subheader("Screening reliability")

all_videos = crud.list_videos(db, study_id)
double_screened = reliability_service.double_coded_videos(db, study_id, all_videos, "screening")

if not double_screened:
    st.caption("No videos have been independently screened by two or more reviewers yet.")
else:
    st.caption(f"{len(double_screened)} video(s) have been screened by 2+ reviewers.")
    stat, disagreements = reliability_service.screening_reliability(db, study_id, double_screened)
    st.dataframe(pd.DataFrame([_stat_row(stat)]), width="stretch", hide_index=True)

    if disagreements:
        with st.expander(f"Disagreements ({len(disagreements)})", expanded=True):
            st.dataframe(_disagreements_df(disagreements), width="stretch", hide_index=True)
        st.caption(
            "To resolve: the reviewer whose decision should stand as the study's record edits "
            "their own entry on the Screening page (the earliest-recorded decision is the "
            "canonical one used everywhere else in the tool)."
        )
    else:
        st.success("No disagreements among double-screened videos.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Coding reliability
# ---------------------------------------------------------------------------

st.subheader("Video coding reliability")

included_videos = crud.list_included_videos(db, study_id)
double_coded = reliability_service.double_coded_videos(db, study_id, included_videos, "coding")

if not double_coded:
    st.caption("No included videos have been independently coded by two or more reviewers yet.")
else:
    st.caption(f"{len(double_coded)} video(s) have been coded by 2+ reviewers.")

    char_stats, char_disagreements = reliability_service.coding_characteristics_reliability(
        db, study_id, double_coded
    )
    info_stats = reliability_service.information_domain_reliability(db, double_coded)
    need_stats = reliability_service.older_adult_need_reliability(db, double_coded)
    pres_stats = reliability_service.presentation_reliability(db, double_coded)

    tab_char, tab_info, tab_needs, tab_pres, tab_disagree = st.tabs(
        ["Characteristics", "Information coverage", "Older-adult needs", "Presentation",
         f"Disagreements ({len(char_disagreements)})"]
    )
    with tab_char:
        st.caption("Multi-select fields (transport mode, jurisdiction) use average set overlap, not kappa.")
        st.dataframe(pd.DataFrame([_stat_row(s) for s in char_stats]), width="stretch", hide_index=True)
    with tab_info:
        st.dataframe(pd.DataFrame([_stat_row(s) for s in info_stats]), width="stretch", hide_index=True)
    with tab_needs:
        st.dataframe(pd.DataFrame([_stat_row(s) for s in need_stats]), width="stretch", hide_index=True)
    with tab_pres:
        st.dataframe(pd.DataFrame([_stat_row(s) for s in pres_stats]), width="stretch", hide_index=True)
    with tab_disagree:
        if char_disagreements:
            st.dataframe(_disagreements_df(char_disagreements), width="stretch", hide_index=True)
            st.caption(
                "Characteristics disagreements only -- domain-level (information coverage/"
                "older-adult needs/presentation) disagreements are reflected in each tab's "
                "agreement % and kappa above."
            )
        else:
            st.success("No characteristics disagreements among double-coded videos.")

st.markdown("---")
st.caption(
    "Interpretation guide: kappa > 0.80 almost perfect, 0.61-0.80 substantial, 0.41-0.60 "
    "moderate, 0.21-0.40 fair, < 0.21 slight/poor (Landis & Koch, 1977). Kappa is undefined "
    "when a field has fewer than two pairs or no variation across raters."
)

db.close()
