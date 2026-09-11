from __future__ import annotations

import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from components.video_player import embed_video
from db import crud
from db.database import get_session
from services import coding_service
from utils.constants import (
    AUDIENCE_TYPES,
    COVERAGE_VALUES,
    INFORMATION_DOMAINS,
    JURISDICTIONS,
    NEED_VALUES,
    OLDER_ADULT_NEEDS,
    PRESENTATION_ITEMS,
    PRESENTATION_VALUES,
    TRANSPORT_MODES,
    UPLOADER_TYPES,
    YES_NO_UNCLEAR,
)
from utils.helpers import format_duration

STATUS_ICONS = {
    coding_service.STATUS_NOT_STARTED: "⚪",
    coding_service.STATUS_IN_PROGRESS: "🟡",
    coding_service.STATUS_COMPLETE: "🟢",
}

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header(
    "Video coding",
    "Code included videos for characteristics, information coverage, older-adult needs, "
    "and presentation.",
)

if not require_study(current_study):
    db.close()
    st.stop()

if current_reviewer is None:
    st.warning(
        "Select a reviewer in the sidebar before coding — each reviewer's coding is kept "
        "separately so a second reviewer's coding never overwrites the first's (needed for "
        "double coding; see the Reliability page).",
        icon="👤",
    )
    db.close()
    st.stop()

study_id = current_study.id

included_videos = crud.list_included_videos(db, study_id)
if not included_videos:
    st.info(
        "No included videos yet. Mark videos as **Include** on the Screening page first — "
        "only included videos enter coding."
    )
    db.close()
    st.stop()

# Canonical (earliest-reviewer) coding drives study-wide progress/gating;
# this reviewer's own coding drives their personal queue below.
canonical_codings = crud.list_video_codings(db, study_id)
my_codings = crud.list_video_codings_for_reviewer(db, study_id, current_reviewer.id)
double_coding_sample = crud.list_double_coding_sample_video_ids(db, study_id, "coding")

# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

progress = coding_service.compute_progress([v.id for v in included_videos], canonical_codings)
p1, p2, p3, p4 = st.columns(4)
p1.metric("Included videos", progress.total)
p2.metric("Not started", progress.not_started)
p3.metric("In progress", progress.in_progress)
p4.metric("Complete", progress.complete)
my_complete = sum(
    1 for v in included_videos
    if coding_service.coding_status(my_codings.get(v.id)) == coding_service.STATUS_COMPLETE
)
st.caption(f"Your progress ({current_reviewer.name}): {my_complete} of {len(included_videos)} complete.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Filters + navigation
# ---------------------------------------------------------------------------

filter_col1, filter_col2 = st.columns([2, 1])
status_filter = filter_col1.selectbox(
    "Filter by your status",
    ["All", coding_service.STATUS_NOT_STARTED, coding_service.STATUS_IN_PROGRESS,
     coding_service.STATUS_COMPLETE],
)
if filter_col2.button("▶ Resume last uncoded"):
    next_uncoded = next(
        (v for v in included_videos
         if coding_service.coding_status(my_codings.get(v.id)) != coding_service.STATUS_COMPLETE),
        None,
    )
    if next_uncoded:
        st.session_state["coding_current_video_pk"] = next_uncoded.id
        st.rerun()
    else:
        st.toast("You've fully coded every included video.", icon="✅")

sample_only = st.checkbox(
    f"Double-coding sample only ({len(double_coding_sample)} video(s) selected — see Reliability page)"
)

filtered = [
    v for v in included_videos
    if (status_filter == "All"
        or coding_service.coding_status(my_codings.get(v.id)) == status_filter)
    and (not sample_only or v.id in double_coding_sample)
]

if not filtered:
    st.success("No videos match this filter.")
    db.close()
    st.stop()

current_pk = st.session_state.get("coding_current_video_pk")
filtered_ids = [v.id for v in filtered]
if current_pk not in filtered_ids:
    current_pk = filtered_ids[0]
idx = filtered_ids.index(current_pk)

jump_labels = {
    v.id: f"{STATUS_ICONS[coding_service.coding_status(my_codings.get(v.id))]} "
    f"{'🔁 ' if v.id in double_coding_sample else ''}{v.title[:65]}"
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
st.session_state["coding_current_video_pk"] = current_pk

current_video = crud.get_video(db, current_pk)
my_current_coding = my_codings.get(current_pk)
st.caption(f"Video {idx + 1} of {len(filtered)} (filtered) — {len(included_videos)} included total")
if current_pk in double_coding_sample:
    st.info("🔁 This video is in the double-coding sample.", icon="🔁")

# ---------------------------------------------------------------------------
# Video + coding form
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

    # Other reviewers' coding is only revealed once *you* have coded this
    # video yourself -- keeps double coding blind until completion (study-
    # initiation guide section 42).
    if my_current_coding is not None:
        all_codings = crud.list_video_codings_for_video(db, current_pk)
        others = [c for c in all_codings if c.reviewer_id != current_reviewer.id]
        if others:
            reviewer_names = {r.id: r.name for r in crud.list_reviewers(db)}
            with st.expander(f"Other reviewers' coding ({len(others)})"):
                for c in others:
                    st.write(f"**{reviewer_names.get(c.reviewer_id, 'Unknown')}**")
                    st.caption(
                        f"Modes: {', '.join(c.transport_modes_json or []) or '—'} · "
                        f"Jurisdictions: {', '.join(c.jurisdictions_json or []) or '—'} · "
                        f"Uploader: {c.uploader_type or '—'} · Audience: {c.intended_audience or '—'} · "
                        f"Older-adult targeted: {c.older_adult_targeted or '—'}"
                    )
                st.caption("Full field-by-field comparison is on the Reliability page.")

with col_form:
    tab_char, tab_info, tab_needs, tab_pres = st.tabs(
        ["Characteristics", "Information coverage", "Older-adult needs", "Presentation"]
    )

    with tab_char:
        default_modes = my_current_coding.transport_modes_json if my_current_coding else []
        transport_modes = st.multiselect(
            "Transport mode(s)", TRANSPORT_MODES,
            default=[m for m in (default_modes or []) if m in TRANSPORT_MODES],
            key=f"modes_{current_pk}",
        )
        default_jurisdictions = my_current_coding.jurisdictions_json if my_current_coding else []
        jurisdictions = st.multiselect(
            "Jurisdiction(s)", JURISDICTIONS,
            default=[j for j in (default_jurisdictions or []) if j in JURISDICTIONS],
            key=f"jurisdictions_{current_pk}",
        )
        uploader_type = st.selectbox(
            "Uploader type", UPLOADER_TYPES,
            index=UPLOADER_TYPES.index(my_current_coding.uploader_type)
            if my_current_coding and my_current_coding.uploader_type in UPLOADER_TYPES else 0,
            key=f"uploader_{current_pk}",
        )
        intended_audience = st.selectbox(
            "Audience", AUDIENCE_TYPES,
            index=AUDIENCE_TYPES.index(my_current_coding.intended_audience)
            if my_current_coding and my_current_coding.intended_audience in AUDIENCE_TYPES else 0,
            key=f"audience_{current_pk}",
        )
        older_adult_targeted = st.radio(
            "Specifically aimed at older adults?", YES_NO_UNCLEAR,
            index=YES_NO_UNCLEAR.index(my_current_coding.older_adult_targeted)
            if my_current_coding and my_current_coding.older_adult_targeted in YES_NO_UNCLEAR else 2,
            key=f"oa_targeted_{current_pk}",
            horizontal=True,
        )
        char_notes = st.text_area(
            "Notes", value=(my_current_coding.notes if my_current_coding else "") or "",
            key=f"char_notes_{current_pk}",
        )

    def _domain_section(title: str, names: list[str], values: list[str], existing: dict, key_prefix: str):
        st.caption(title)
        results: dict[str, tuple[str, str | None]] = {}
        for name in names:
            row = existing.get(name)
            c1, c2, c3 = st.columns([3, 2, 3])
            c1.markdown(f"<div style='padding-top:0.5rem'>{name}</div>", unsafe_allow_html=True)
            default_value = row.value if row and row.value in values else values[-1]
            value = c2.selectbox(
                name, values, index=values.index(default_value),
                key=f"{key_prefix}_{name}_{current_pk}", label_visibility="collapsed",
            )
            note = c3.text_input(
                f"{name} notes", value=(row.notes if row else "") or "",
                key=f"{key_prefix}_notes_{name}_{current_pk}",
                placeholder="Notes (optional)", label_visibility="collapsed",
            )
            results[name] = (value, note or None)
        return results

    with tab_info:
        existing_domains = (
            crud.list_information_domain_codes(db, my_current_coding.id) if my_current_coding else {}
        )
        information_domain_values = _domain_section(
            "For each domain, is this information present in the video?",
            INFORMATION_DOMAINS, COVERAGE_VALUES, existing_domains, "domain",
        )

    with tab_needs:
        existing_needs = (
            crud.list_older_adult_need_codes(db, my_current_coding.id) if my_current_coding else {}
        )
        older_adult_need_values = _domain_section(
            "For each need, is it addressed in the video?",
            OLDER_ADULT_NEEDS, NEED_VALUES, existing_needs, "need",
        )

    with tab_pres:
        existing_presentation = (
            crud.list_presentation_codes(db, my_current_coding.id) if my_current_coding else {}
        )
        presentation_values = _domain_section(
            "How is the information presented?",
            PRESENTATION_ITEMS, PRESENTATION_VALUES, existing_presentation, "presentation",
        )

    st.markdown("---")
    mark_complete = st.checkbox(
        "Mark this video's coding as complete",
        value=coding_service.coding_status(my_current_coding) == coding_service.STATUS_COMPLETE,
        key=f"mark_complete_{current_pk}",
    )

    def _save(advance: bool):
        coding_service.save_video_coding(
            db,
            study_id=study_id,
            video_pk=current_pk,
            reviewer_id=current_reviewer.id,
            transport_modes=transport_modes,
            jurisdictions=jurisdictions,
            uploader_type=uploader_type,
            intended_audience=intended_audience,
            older_adult_targeted=older_adult_targeted,
            notes=char_notes or None,
            information_domain_values=information_domain_values,
            older_adult_need_values=older_adult_need_values,
            presentation_values=presentation_values,
            mark_complete=mark_complete,
        )
        if advance and idx < len(filtered) - 1:
            st.session_state["coding_current_video_pk"] = filtered_ids[idx + 1]
        st.rerun()

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("◀ Previous", disabled=idx == 0):
        st.session_state["coding_current_video_pk"] = filtered_ids[idx - 1]
        st.rerun()
    if b2.button("Save"):
        _save(advance=False)
    if b3.button("Save & next ▶", type="primary"):
        _save(advance=True)
    if b4.button("Next ▶", disabled=idx == len(filtered) - 1):
        st.session_state["coding_current_video_pk"] = filtered_ids[idx + 1]
        st.rerun()

db.close()
