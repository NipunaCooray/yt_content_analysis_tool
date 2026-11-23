"""
Shared bookkeeping for pilot and full search runs: executing a batch of
queries, recording which ones failed, and tracking the project's daily
YouTube search quota.

Since June 2026 search.list has its own quota bucket -- by default 100 calls
per project per day, reset at midnight Pacific time, shared by everyone using
the app. Each 50 results of a query is one call. The usage figures here are
estimated from the runs this app has recorded; Google's own count is in the
Cloud Console (APIs & Services -> YouTube Data API v3 -> Quotas).

Run bookkeeping lives in each run's parameters_json:
  query_ids       every query the run covers
  failed_queries  {"<query id>": {"query_text": ..., "error": "quota" | message}}
                  -- only the queries currently failed; cleared when retried OK
  search_batches  [{"at": iso UTC, "query_ids": [...], "calls": n}] -- one per
                  execution (a pilot run can be extended with more queries later)
Runs recorded before this existed have none of the last two keys, so every
reader falls back to what can be inferred from status and saved results.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import FullSearchRun, PilotSearchResult, PilotSearchRun, SearchQuery, SearchResultRaw, utcnow
from services import youtube_api
from utils.constants import RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_PARTIAL
from utils.helpers import publication_date_api_params
from utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SEARCH_QUOTA_PER_DAY = 100
QUOTA_ERROR = "quota"

PILOT = "pilot"
FULL = "full"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchSettings:
    """Everything that changes what a query returns. Two searches of the same
    query with equal settings, close together in time, return the same videos."""

    results_per_query: int
    search_order: str
    region_code: str = "AU"
    relevance_language: str = "en"
    publication_filter_type: str = "all_time"
    published_after: datetime.date | None = None
    published_before: datetime.date | None = None

    @property
    def pages_per_query(self) -> int:
        return max(1, math.ceil(self.results_per_query / 50))

    def api_kwargs(self) -> dict:
        return dict(
            max_results=self.results_per_query,
            order=self.search_order,
            region_code=self.region_code,
            relevance_language=self.relevance_language,
            **publication_date_api_params(
                self.publication_filter_type, self.published_after, self.published_before
            ),
        )


def _date(value: str | None) -> datetime.date | None:
    return datetime.date.fromisoformat(value) if value else None


def settings_for_run(run: PilotSearchRun | FullSearchRun) -> SearchSettings:
    params = run.parameters_json or {}
    if isinstance(run, PilotSearchRun):
        results_per_query, search_order = run.results_per_query, run.search_order
    else:
        results_per_query, search_order = params.get("results_per_query"), params.get("search_order")
    return SearchSettings(
        results_per_query=int(results_per_query or 10),
        search_order=search_order or "relevance",
        region_code=params.get("region_code") or "AU",
        relevance_language=params.get("relevance_language") or "en",
        publication_filter_type=params.get("publication_filter_type") or "all_time",
        published_after=_date(params.get("published_after")),
        published_before=_date(params.get("published_before")),
    )


# ---------------------------------------------------------------------------
# Executing a batch of queries
# ---------------------------------------------------------------------------


@dataclass
class BatchResult:
    queries: list[SearchQuery]
    saved: int = 0
    succeeded_ids: list[int] = field(default_factory=list)
    quota_failed: list[SearchQuery] = field(default_factory=list)
    other_errors: dict[int, str] = field(default_factory=dict)  # query id -> message
    calls: int = 0

    @property
    def queries_failed(self) -> int:
        return len(self.quota_failed) + len(self.other_errors)

    def error_lines(self) -> list[str]:
        text = {q.id: q.query_text for q in self.queries}
        lines = [f"Query '{text[qid]}': {msg}" for qid, msg in self.other_errors.items()]
        if self.quota_failed:
            lines.append(youtube_api.summarise_quota_failures([q.query_text for q in self.quota_failed]))
        return lines


def execute_queries(
    db: Session,
    queries: list[SearchQuery],
    settings: SearchSettings,
    save_items: Callable[[SearchQuery, list[youtube_api.SearchResultItem]], None],
) -> BatchResult:
    """Search every query, saving each one's results as soon as it returns.

    Quota errors don't stop the batch: near the limit Google still lets some
    calls through, and a rejected call costs nothing.
    """
    batch = BatchResult(queries=list(queries))
    for query in queries:
        try:
            items = youtube_api.search_videos(query.query_text, **settings.api_kwargs())
        except youtube_api.YouTubeQuotaExceededError:
            logger.warning("Query '%s': YouTube search quota exceeded.", query.query_text)
            batch.quota_failed.append(query)
            continue
        except youtube_api.YouTubeAPIError as exc:
            logger.warning("Query '%s': %s", query.query_text, exc)
            batch.other_errors[query.id] = str(exc)
            batch.calls += 1
            continue

        save_items(query, items)
        batch.saved += len(items)
        batch.succeeded_ids.append(query.id)
        batch.calls += settings.pages_per_query
        db.commit()  # persist this query's results now, not at the end of the whole run
    return batch


def record_batch(
    db: Session,
    run: PilotSearchRun | FullSearchRun,
    batch: BatchResult,
    run_has_results: bool,
) -> None:
    """Fold a finished batch into the run's bookkeeping, status and error message."""
    db.refresh(run)  # pick up anything another session recorded meanwhile
    params = dict(run.parameters_json or {})

    query_ids = list(params.get("query_ids") or [])
    for q in batch.queries:
        if q.id not in query_ids:
            query_ids.append(q.id)

    failed = dict(params.get("failed_queries") or {})
    if "failed_queries" not in params:
        # Run recorded before this bookkeeping existed: carry over what we can infer.
        for qid in _legacy_failed_ids(db, run):
            failed[str(qid)] = {"query_text": None, "error": "failed in an earlier attempt"}
    for qid in batch.succeeded_ids:
        failed.pop(str(qid), None)
    for q in batch.quota_failed:
        failed[str(q.id)] = {"query_text": q.query_text, "error": QUOTA_ERROR}
    text = {q.id: q.query_text for q in batch.queries}
    for qid, msg in batch.other_errors.items():
        failed[str(qid)] = {"query_text": text[qid], "error": msg}

    batches = list(params.get("search_batches") or [])
    batches.append({"at": utcnow().isoformat(), "query_ids": [q.id for q in batch.queries], "calls": batch.calls})

    params.update(query_ids=query_ids, failed_queries=failed, search_batches=batches)

    if not failed:
        status = RUN_STATUS_COMPLETED
    elif run_has_results:
        status = RUN_STATUS_PARTIAL
    else:
        status = RUN_STATUS_FAILED

    run.parameters_json = params  # reassign so SQLAlchemy sees the JSON change
    run.status = status
    run.completed_at = utcnow()
    run.error_message = _error_message(failed)
    db.commit()
    db.refresh(run)


def _error_message(failed: dict) -> str | None:
    lines, quota = [], []
    for entry in failed.values():
        label = entry.get("query_text") or "(query)"
        if entry.get("error") == QUOTA_ERROR:
            quota.append(label)
        else:
            lines.append(f"Query '{label}': {entry.get('error')}")
    if quota:
        lines.append(youtube_api.summarise_quota_failures(quota))
    return "; ".join(lines) or None


# ---------------------------------------------------------------------------
# Which queries succeeded / failed in a run
# ---------------------------------------------------------------------------


def _ids_with_results(db: Session, run: PilotSearchRun | FullSearchRun) -> set[int]:
    if isinstance(run, PilotSearchRun):
        stmt = select(PilotSearchResult.query_id).where(PilotSearchResult.pilot_search_run_id == run.id)
    else:
        stmt = select(SearchResultRaw.query_id).where(SearchResultRaw.full_search_run_id == run.id)
    return set(db.execute(stmt.distinct()).scalars().all())


def _legacy_failed_ids(db: Session, run: PilotSearchRun | FullSearchRun) -> list[int]:
    if run.status not in (RUN_STATUS_PARTIAL, RUN_STATUS_FAILED):
        return []
    with_results = _ids_with_results(db, run)
    return [qid for qid in (run.parameters_json or {}).get("query_ids", []) if qid not in with_results]


def failed_query_ids(db: Session, run: PilotSearchRun | FullSearchRun) -> list[int]:
    params = run.parameters_json or {}
    if "failed_queries" in params:
        return [int(k) for k in params["failed_queries"]]
    return _legacy_failed_ids(db, run)


def succeeded_query_ids(db: Session, run: PilotSearchRun | FullSearchRun) -> set[int]:
    params = run.parameters_json or {}
    query_ids = set(params.get("query_ids") or [])
    if "failed_queries" in params:
        return query_ids - {int(k) for k in params["failed_queries"]}
    if run.status == RUN_STATUS_COMPLETED:
        return query_ids
    # Unfinished or legacy partial run: only queries with saved results are known good.
    return query_ids & _ids_with_results(db, run)


# ---------------------------------------------------------------------------
# Daily quota
# ---------------------------------------------------------------------------


def search_quota_per_day() -> int:
    """100 by default; set YOUTUBE_SEARCH_QUOTA_PER_DAY if Google grants more."""
    from db.database import get_secret

    try:
        return int(get_secret("YOUTUBE_SEARCH_QUOTA_PER_DAY") or DEFAULT_SEARCH_QUOTA_PER_DAY)
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_QUOTA_PER_DAY


def quota_day_bounds(now: datetime.datetime | None = None) -> tuple[datetime.datetime, datetime.datetime]:
    """(start, reset) of the current quota day as naive UTC, matching how run
    timestamps are stored. The quota resets at midnight Pacific time."""
    now = now or utcnow()
    try:
        from zoneinfo import ZoneInfo

        pacific = ZoneInfo("America/Los_Angeles")
        local = now.replace(tzinfo=datetime.timezone.utc).astimezone(pacific)
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        reset_local = start_local + datetime.timedelta(days=1)  # wall-clock, so DST-safe
        to_utc = lambda d: d.astimezone(datetime.timezone.utc).replace(tzinfo=None)  # noqa: E731
        return to_utc(start_local), to_utc(reset_local)
    except Exception:  # noqa: BLE001 - no tz database: assume PST
        start = (now - datetime.timedelta(hours=8)).replace(hour=0, minute=0, second=0, microsecond=0)
        start += datetime.timedelta(hours=8)
        return start, start + datetime.timedelta(days=1)


@dataclass
class QuotaStatus:
    used: int
    limit: int
    resets_at: datetime.datetime  # naive UTC

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def _calls_today(run, settings: SearchSettings, start: datetime.datetime) -> int:
    params = run.parameters_json or {}
    batches = params.get("search_batches")
    if batches is not None:
        # An extension still in progress isn't counted until its batch is recorded.
        return sum(
            int(b.get("calls") or 0) for b in batches
            if datetime.datetime.fromisoformat(b["at"]) >= start
        )
    # Legacy run, or a first batch still in progress: every query attempted once.
    if run.started_at and run.started_at >= start:
        return len(params.get("query_ids") or []) * settings.pages_per_query
    return 0


def quota_status(db: Session, now: datetime.datetime | None = None) -> QuotaStatus:
    """Searches used today across *all* studies -- the quota is per project."""
    start, reset = quota_day_bounds(now)
    used = 0
    for model in (PilotSearchRun, FullSearchRun):
        runs = db.execute(
            select(model).where(or_(model.started_at >= start, model.completed_at >= start))
        ).scalars().all()
        for run in runs:
            used += _calls_today(run, settings_for_run(run), start)
    return QuotaStatus(used=used, limit=search_quota_per_day(), resets_at=reset)


# ---------------------------------------------------------------------------
# Repeat detection
# ---------------------------------------------------------------------------


def _searched_since(run, start: datetime.datetime) -> set[int]:
    """Query ids this run searched at or after `start`."""
    params = run.parameters_json or {}
    batches = params.get("search_batches")
    if batches is not None:
        return {
            qid for b in batches
            if datetime.datetime.fromisoformat(b["at"]) >= start
            for qid in b.get("query_ids") or []
        }
    if run.started_at and run.started_at >= start:
        return set(params.get("query_ids") or [])
    return set()


def find_repeats(
    db: Session,
    study_id: int,
    kind: str,
    query_ids: list[int],
    settings: SearchSettings,
    now: datetime.datetime | None = None,
) -> dict[int, int]:
    """Selected queries that already have results with these exact settings,
    mapped to the most recent run holding them.

    Pilot: only runs searched today -- a pilot query re-run on another day is a
    legitimate check that results have changed. Full search: any earlier run,
    since every full run feeds the same deduplicated video list.
    """
    wanted = set(query_ids)
    if not wanted:
        return {}
    model = PilotSearchRun if kind == PILOT else FullSearchRun
    runs = db.execute(
        select(model).where(model.study_id == study_id).order_by(model.id.desc())
    ).scalars().all()
    start = quota_day_bounds(now)[0] if kind == PILOT else None

    repeats: dict[int, int] = {}
    for run in runs:
        if settings_for_run(run) != settings:
            continue
        done = succeeded_query_ids(db, run)
        if start is not None:
            done &= _searched_since(run, start)
        for qid in (done & wanted) - repeats.keys():
            repeats[qid] = run.id
    return repeats
