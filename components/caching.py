"""
Streamlit-cache wrappers for expensive, read-heavy queries.

Deliberately kept out of services/ and db/crud.py, which stay Streamlit-free
by design (see the repo structure) -- caching is a UI/deployment-layer
concern specific to running under Streamlit's per-interaction rerun model,
not business logic.

Cache safety: every cached function here returns *plain data* (dicts,
pandas DataFrames) rather than live SQLAlchemy ORM objects. A cached ORM
object can raise DetachedInstanceError on the next rerun once the Session
that produced it has closed (which happens at the end of every page) --
returning plain data sidesteps that entirely, at the cost of the caller
doing one more (cheap, always-fresh) primary-key lookup for the actual
selected row. See measurements in the PostgreSQL-latency investigation:
~250ms per round trip, so cutting the sidebar's redundant
list-then-refetch pattern and caching the list itself both matter.

TTLs are short (a few/tens of seconds) -- the tradeoff is: the acting
user's own writes are made visible immediately via explicit invalidate_*()
calls at the point of mutation, while some other, less obvious mutation
paths (e.g. a pilot run flipping a study's search_status) may leave a
stale *label* in someone else's sidebar for up to the TTL. That's a
cosmetic-only gap -- the actual selected Study/Reviewer object handed to
every page is always fetched fresh, never cached.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from db import crud
from services import export_service

_SIDEBAR_TTL = 15  # seconds
_EXPORT_TTL = 15


@st.cache_data(ttl=_SIDEBAR_TTL, show_spinner=False)
def cached_study_options(_db: Session) -> list[dict]:
    """Plain id/name/status rows for the sidebar's study picker."""
    return [
        {"id": s.id, "name": s.name, "search_status": s.search_status}
        for s in crud.list_studies(_db)
    ]


@st.cache_data(ttl=_SIDEBAR_TTL, show_spinner=False)
def cached_reviewer_options(_db: Session) -> list[dict]:
    """Plain id/name/initials rows for the sidebar's reviewer picker."""
    return [
        {"id": r.id, "name": r.name, "initials": r.initials}
        for r in crud.list_reviewers(_db)
    ]


def invalidate_study_options() -> None:
    """Call right after creating/updating/deleting a study."""
    cached_study_options.clear()


def invalidate_reviewer_options() -> None:
    """Call right after creating/updating/deleting a reviewer."""
    cached_reviewer_options.clear()


@st.cache_data(ttl=_EXPORT_TTL, show_spinner=False)
def cached_export_dataframe(_db: Session, study_id: int, dataset_key: str):
    """A single export dataset's DataFrame -- safe to cache as-is, since
    export_service already returns plain pandas DataFrames, never ORM
    objects. Used by both the Export page (renders all 17 previews on
    every rerun) and the Dashboard (reuses several of the same builders)."""
    dataset = next(d for d in export_service.EXPORT_DATASETS if d.key == dataset_key)
    return export_service.build_dataframe(_db, study_id, dataset)


def invalidate_export_cache() -> None:
    """Call after any write that could change what an export would show,
    if you need the acting user to see it before the TTL expires (rarely
    necessary in practice -- Export/Dashboard are read-only pages, so the
    write always happens on a different page/rerun already outside this
    cache's scope)."""
    cached_export_dataframe.clear()
