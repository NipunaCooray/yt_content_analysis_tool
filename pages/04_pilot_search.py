from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from components.video_player import video_thumbnail
from db import crud
from db.database import get_session
from services import pilot_service
from services.youtube_api import api_key_configured, estimate_search_calls
from utils.constants import IRRELEVANCE_REASONS, PILOT_RESULT_COUNT_OPTIONS, SEARCH_ORDER_OPTIONS

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header(
    "Pilot search",
    "Test the search strategy on a small sample, rate relevance, refine queries, and approve.",
)

if not require_study(current_study):
    st.stop()

study_id = current_study.id

active_queries = crud.list_search_queries(db, study_id, active_only=True)
all_runs = crud.list_pilot_search_runs(db, study_id)

# ---------------------------------------------------------------------------
# Run a new pilot search
# ---------------------------------------------------------------------------

with st.expander("Run a new pilot search", expanded=not all_runs):
    if not active_queries:
        st.info("No active queries yet. Add some in Search strategy first.")
    elif not api_key_configured():
        st.error(
            "No YouTube API key configured. Add YOUTUBE_API_KEY to your .env file "
            "(see Settings) before running a search."
        )
    else:
        query_options = {q.id: q.query_text for q in active_queries}
        selected_ids = st.multiselect(
            "Queries to include",
            options=list(query_options.keys()),
            default=list(query_options.keys()),
            format_func=lambda qid: query_options[qid],
        )
        col1, col2 = st.columns(2)
        results_per_query = col1.selectbox(
            "Results per query",
            PILOT_RESULT_COUNT_OPTIONS,
            index=PILOT_RESULT_COUNT_OPTIONS.index(10)
            if 10 in PILOT_RESULT_COUNT_OPTIONS
            else 0,
        )
        search_order = col2.selectbox(
            "Search order", SEARCH_ORDER_OPTIONS, index=SEARCH_ORDER_OPTIONS.index("relevance")
        )
        run_notes = st.text_input("Notes for this pilot run (optional)")

        est_calls = estimate_search_calls(len(selected_ids), int(results_per_query))
        st.caption(
            f"Estimated API usage: ~{est_calls} search call(s) "
            f"(~{est_calls * 100} search-quota units)."
        )

        if st.button("Run pilot search", type="primary", disabled=not selected_ids):
            queries_to_run = [q for q in active_queries if q.id in selected_ids]
            with st.spinner(f"Running pilot search across {len(queries_to_run)} quer(y/ies)..."):
                outcome = pilot_service.run_pilot_search(
                    db,
                    study_id=study_id,
                    queries=queries_to_run,
                    results_per_query=results_per_query,
                    search_order=search_order,
                    reviewer_id=current_reviewer.id if current_reviewer else None,
                    notes=run_notes or None,
                )
            if current_study.search_status == "Draft":
                crud.update_study(db, study_id, search_status="Pilot testing")
            st.session_state["pilot_run_id"] = outcome.run_id
            if outcome.errors:
                st.warning(
                    f"Saved {outcome.results_saved} result(s), but {len(outcome.errors)} "
                    f"quer(y/ies) failed:\n\n" + "\n".join(f"- {e}" for e in outcome.errors)
                )
            else:
                st.success(f"Pilot run complete: {outcome.results_saved} results saved.")
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------------------
# Select a pilot run to review
# ---------------------------------------------------------------------------

if not all_runs:
    st.info("No pilot runs yet. Run one above.")
    db.close()
    st.stop()

run_options = {
    r.id: f"Run #{r.id} — {r.run_timestamp:%Y-%m-%d %H:%M} "
    f"({r.results_per_query}/query, order={r.search_order})"
    for r in all_runs
}
default_run_id = st.session_state.get("pilot_run_id", all_runs[0].id)
if default_run_id not in run_options:
    default_run_id = all_runs[0].id

selected_run_id = st.selectbox(
    "Pilot run",
    options=list(run_options.keys()),
    format_func=lambda rid: run_options[rid],
    index=list(run_options.keys()).index(default_run_id),
)
st.session_state["pilot_run_id"] = selected_run_id
selected_run = crud.get_pilot_search_run(db, selected_run_id)
if selected_run.notes:
    st.caption(f"Notes: {selected_run.notes}")

# ---------------------------------------------------------------------------
# Query performance summary
# ---------------------------------------------------------------------------

st.subheader("Query performance")
performance = pilot_service.compute_query_performance(db, selected_run_id)

if not performance:
    st.info("No results recorded for this pilot run.")
else:
    perf_df = pd.DataFrame(
        [
            {
                "Query": p.query_text,
                "Total": p.total,
                "Reviewed": p.reviewed,
                "Relevant": p.relevant,
                "Potential": p.potentially_relevant,
                "Irrelevant": p.irrelevant,
                "Relevant %": p.strict_relevance_rate,
                "Relevant+Potential %": p.broad_relevance_rate,
            }
            for p in performance
        ]
    )
    st.dataframe(perf_df, width='stretch', hide_index=True)
    st.caption(
        "Relevant % and Relevant+Potential % are calculated over *reviewed* results only. "
        "The tool does not decide whether a rate is 'good enough' — that's a research judgement."
    )

# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

with st.expander("Diagnostics"):
    diagnostics = pilot_service.compute_diagnostics(db, selected_run_id)
    d1, d2, d3 = st.columns(3)
    d1.metric("Total results", diagnostics.total_results)
    d2.metric("Unique videos", diagnostics.unique_videos)
    d3.metric("Duplicate videos (2+ queries)", len(diagnostics.duplicate_video_ids))

    if diagnostics.irrelevance_reason_counts:
        st.markdown("**Irrelevance reasons**")
        reasons_df = pd.DataFrame(
            sorted(diagnostics.irrelevance_reason_counts.items(), key=lambda x: -x[1]),
            columns=["Reason", "Count"],
        )
        st.dataframe(reasons_df, width='stretch', hide_index=True)

# ---------------------------------------------------------------------------
# Result review
# ---------------------------------------------------------------------------

st.subheader("Review results")

filter_col1, filter_col2 = st.columns(2)
query_filter_options = {0: "All queries"} | {p.query_id: p.query_text for p in performance}
query_filter = filter_col1.selectbox(
    "Filter by query", options=list(query_filter_options.keys()),
    format_func=lambda qid: query_filter_options[qid],
)
rating_filter = filter_col2.selectbox(
    "Filter by status",
    ["Not yet reviewed", "Relevant", "Potentially relevant", "Irrelevant", "All"],
)

results = crud.list_pilot_search_results(
    db,
    selected_run_id,
    relevance_rating=None if rating_filter == "All" else rating_filter,
    query_id=None if query_filter == 0 else query_filter,
)

if not results:
    st.success("No results match this filter — nothing left to review here.")
else:
    result_ids = [r.id for r in results]
    nav_key = f"pilot_review_idx_{selected_run_id}"
    idx = st.session_state.get(nav_key, 0)
    idx = max(0, min(idx, len(results) - 1))

    jump_labels = {i: f"{i+1}. {r.title[:70]}" for i, r in enumerate(results)}
    jump_idx = st.selectbox(
        "Jump to result",
        options=list(jump_labels.keys()),
        format_func=lambda i: jump_labels[i],
        index=idx,
    )
    if jump_idx != idx:
        idx = jump_idx
        st.session_state[nav_key] = idx

    current = results[idx]
    st.caption(f"Result {idx + 1} of {len(results)}")

    col_video, col_form = st.columns([1, 1])

    with col_video:
        video_thumbnail(current.thumbnail_url, current.video_url)
        st.markdown(f"**{current.title}**")
        st.write(current.channel_title or "")
        meta_bits = []
        if current.published_at:
            meta_bits.append(current.published_at.strftime("%Y-%m-%d"))
        query_obj = crud.get_search_query(db, current.query_id)
        if query_obj:
            meta_bits.append(f"query: {query_obj.query_text}")
        meta_bits.append(f"rank: {current.result_rank}")
        st.caption(" · ".join(meta_bits))
        if current.description:
            with st.expander("Description"):
                st.write(current.description)
        if current.video_url:
            st.link_button("Open on YouTube", current.video_url)

    with col_form:
        rating_options = ["Relevant", "Potentially relevant", "Irrelevant"]
        default_rating = (
            current.relevance_rating if current.relevance_rating in rating_options else "Relevant"
        )
        rating = st.radio(
            "Relevance",
            rating_options,
            index=rating_options.index(default_rating),
            key=f"rating_{current.id}",
        )
        reason = None
        if rating == "Irrelevant":
            default_reason = (
                current.irrelevance_reason
                if current.irrelevance_reason in IRRELEVANCE_REASONS
                else IRRELEVANCE_REASONS[0]
            )
            reason = st.selectbox(
                "Irrelevance reason",
                IRRELEVANCE_REASONS,
                index=IRRELEVANCE_REASONS.index(default_reason),
                key=f"reason_{current.id}",
            )
        notes = st.text_area(
            "Notes", value=current.reviewer_notes or "", key=f"notes_{current.id}"
        )

        def _save(advance: bool):
            crud.update_pilot_result_relevance(
                db,
                current.id,
                relevance_rating=rating,
                irrelevance_reason=reason,
                reviewer_notes=notes or None,
                reviewer_id=current_reviewer.id if current_reviewer else None,
            )
            if advance and idx < len(results) - 1:
                st.session_state[nav_key] = idx + 1
            st.rerun()

        b1, b2, b3, b4 = st.columns(4)
        if b1.button("◀ Previous", disabled=idx == 0):
            st.session_state[nav_key] = idx - 1
            st.rerun()
        if b2.button("Save"):
            _save(advance=False)
        if b3.button("Save & next ▶", type="primary"):
            _save(advance=True)
        if b4.button("Next ▶", disabled=idx == len(results) - 1):
            st.session_state[nav_key] = idx + 1
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------------------
# Approve search strategy
# ---------------------------------------------------------------------------

st.subheader("Approve search strategy")
approvals = crud.list_search_strategy_approvals(db, study_id)
if approvals:
    latest = approvals[0]
    st.caption(
        f"Last approved {latest.approved_at:%Y-%m-%d %H:%M} "
        f"with {len(latest.query_snapshot_json or [])} active quer(y/ies). "
        f"Study status: **{current_study.search_status}**."
    )
    st.warning(
        "Editing active queries after approval is allowed but will be logged. "
        "Re-approve once you're happy with the refined strategy.",
        icon="⚠️",
    )

st.write(
    f"Approving will snapshot the **{len(active_queries)} currently active** quer(y/ies) "
    "and mark the study 'Ready for full search'."
)
approve_notes = st.text_input("Approval notes (optional)", key="approve_notes")
if st.button("✅ Approve search strategy", type="primary", disabled=not active_queries):
    pilot_service.approve_search_strategy(
        db,
        study_id=study_id,
        reviewer_id=current_reviewer.id if current_reviewer else None,
        results_per_query=current_study.default_results_per_query,
        search_order=current_study.search_order,
        notes=approve_notes or None,
    )
    st.success("Search strategy approved. Study status set to 'Ready for full search'.")
    st.rerun()

db.close()
