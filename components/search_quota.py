"""Daily search-quota display and pre-run warnings shared by the pilot and
full search pages. See services/search_runs.py for how usage is counted."""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from db.models import utcnow
from services.search_runs import QuotaStatus, quota_status


def _until(resets_at) -> str:
    minutes = max(0, int((resets_at - utcnow()).total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def render_quota_status(db: Session) -> QuotaStatus:
    status = quota_status(db)
    text = (
        f"**YouTube searches used today: ~{status.used} of {status.limit}** "
        f"(shared by everyone using the app; resets in {_until(status.resets_at)}, "
        "at midnight Pacific time)."
    )
    if status.remaining == 0:
        st.warning(
            text + " Today's search quota is used up — searches will most likely fail "
            "until it resets.",
            icon="⛔",
        )
    else:
        st.caption(text)
    return status


def render_shortfall_warning(est_calls: int, status: QuotaStatus) -> None:
    if est_calls <= status.remaining or status.remaining == 0:
        return  # nothing to add, or the used-up warning above already says it
    st.warning(
        f"This run needs ~{est_calls} searches but only ~{status.remaining} are left today. "
        "Queries past that will most likely fail on quota; you can retry just those after "
        "the reset, or run fewer queries now.",
        icon="⚠️",
    )


def render_repeat_warning(
    repeats: dict[int, int],
    query_text: dict[int, str],
    select_key: str,
    when: str,
) -> None:
    """Warn about selected queries that already have results with the same
    settings, with a one-click way to deselect them. `when` completes the
    sentence "already searched ... with these settings"."""
    if not repeats:
        return
    listed = "\n".join(
        f"- {query_text.get(qid, f'query {qid}')} (run #{run_id})" for qid, run_id in repeats.items()
    )
    st.warning(
        f"**{len(repeats)} selected quer(y/ies) were already searched {when} with these "
        f"settings**, so running them again uses {len(repeats)}+ searches for (almost) the "
        f"same results:\n\n{listed}\n\nYou can still run them if you mean to.",
        icon="🔁",
    )

    def _deselect() -> None:
        st.session_state[select_key] = [
            qid for qid in st.session_state.get(select_key, []) if qid not in repeats
        ]

    st.button("Remove repeated queries from the selection", on_click=_deselect, key=f"{select_key}_dedupe")
