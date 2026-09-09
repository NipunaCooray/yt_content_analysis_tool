from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import page_header, render_context_sidebar, require_study
from db import crud
from db.database import get_session
from services import search_service
from services.deduplication import best_rank_per_video, queries_per_video
from services.youtube_api import api_key_configured, estimate_search_calls
from utils.constants import SEARCH_ORDER_OPTIONS

LARGE_RUN_CALL_THRESHOLD = 20

db = get_session()
current_study, current_reviewer = render_context_sidebar(db)

page_header("Full search results", "Run the approved search strategy and preserve all results.")

if not require_study(current_study):
    st.stop()

study_id = current_study.id

latest_approval = crud.get_latest_approval(db, study_id)

if latest_approval is None:
    st.warning(
        "No approved search strategy yet. Go to **Pilot search**, test your queries, and "
        "click **Approve search strategy** before running the full search.",
        icon="⚠️",
    )
    db.close()
    st.stop()

approved_query_ids = {q["id"] for q in (latest_approval.query_snapshot_json or [])}
active_queries = crud.list_search_queries(db, study_id, active_only=True)
active_ids = {q.id for q in active_queries}

if approved_query_ids != active_ids:
    st.warning(
        "The active query set has changed since the search strategy was last approved "
        f"({latest_approval.approved_at:%Y-%m-%d %H:%M}). Consider re-approving on the "
        "Pilot search page before running the full search, or proceed knowingly — this "
        "will be logged either way.",
        icon="⚠️",
    )

# ---------------------------------------------------------------------------
# Run a new full search
# ---------------------------------------------------------------------------

with st.expander("Run full search", expanded=not crud.list_full_search_runs(db, study_id)):
    if not active_queries:
        st.info("No active queries. Add some in Search strategy first.")
    elif not api_key_configured():
        st.error("No YouTube API key configured. See Settings.")
    else:
        query_options = {q.id: q.query_text for q in active_queries}
        default_selected = [qid for qid in query_options if qid in approved_query_ids] or list(
            query_options.keys()
        )
        selected_ids = st.multiselect(
            "Queries to include",
            options=list(query_options.keys()),
            default=default_selected,
            format_func=lambda qid: query_options[qid],
        )
        col1, col2 = st.columns(2)
        results_per_query = col1.number_input(
            "Results per query",
            min_value=1,
            max_value=200,
            value=current_study.default_results_per_query or 10,
        )
        search_order = col2.selectbox(
            "Search order",
            SEARCH_ORDER_OPTIONS,
            index=SEARCH_ORDER_OPTIONS.index(current_study.search_order)
            if current_study.search_order in SEARCH_ORDER_OPTIONS
            else 0,
        )
        run_notes = st.text_input("Notes for this full search run (optional)")

        est_calls = estimate_search_calls(len(selected_ids), int(results_per_query))
        st.caption(
            f"Estimated API usage: ~{est_calls} search call(s) "
            f"(~{est_calls * 100} search-quota units), plus metadata lookups for new videos."
        )

        confirmed = True
        if est_calls > LARGE_RUN_CALL_THRESHOLD:
            confirmed = st.checkbox(
                f"I understand this will use approximately {est_calls} API search calls."
            )

        if st.button(
            "Run full search", type="primary", disabled=not selected_ids or not confirmed
        ):
            queries_to_run = [q for q in active_queries if q.id in selected_ids]
            with st.spinner(f"Running full search across {len(queries_to_run)} quer(y/ies)..."):
                outcome = search_service.run_full_search(
                    db,
                    study_id=study_id,
                    queries=queries_to_run,
                    results_per_query=int(results_per_query),
                    search_order=search_order,
                    approval_id=latest_approval.id,
                    notes=run_notes or None,
                )
            msg = (
                f"Full search complete: {outcome.raw_results_saved} raw result(s) saved, "
                f"{outcome.dedup.newly_created} new unique video(s) added "
                f"({outcome.dedup.unique_count} unique total)."
            )
            if outcome.dedup.metadata_unavailable:
                msg += (
                    f" {len(outcome.dedup.metadata_unavailable)} video(s) had no metadata "
                    "available (likely deleted/private) — kept with search-result fields only."
                )
            if outcome.errors:
                st.warning(
                    msg + f"\n\n{len(outcome.errors)} quer(y/ies) failed:\n\n"
                    + "\n".join(f"- {e}" for e in outcome.errors)
                )
            else:
                st.success(msg)
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

full_runs = crud.list_full_search_runs(db, study_id)

if not full_runs:
    st.info("No full search has been run yet. Use 'Run full search' above.")
    db.close()
    st.stop()

raw_results = crud.list_search_results_raw(db, study_id)
videos = crud.list_videos(db, study_id)

m1, m2, m3 = st.columns(3)
m1.metric("Raw results", len(raw_results))
m2.metric("Unique videos", len(videos))
m3.metric("Duplicate occurrences", len(raw_results) - len(videos))

tab_raw, tab_unique, tab_log = st.tabs(["Raw results", "Unique videos", "Search log"])

with tab_raw:
    if not raw_results:
        st.info("No raw results yet.")
    else:
        query_lookup = {q.id: q.query_text for q in crud.list_search_queries(db, study_id)}
        raw_df = pd.DataFrame(
            [
                {
                    "Query": query_lookup.get(r.query_id, "(deleted query)"),
                    "Rank": r.result_rank,
                    "Title": r.title,
                    "Channel": r.channel_title,
                    "Published": r.published_at,
                    "Video URL": r.video_url,
                }
                for r in raw_results
            ]
        )
        st.dataframe(raw_df, width="stretch", hide_index=True)

with tab_unique:
    if not videos:
        st.info("No unique videos yet.")
    else:
        q_per_video = queries_per_video(raw_results)
        best_rank = best_rank_per_video(raw_results)
        unique_df = pd.DataFrame(
            [
                {
                    "Title": v.title,
                    "Channel": v.channel_title,
                    "Published": v.published_at,
                    "Duration (s)": v.duration_seconds,
                    "Views": v.view_count,
                    "Queries found by": len(q_per_video.get(v.video_id, set())),
                    "Best rank": best_rank.get(v.video_id),
                    # Screening/coding tables are built in Phases 4-5; every
                    # video starts in these default states until then.
                    "Screening status": "Not screened",
                    "Coding status": "Not started",
                    "Video URL": v.video_url,
                }
                for v in videos
            ]
        )
        st.dataframe(unique_df, width="stretch", hide_index=True)

with tab_log:
    log_df = pd.DataFrame(
        [
            {
                "Run": r.id,
                "Timestamp": r.run_timestamp,
                "Results/query": (r.parameters_json or {}).get("results_per_query"),
                "Order": (r.parameters_json or {}).get("search_order"),
                "Queries": len((r.parameters_json or {}).get("query_ids", [])),
                "Notes": r.notes,
            }
            for r in full_runs
        ]
    )
    st.dataframe(log_df, width="stretch", hide_index=True)
    st.caption("Full audit trail (query edits, approvals, etc.) is available on the Settings page.")

db.close()
