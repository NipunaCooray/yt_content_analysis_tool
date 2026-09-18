"""
Pilot-search business logic: running pilot searches, computing per-query
relevance statistics, and diagnostics. See handover doc section 9.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from db import crud
from db.models import PilotSearchResult, SearchQuery, utcnow
from services import youtube_api
from utils.constants import (
    PUBLICATION_FILTER_ALL_TIME,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PARTIAL,
    RUN_STATUS_RUNNING,
)
from utils.helpers import publication_date_api_params, safe_percentage
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PilotRunOutcome:
    run_id: int
    queries_run: int
    results_saved: int
    errors: list[str]


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
    date_params = publication_date_api_params(publication_filter_type, published_after, published_before)

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

    errors: list[str] = []
    saved = 0
    for query in queries:
        try:
            items = youtube_api.search_videos(
                query.query_text,
                max_results=results_per_query,
                order=search_order,
                region_code=region_code,
                relevance_language=relevance_language,
                **date_params,
            )
        except youtube_api.YouTubeAPIError as exc:
            msg = f"Query '{query.query_text}': {exc}"
            logger.warning(msg)
            errors.append(msg)
            continue

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
            saved += 1
        db.commit()  # persist this query's results now, not at the end of the whole run

    if not errors:
        final_status = RUN_STATUS_COMPLETED
    elif saved > 0:
        final_status = RUN_STATUS_PARTIAL
    else:
        final_status = RUN_STATUS_FAILED
    crud.update_pilot_search_run(
        db, run.id,
        status=final_status,
        completed_at=utcnow(),
        error_message="; ".join(errors) if errors else None,
    )

    return PilotRunOutcome(run_id=run.id, queries_run=len(queries), results_saved=saved, errors=errors)


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
