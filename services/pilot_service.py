"""
Pilot-search business logic: running pilot searches, computing per-query
relevance statistics, and diagnostics. See handover doc section 9.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import crud
from db.models import PilotSearchResult, SearchQuery, utcnow
from services import search_runs, youtube_api  # noqa: F401 - youtube_api patched in tests
from utils.constants import PUBLICATION_FILTER_ALL_TIME, RUN_STATUS_RUNNING
from utils.helpers import safe_percentage
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PilotRunOutcome:
    run_id: int
    queries_run: int
    results_saved: int
    errors: list[str]
    queries_failed: int = 0


def run_pilot_search(
    db: Session,
    study_id: int,
    queries: list[SearchQuery],
    results_per_query: int,
    search_order: str,
    reviewer_id: int | None,
    notes: str | None = None,
    region_code: str = "AU",
    relevance_language: str = "en",
    publication_filter_type: str = PUBLICATION_FILTER_ALL_TIME,
    published_after: datetime.date | None = None,
    published_before: datetime.date | None = None,
) -> PilotRunOutcome:
    """
    Execute a pilot search across the given queries and persist a new
    PilotSearchRun + PilotSearchResult rows. Never overwrites prior runs.

    The publication-date filter uses the same logic the full search will use
    (see search_service.run_full_search), so pilot results are representative
    of what the full search will retrieve.

    A query's results are committed as soon as that query completes, not
    batched until the whole run finishes -- so if something goes wrong
    partway through (a crash, a Streamlit Cloud restart), the queries that
    already succeeded stay saved rather than being lost with the rest of the
    transaction. The run's `status` reflects what actually happened:
    completed (all queries succeeded), partial (some did), or failed (none
    did) -- durable in the database even if the process dies before this
    function returns.
    """
    run = crud.create_pilot_search_run(
        db,
        study_id=study_id,
        results_per_query=results_per_query,
        search_order=search_order,
        reviewer_id=reviewer_id,
        notes=notes,
        status=RUN_STATUS_RUNNING,
        started_at=utcnow(),
        parameters_json={
            "region_code": region_code,
            "relevance_language": relevance_language,
            "query_ids": [q.id for q in queries],
            "publication_filter_type": publication_filter_type,
            "published_after": published_after.isoformat() if published_after else None,
            "published_before": published_before.isoformat() if published_before else None,
        },
    )
    return _execute_into_run(db, run, queries)


def add_queries_to_pilot_run(
    db: Session,
    run_id: int,
    queries: list[SearchQuery],
    reviewer_id: int | None,
) -> PilotRunOutcome:
    """Search more queries into an existing pilot run, using that run's own
    settings, so its performance table, diagnostics and review cover them
    together with the queries already there -- without re-searching those.

    Queries that already succeeded in the run are skipped; ones that failed
    there (e.g. on quota) are retried.
    """
    run = crud.get_pilot_search_run(db, run_id)
    if run is None:
        raise ValueError(f"Pilot run {run_id} not found")
    done = search_runs.succeeded_query_ids(db, run)
    to_run = [q for q in queries if q.id not in done]

    crud.log_audit_event(
        db, "pilot_run_extended", "pilot_search_run", run.id,
        study_id=run.study_id, reviewer_id=reviewer_id,
        details={"query_ids": [q.id for q in to_run]},
    )
    if not to_run:
        return PilotRunOutcome(run_id=run.id, queries_run=0, results_saved=0, errors=[])
    crud.update_pilot_search_run(db, run.id, status=RUN_STATUS_RUNNING)
    return _execute_into_run(db, run, to_run)


def _execute_into_run(db: Session, run, queries: list[SearchQuery]) -> PilotRunOutcome:
    def save(query: SearchQuery, items) -> None:
        for item in items:
            crud.add_pilot_search_result(
                db,
                pilot_search_run_id=run.id,
                query_id=query.id,
                video_id=item.video_id,
                result_rank=item.rank,
                title=item.title,
                description=item.description,
                channel_title=item.channel_title,
                published_at=item.published_at,
                thumbnail_url=item.thumbnail_url,
                video_url=item.video_url,
                relevance_rating="Not yet reviewed",
                raw_json=item.raw,
            )

    batch = search_runs.execute_queries(db, queries, search_runs.settings_for_run(run), save)
    has_results = db.execute(
        select(PilotSearchResult.id).where(PilotSearchResult.pilot_search_run_id == run.id).limit(1)
    ).first() is not None
    search_runs.record_batch(db, run, batch, run_has_results=has_results)

    return PilotRunOutcome(
        run_id=run.id, queries_run=len(queries), results_saved=batch.saved,
        errors=batch.error_lines(), queries_failed=batch.queries_failed,
    )


@dataclass
class QueryPerformance:
    query_id: int
    query_text: str
    reviewed: int
    relevant: int
    potentially_relevant: int
    irrelevant: int
    not_yet_reviewed: int
    total: int
    strict_relevance_rate: float | None
    broad_relevance_rate: float | None


def compute_query_performance(db: Session, pilot_search_run_id: int) -> list[QueryPerformance]:
    """Per-query relevance stats for a pilot run (handover doc section 37)."""
    results = crud.list_pilot_search_results(db, pilot_search_run_id)
    by_query: dict[int, list[PilotSearchResult]] = defaultdict(list)
    for r in results:
        by_query[r.query_id].append(r)

    performance: list[QueryPerformance] = []
    for query_id, rows in by_query.items():
        query = crud.get_search_query(db, query_id)
        total = len(rows)
        relevant = sum(1 for r in rows if r.relevance_rating == "Relevant")
        potential = sum(1 for r in rows if r.relevance_rating == "Potentially relevant")
        irrelevant = sum(1 for r in rows if r.relevance_rating == "Irrelevant")
        not_reviewed = sum(1 for r in rows if r.relevance_rating == "Not yet reviewed")
        reviewed = total - not_reviewed

        performance.append(
            QueryPerformance(
                query_id=query_id,
                query_text=query.query_text if query else "(deleted query)",
                reviewed=reviewed,
                relevant=relevant,
                potentially_relevant=potential,
                irrelevant=irrelevant,
                not_yet_reviewed=not_reviewed,
                total=total,
                strict_relevance_rate=safe_percentage(relevant, reviewed),
                broad_relevance_rate=safe_percentage(relevant + potential, reviewed),
            )
        )
    performance.sort(key=lambda p: p.query_text.lower())
    return performance


@dataclass
class PilotDiagnostics:
    duplicate_video_ids: dict[str, int]  # video_id -> number of queries that retrieved it
    irrelevance_reason_counts: dict[str, int]
    total_results: int
    unique_videos: int


def compute_diagnostics(db: Session, pilot_search_run_id: int) -> PilotDiagnostics:
    results = crud.list_pilot_search_results(db, pilot_search_run_id)

    video_to_queries: dict[str, set[int]] = defaultdict(set)
    reason_counter: Counter[str] = Counter()
    for r in results:
        video_to_queries[r.video_id].add(r.query_id)
        if r.relevance_rating == "Irrelevant" and r.irrelevance_reason:
            reason_counter[r.irrelevance_reason] += 1

    duplicates = {vid: len(qs) for vid, qs in video_to_queries.items() if len(qs) > 1}

    return PilotDiagnostics(
        duplicate_video_ids=duplicates,
        irrelevance_reason_counts=dict(reason_counter),
        total_results=len(results),
        unique_videos=len(video_to_queries),
    )


def approve_search_strategy(
    db: Session,
    study_id: int,
    reviewer_id: int | None,
    results_per_query: int,
    search_order: str,
    notes: str | None = None,
    publication_filter_type: str = PUBLICATION_FILTER_ALL_TIME,
    published_after: datetime.date | None = None,
    published_before: datetime.date | None = None,
) -> None:
    """Snapshot the currently active query set and mark the study ready for
    full search. The publication-date filter is part of the approved
    strategy, same as results_per_query/search_order -- the Full Search page
    uses this snapshot's date filter automatically."""
    active_queries = crud.list_search_queries(db, study_id, active_only=True)
    snapshot = [
        {
            "id": q.id,
            "query_text": q.query_text,
            "category": q.category,
            "state_territory": q.state_territory,
        }
        for q in active_queries
    ]
    crud.create_search_strategy_approval(
        db,
        study_id=study_id,
        reviewer_id=reviewer_id,
        query_snapshot_json=snapshot,
        parameters_json={
            "results_per_query": results_per_query,
            "search_order": search_order,
            "publication_filter_type": publication_filter_type,
            "published_after": published_after.isoformat() if published_after else None,
            "published_before": published_before.isoformat() if published_before else None,
        },
        notes=notes,
    )
    crud.update_study(db, study_id, search_status="Ready for full search")
