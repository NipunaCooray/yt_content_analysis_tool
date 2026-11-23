"""
Full-search execution (Phase 3): runs the approved search strategy, stores
every raw result (never overwriting prior runs), and builds the
deduplicated master video list. See handover doc section 12.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from db import crud
from db.models import SearchQuery, utcnow
from services import search_runs, youtube_api  # noqa: F401 - youtube_api patched in tests
from services.deduplication import DeduplicationOutcome, deduplicate_and_enrich
from utils.constants import PUBLICATION_FILTER_ALL_TIME, RUN_STATUS_RUNNING
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FullSearchOutcome:
    run_id: int
    queries_run: int
    raw_results_saved: int
    errors: list[str] = field(default_factory=list)
    dedup: DeduplicationOutcome | None = None
    queries_failed: int = 0


def run_full_search(
    db: Session,
    study_id: int,
    queries: list[SearchQuery],
    results_per_query: int,
    search_order: str,
    approval_id: int | None,
    notes: str | None = None,
    region_code: str = "AU",
    relevance_language: str = "en",
    publication_filter_type: str = PUBLICATION_FILTER_ALL_TIME,
    published_after: datetime.date | None = None,
    published_before: datetime.date | None = None,
) -> FullSearchOutcome:
    """
    Execute the (approved) search strategy across the given queries and
    persist a new FullSearchRun + SearchResultRaw rows, then refresh the
    deduplicated video master list. Never overwrites prior runs' raw data.

    The publication-date filter is a filter on the search, not a sort --
    `search_order` is applied independently, same as ever.

    A query's raw results are committed as soon as that query completes
    (not batched until the whole run finishes), and the run's `status` is
    updated as it progresses -- same durability rationale as
    pilot_service.run_pilot_search: a crash or restart partway through
    shouldn't lose the queries that already succeeded.
    """
    run = crud.create_full_search_run(
        db,
        study_id=study_id,
        approval_id=approval_id,
        status=RUN_STATUS_RUNNING,
        started_at=utcnow(),
        parameters_json={
            "results_per_query": results_per_query,
            "search_order": search_order,
            "region_code": region_code,
            "relevance_language": relevance_language,
            "query_ids": [q.id for q in queries],
            "publication_filter_type": publication_filter_type,
            "published_after": published_after.isoformat() if published_after else None,
            "published_before": published_before.isoformat() if published_before else None,
        },
        notes=notes,
    )

    def save(query: SearchQuery, items) -> None:
        for item in items:
            crud.add_search_result_raw(
                db,
                full_search_run_id=run.id,
                query_id=query.id,
                video_id=item.video_id,
                result_rank=item.rank,
                title=item.title,
                channel_title=item.channel_title,
                published_at=item.published_at,
                thumbnail_url=item.thumbnail_url,
                video_url=item.video_url,
                raw_json=item.raw,
            )

    batch = search_runs.execute_queries(db, queries, search_runs.settings_for_run(run), save)
    search_runs.record_batch(db, run, batch, run_has_results=batch.saved > 0)
    saved = batch.saved
    errors = batch.error_lines()

    dedup_outcome = deduplicate_and_enrich(db, study_id)
    if saved > 0:
        crud.update_study(db, study_id, search_status="Full search completed")

    return FullSearchOutcome(
        run_id=run.id,
        queries_run=len(queries),
        raw_results_saved=saved,
        errors=errors,
        dedup=dedup_outcome,
        queries_failed=batch.queries_failed,
    )
