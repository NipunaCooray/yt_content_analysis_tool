from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from components.video_player import embed_video
from db import crud
from db.database import get_session
from services import accuracy_service
from utils.constants import ACCURACY_VALUES, CLAIM_CATEGORIES
from utils.helpers import format_duration

STATUS_ICONS = {
    accuracy_service.STATUS_NOT_STARTED: "⚪",
    accuracy_service.STATUS_IN_PROGRESS: "🟡",
    accuracy_service.STATUS_COMPLETE: "🟢",
}

ASSESSMENT_ICONS = {
    "Correct": "✅",
    "Correct but incomplete": "🟡",
    "Outdated": "🕒",
    "Incorrect": "❌",
    "Unverifiable": "❓",
}

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header(
    "Accuracy assessment",
    "Assess factual/instructional claims at claim level against official sources.",
)

if not require_study(current_study):
    st.stop()

study_id = current_study.id

included_videos = crud.list_included_videos(db, study_id)
if not included_videos:
    st.info(
        "No included videos yet. Mark videos as **Include** on the Screening page first — "
        "only included videos enter accuracy assessment."
    )
    db.close()
    st.stop()

review_statuses = crud.list_accuracy_review_statuses(db, study_id)
claim_counts = crud.count_accuracy_claims(db, study_id)

# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

progress = accuracy_service.compute_progress(
    [v.id for v in included_videos], review_statuses, claim_counts
)
p1, p2, p3, p4 = st.columns(4)
p1.metric("Included videos", progress.total)
p2.metric("Not started", progress.not_started)
p3.metric("In progress", progress.in_progress)
p4.metric("Complete", progress.complete)

st.markdown("---")

# ---------------------------------------------------------------------------
# Filters + navigation
# ---------------------------------------------------------------------------

filter_col1, filter_col2 = st.columns([2, 1])
status_filter = filter_col1.selectbox(
    "Filter by status",
    ["All", accuracy_service.STATUS_NOT_STARTED, accuracy_service.STATUS_IN_PROGRESS,
     accuracy_service.STATUS_COMPLETE],
)
if filter_col2.button("▶ Resume last incomplete"):
    next_incomplete = next(
        (v for v in included_videos
         if accuracy_service.accuracy_status(review_statuses.get(v.id), claim_counts.get(v.id, 0))
         != accuracy_service.STATUS_COMPLETE),
        None,
    )
    if next_incomplete:
        st.session_state["accuracy_current_video_pk"] = next_incomplete.id
        st.rerun()
    else:
        st.toast("All included videos have a completed accuracy review.", icon="✅")

filtered = [
    v for v in included_videos
    if status_filter == "All"
    or accuracy_service.accuracy_status(review_statuses.get(v.id), claim_counts.get(v.id, 0))
    == status_filter
]

if not filtered:
    st.success("No videos match this filter.")
    db.close()
    st.stop()

current_pk = st.session_state.get("accuracy_current_video_pk")
filtered_ids = [v.id for v in filtered]
if current_pk not in filtered_ids:
    current_pk = filtered_ids[0]
idx = filtered_ids.index(current_pk)

jump_labels = {
    v.id: (
        f"{STATUS_ICONS[accuracy_service.accuracy_status(review_statuses.get(v.id), claim_counts.get(v.id, 0))]} "
        f"{v.title[:65]} ({claim_counts.get(v.id, 0)} claim{'s' if claim_counts.get(v.id, 0) != 1 else ''})"
    )
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
st.session_state["accuracy_current_video_pk"] = current_pk

current_video = crud.get_video(db, current_pk)
current_review_status = review_statuses.get(current_pk)
st.caption(f"Video {idx + 1} of {len(filtered)} (filtered) — {len(included_videos)} included total")

# ---------------------------------------------------------------------------
# Video + claims
# ---------------------------------------------------------------------------

col_video, col_form = st.columns([2, 3])

with col_video:
    embed_video(current_video.video_id)
    st.markdown(f"**{current_video.title}**")
    meta_bits = [current_video.channel_title or ""]
    if current_video.published_at:
        meta_bits.append(current_video.published_at.strftime("%Y-%m-%d"))
    meta_bits.append(format_duration(current_video.duration_seconds))
    st.caption(" · ".join(b for b in meta_bits if b))
    if current_video.description:
        with st.expander("Description"):
            st.write(current_video.description)
    if current_video.video_url:
        st.link_button("Open on YouTube", current_video.video_url)

    is_complete = bool(current_review_status and current_review_status.is_complete)
    if is_complete:
        st.success(
            f"Accuracy review marked complete"
            + (f" ({current_review_status.completed_at:%Y-%m-%d %H:%M})"
               if current_review_status.completed_at else "")
        )
        if st.button("↩ Reopen review"):
            crud.set_accuracy_review_complete(
                db, study_id=study_id, video_pk=current_pk,
                reviewer_id=current_reviewer.id if current_reviewer else None, is_complete=False,
            )
            st.rerun()
    else:
        if st.button("✅ Mark accuracy review complete", type="primary"):
            crud.set_accuracy_review_complete(
                db, study_id=study_id, video_pk=current_pk,
                reviewer_id=current_reviewer.id if current_reviewer else None, is_complete=True,
            )
            st.rerun()

with col_form:
    claims = crud.list_accuracy_claims(db, study_id, current_pk)

    st.markdown(f"#### Claims ({len(claims)})")
    if not claims:
        st.caption("No claims recorded yet for this video.")

    for claim in claims:
        icon = ASSESSMENT_ICONS.get(claim.assessment, "")
        with st.expander(f"{icon} {claim.claim_text[:70]}"):
            with st.form(f"edit_claim_{claim.id}"):
                claim_text = st.text_area(
                    "Claim text*", value=claim.claim_text, key=f"claim_text_{claim.id}"
                )
                col1, col2 = st.columns(2)
                category = col1.selectbox(
                    "Category", CLAIM_CATEGORIES,
                    index=CLAIM_CATEGORIES.index(claim.category)
                    if claim.category in CLAIM_CATEGORIES else 0,
                    key=f"category_{claim.id}",
                )
                assessment = col2.selectbox(
                    "Assessment", ACCURACY_VALUES,
                    index=ACCURACY_VALUES.index(claim.assessment)
                    if claim.assessment in ACCURACY_VALUES else 0,
                    key=f"assessment_{claim.id}",
                )
                source_url = st.text_input(
                    "Official source URL", value=claim.official_source_url or "",
                    key=f"source_{claim.id}",
                )
                notes = st.text_area(
                    "Notes", value=claim.notes or "", key=f"claim_notes_{claim.id}"
                )

                b1, b2 = st.columns(2)
                save = b1.form_submit_button("Save", type="primary")
                delete = b2.form_submit_button("Delete claim")

                if save:
                    if not claim_text.strip():
                        st.error("Claim text is required.")
                    else:
                        crud.update_accuracy_claim(
                            db, claim.id,
                            claim_text=claim_text.strip(),
                            category=category,
                            assessment=assessment,
                            official_source_url=source_url or None,
                            notes=notes or None,
                        )
                        st.success("Claim updated.")
                        st.rerun()

                if delete:
                    crud.delete_accuracy_claim(db, claim.id)
                    st.warning("Claim deleted.")
                    st.rerun()

            if claim.official_source_url:
                st.link_button("Open source URL", claim.official_source_url)

    st.markdown("#### Add a new claim")
    with st.form(f"add_claim_{current_pk}", clear_on_submit=True):
        new_claim_text = st.text_area("Claim text*", placeholder='"You need an Opal card to catch the bus."')
        col1, col2 = st.columns(2)
        new_category = col1.selectbox("Category", CLAIM_CATEGORIES, index=0, key="new_category")
        new_assessment = col2.selectbox("Assessment", ACCURACY_VALUES, index=0, key="new_assessment")
        new_source_url = st.text_input("Official source URL", key="new_source_url")
        new_notes = st.text_area("Notes", key="new_claim_notes")
        add_submitted = st.form_submit_button("Add claim", type="primary")

        if add_submitted:
            if not new_claim_text.strip():
                st.error("Claim text is required.")
            else:
                crud.create_accuracy_claim(
                    db,
                    study_id=study_id,
                    video_pk=current_pk,
                    reviewer_id=current_reviewer.id if current_reviewer else None,
                    claim_text=new_claim_text.strip(),
                    category=new_category,
                    assessment=new_assessment,
                    official_source_url=new_source_url or None,
                    notes=new_notes or None,
                )
                st.success("Claim added.")
                st.rerun()

    st.markdown("---")
    nav1, nav2 = st.columns(2)
    if nav1.button("◀ Previous", disabled=idx == 0):
        st.session_state["accuracy_current_video_pk"] = filtered_ids[idx - 1]
        st.rerun()
    if nav2.button("Next ▶", disabled=idx == len(filtered) - 1):
        st.session_state["accuracy_current_video_pk"] = filtered_ids[idx + 1]
        st.rerun()

db.close()
