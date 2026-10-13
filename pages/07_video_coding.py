from __future__ import annotations

import streamlit as st

from components.navigation import close_and_rerun, page_header, render_context_sidebar, require_study
from components.video_player import embed_video
from db import crud
from db.database import get_session
from services import coding_service
from utils.constants import (
    ACCURACY_NOTES_HELP,
    ACCURACY_NOTES_LABEL,
    AUDIENCE_TYPES,
    INFORMATION_COVERAGE_CATEGORIES,
    INFORMATION_COVERAGE_ITEMS,
    INFORMATION_COVERAGE_VALUES,
    JURISDICTIONS,
    OLDER_ADULT_NEED_ITEMS,
    OLDER_ADULT_NEED_VALUES,
    OLDER_ADULT_NEEDS_NOTE_PROMPT,
    OLDER_ADULT_NEEDS_PROMPT,
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
    "Code included videos for characteristics, information coverage, and older-adult needs.",
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

filter_col1, filter_col2 = st.columns([2, 1], vertical_alignment="bottom")
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
        close_and_rerun(db)
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
    # This reviewer's saved item codes. Rows from the pre-revision framework
    # (stored under legacy names) are simply never looked up below, so they
    # stay untouched in the database.
    existing_domains = (
        crud.list_information_domain_codes(db, my_current_coding.id) if my_current_coding else {}
    )
    existing_needs = (
        crud.list_older_adult_need_codes(db, my_current_coding.id) if my_current_coding else {}
    )

    def _saved(rows: dict, key: str, field: str):
        row = rows.get(key)
        return getattr(row, field) if row else None

    if coding_service.coding_status(my_current_coding) == coding_service.STATUS_COMPLETE and (
        coding_service.missing_for_completion(
            {i.key: _saved(existing_domains, i.key, "value") for i in INFORMATION_COVERAGE_ITEMS},
            {i.key: _saved(existing_needs, i.key, "value") for i in OLDER_ADULT_NEED_ITEMS},
        )
    ):
        st.info(
            "This video was marked complete under the previous coding framework. The revised "
            "information-coverage and older-adult-needs items are uncoded -- code them and save "
            "to keep it complete.",
            icon=":material/info:",
        )

    tab_char, tab_info, tab_needs = st.tabs(
        ["Characteristics", "Information coverage", "Older-adult needs"]
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
        accuracy_notes = st.text_area(
            ACCURACY_NOTES_LABEL,
            value=(my_current_coding.accuracy_notes if my_current_coding else "") or "",
            key=f"accuracy_notes_{current_pk}",
        )
        st.caption(ACCURACY_NOTES_HELP)

    with tab_info:
        st.caption("For each item, is this information present in the video?")
        information_domain_values: dict[str, tuple[str | None, str | None]] = {}
        for group_index, category in enumerate(INFORMATION_COVERAGE_CATEGORIES):
            items = [i for i in INFORMATION_COVERAGE_ITEMS if i.category == category]
            value_keys = {i.key: f"ic_{i.key}_{current_pk}" for i in items}
            # Count from widget state when it exists (this rerun's edits),
            # otherwise from what's saved -- so the label stays current.
            n_coded = sum(
                1 for i in items
                if st.session_state.get(value_keys[i.key], _saved(existing_domains, i.key, "value"))
            )
            all_coded = n_coded == len(items)
            with st.expander(
                f"{category} · {n_coded}/{len(items)} coded",
                icon=":material/check_circle:" if all_coded else None,
                # Keyed so the label's changing count doesn't remount (and
                # collapse) the expander mid-coding.
                key=f"ic_group_{group_index}_{current_pk}",
            ):
                for item in items:
                    saved_value = _saved(existing_domains, item.key, "value")
                    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
                    with c1:
                        value = st.segmented_control(
                            item.label, INFORMATION_COVERAGE_VALUES,
                            default=saved_value if saved_value in INFORMATION_COVERAGE_VALUES else None,
                            key=value_keys[item.key], help=item.help,
                        )
                    with c2:
                        note = st.text_input(
                            f"{item.label} notes",
                            value=_saved(existing_domains, item.key, "notes") or "",
                            key=f"ic_notes_{item.key}_{current_pk}",
                            placeholder="Notes (optional)", label_visibility="collapsed",
                        )
                    information_domain_values[item.key] = (value, note or None)

    with tab_needs:
        st.caption(OLDER_ADULT_NEEDS_PROMPT)
        older_adult_need_values: dict[str, tuple[str | None, str | None]] = {}
        for item in OLDER_ADULT_NEED_ITEMS:
            with st.container(border=True):
                saved_value = _saved(existing_needs, item.key, "value")
                mentioned = st.segmented_control(
                    item.label, OLDER_ADULT_NEED_VALUES,
                    default=saved_value if saved_value in OLDER_ADULT_NEED_VALUES else None,
                    key=f"need_{item.key}_{current_pk}",
                )
                note = None
                if mentioned == "Yes":
                    note = st.text_area(
                        OLDER_ADULT_NEEDS_NOTE_PROMPT,
                        value=_saved(existing_needs, item.key, "notes") or "",
                        key=f"need_notes_{item.key}_{current_pk}",
                        height=80,
                    )
                older_adult_need_values[item.key] = (mentioned, note or None)

    st.markdown("---")
    incomplete_warning = st.session_state.pop("coding_incomplete_warning", None)
    if incomplete_warning:
        st.warning(incomplete_warning, icon=":material/warning:")
    mark_complete = st.checkbox(
        "Mark this video's coding as complete",
        value=coding_service.coding_status(my_current_coding) == coding_service.STATUS_COMPLETE,
        key=f"mark_complete_{current_pk}",
    )

    def _save(advance: bool):
        saved = coding_service.save_video_coding(
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
            accuracy_notes=accuracy_notes or None,
            information_domain_values=information_domain_values,
            older_adult_need_values=older_adult_need_values,
            mark_complete=mark_complete,
        )
        if mark_complete and saved.status != coding_service.STATUS_COMPLETE:
            missing = coding_service.missing_for_completion(
                {k: v for k, (v, _) in information_domain_values.items()},
                {k: v for k, (v, _) in older_adult_need_values.items()},
            )
            shown = "; ".join(missing[:5]) + (f"; and {len(missing) - 5} more" if len(missing) > 5 else "")
            st.session_state["coding_incomplete_warning"] = (
                f"Saved \"{current_video.title}\" as in progress, not complete -- "
                f"{len(missing)} item(s) still uncoded: {shown}."
            )
        if advance and idx < len(filtered) - 1:
            st.session_state["coding_current_video_pk"] = filtered_ids[idx + 1]
        close_and_rerun(db)

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("◀ Previous", disabled=idx == 0):
        st.session_state["coding_current_video_pk"] = filtered_ids[idx - 1]
        close_and_rerun(db)
    if b2.button("Save"):
        _save(advance=False)
    if b3.button("Save & next ▶", type="primary"):
        _save(advance=True)
    if b4.button("Next ▶", disabled=idx == len(filtered) - 1):
        st.session_state["coding_current_video_pk"] = filtered_ids[idx + 1]
        close_and_rerun(db)

db.close()
