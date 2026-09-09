from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from components.video_player import embed_video
from db import crud
from db.database import get_session
from services import screening_service
from utils.constants import EXCLUSION_REASONS
from utils.helpers import format_duration

STATUS_ICONS = {
    screening_service.STATUS_NOT_SCREENED: "⚪",
    screening_service.STATUS_INCLUDED: "🟢",
    screening_service.STATUS_EXCLUDED: "🔴",
    screening_service.STATUS_UNSURE: "🟡",
}

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Screening", "Determine which unique videos are eligible for content analysis.")

if not require_study(current_study):
    st.stop()

study_id = current_study.id

all_videos = crud.list_videos(db, study_id)
if not all_videos:
    st.info(
        "No videos to screen yet. Run a full search first (see Full search results)."
    )
    db.close()
    st.stop()

decisions = crud.list_screening_decisions(db, study_id)

# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

progress = screening_service.compute_progress(all_videos, decisions)
p1, p2, p3, p4, p5 = st.columns(5)
p1.metric("Total", progress.total)
p2.metric("Not screened", progress.not_screened)
p3.metric("Included", progress.included)
p4.metric("Excluded", progress.excluded)
p5.metric("Unsure", progress.unsure)

st.markdown("---")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

reviewers = crud.list_reviewers(db)
filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
status_filter = filter_col1.selectbox(
    "Filter by status",
    ["All", screening_service.STATUS_NOT_SCREENED, screening_service.STATUS_INCLUDED,
     screening_service.STATUS_EXCLUDED, screening_service.STATUS_UNSURE],
)
reviewer_filter_options = {0: "All reviewers"} | {r.id: r.name for r in reviewers}
reviewer_filter = filter_col2.selectbox(
    "Filter by reviewer",
    options=list(reviewer_filter_options.keys()),
    format_func=lambda rid: reviewer_filter_options[rid],
)
if filter_col3.button("▶ Resume last unscreened"):
    next_unscreened = next(
        (v for v in all_videos if screening_service.screening_status(decisions.get(v.id))
         == screening_service.STATUS_NOT_SCREENED),
        None,
    )
    if next_unscreened:
        st.session_state["screening_current_video_pk"] = next_unscreened.id
        st.rerun()
    else:
        st.toast("All videos have been screened.", icon="✅")

st.caption(
    "There's no transport-mode filter here — that's assigned during Video coding, which "
    "happens after screening."
)

filtered = [
    v for v in all_videos
    if (status_filter == "All" or screening_service.screening_status(decisions.get(v.id)) == status_filter)
    and (reviewer_filter == 0 or (decisions.get(v.id) and decisions[v.id].reviewer_id == reviewer_filter))
]

if not filtered:
    st.success("No videos match this filter.")
    db.close()
    st.stop()

# ---------------------------------------------------------------------------
# Current video selection
# ---------------------------------------------------------------------------

current_pk = st.session_state.get("screening_current_video_pk")
filtered_ids = [v.id for v in filtered]
if current_pk not in filtered_ids:
    current_pk = filtered_ids[0]
idx = filtered_ids.index(current_pk)

jump_labels = {
    v.id: f"{STATUS_ICONS[screening_service.screening_status(decisions.get(v.id))]} {v.title[:70]}"
    for v in filtered
}
jump_pk = st.selectbox(
    "Jump to video",
    options=filtered_ids,
    format_func=lambda vpk: jump_labels[vpk],
    index=idx,
)
if jump_pk != current_pk:
    current_pk = jump_pk
    idx = filtered_ids.index(current_pk)
st.session_state["screening_current_video_pk"] = current_pk

current_video = crud.get_video(db, current_pk)
current_decision = decisions.get(current_pk)
st.caption(f"Video {idx + 1} of {len(filtered)} (filtered) — {len(all_videos)} total")

# ---------------------------------------------------------------------------
# Video + screening form
# ---------------------------------------------------------------------------

col_video, col_form = st.columns([3, 2])

with col_video:
    embed_video(current_video.video_id)
    st.markdown(f"**{current_video.title}**")
    meta_bits = [current_video.channel_title or ""]
    if current_video.published_at:
        meta_bits.append(current_video.published_at.strftime("%Y-%m-%d"))
    meta_bits.append(format_duration(current_video.duration_seconds))
    st.caption(" · ".join(b for b in meta_bits if b))

    raw_rows = crud.list_raw_results_for_video(db, study_id, current_video.video_id)
    query_lookup = {q.id: q.query_text for q in crud.list_search_queries(db, study_id)}
    queries_found_by = sorted({query_lookup.get(r.query_id, "(deleted query)") for r in raw_rows})
    if queries_found_by:
        st.caption("Found by: " + ", ".join(queries_found_by))

    if current_video.description:
        with st.expander("Description"):
            st.write(current_video.description)

    if current_video.video_url:
        st.link_button("Open on YouTube", current_video.video_url)

with col_form:
    decision_options = ["Include", "Exclude", "Unsure"]
    default_decision = (
        current_decision.decision if current_decision and current_decision.decision in decision_options
        else "Include"
    )
    decision = st.radio(
        "Screening decision",
        decision_options,
        index=decision_options.index(default_decision),
        key=f"decision_{current_pk}",
        horizontal=True,
    )

    exclusion_reason = None
    if decision == "Exclude":
        default_reason = (
            current_decision.exclusion_reason
            if current_decision and current_decision.exclusion_reason in EXCLUSION_REASONS
            else EXCLUSION_REASONS[0]
        )
        exclusion_reason = st.selectbox(
            "Exclusion reason",
            EXCLUSION_REASONS,
            index=EXCLUSION_REASONS.index(default_reason),
            key=f"exclusion_reason_{current_pk}",
        )

    notes = st.text_area(
        "Screening notes",
        value=(current_decision.notes if current_decision else "") or "",
        key=f"screening_notes_{current_pk}",
    )

    if current_decision and current_decision.screened_at:
        st.caption(
            f"First screened {current_decision.screened_at:%Y-%m-%d %H:%M}"
            + (f", last updated {current_decision.updated_at:%Y-%m-%d %H:%M}"
               if current_decision.updated_at else "")
        )

    def _save(advance: bool):
        crud.upsert_screening_decision(
            db,
            study_id=study_id,
            video_pk=current_pk,
            reviewer_id=current_reviewer.id if current_reviewer else None,
            decision=decision,
            exclusion_reason=exclusion_reason,
            notes=notes or None,
        )
        if advance and idx < len(filtered) - 1:
            st.session_state["screening_current_video_pk"] = filtered_ids[idx + 1]
        st.rerun()

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("◀ Previous", disabled=idx == 0):
        st.session_state["screening_current_video_pk"] = filtered_ids[idx - 1]
        st.rerun()
    if b2.button("Save"):
        _save(advance=False)
    if b3.button("Save & next ▶", type="primary"):
        _save(advance=True)
    if b4.button("Next ▶", disabled=idx == len(filtered) - 1):
        st.session_state["screening_current_video_pk"] = filtered_ids[idx + 1]
        st.rerun()

db.close()
