"""
Deduplication of raw full-search results into the `videos` master list.

Raw search_results_raw rows are never discarded -- one Video row is created
per unique (study_id, video_id), built from *all* raw results collected for
the study so far (across every full search run), not just the latest run.
See handover doc section 12.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from db import crud
from db.models import SearchResultRaw
from services import youtube_api
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeduplicationOutcome:
    raw_count: int
    unique_count: int
    newly_created: int
    metadata_unavailable: list[str] = field(default_factory=list)


def queries_per_video(raw_results: list[SearchResultRaw]) -> dict[str, set[int]]:
    """video_id -> set of query_ids that retrieved it (for 'N queries found this')."""
    mapping: dict[str, set[int]] = defaultdict(set)
    for row in raw_results:
        mapping[row.video_id].add(row.query_id)
    return mapping


def best_rank_per_video(raw_results: list[SearchResultRaw]) -> dict[str, int]:
    best: dict[str, int] = {}
    for row in raw_results:
        if row.result_rank is None:
            continue
        if row.video_id not in best or row.result_rank < best[row.video_id]:
            best[row.video_id] = row.result_rank
    return best


def deduplicate_and_enrich(db: Session, study_id: int) -> DeduplicationOutcome:
    """
    Build/refresh the deduplicated Video master list for a study from every
    raw search result collected so far. Safe to call repeatedly -- existing
    Video rows are left untouched, only missing ones are added.
    """
    raw_results = crud.list_search_results_raw(db, study_id)

    # First-seen raw row per unique video_id, used as a metadata fallback.
    first_seen: OrderedDict[str, SearchResultRaw] = OrderedDict()
    for row in raw_results:
        if row.video_id not in first_seen:
            first_seen[row.video_id] = row

    existing_ids = {v.video_id for v in crud.list_videos(db, study_id)}
    missing_ids = [vid for vid in first_seen if vid not in existing_ids]

    details: dict[str, dict] = {}
    if missing_ids:
        try:
            details = youtube_api.get_video_details(missing_ids)
        except youtube_api.YouTubeAPIError as exc:
            logger.warning(
                "Metadata fetch failed for %d video(s); falling back to search-result "
                "fields only: %s",
                len(missing_ids),
                exc,
            )
            details = {}

    unavailable: list[str] = []
    for vid in missing_ids:
        info = details.get(vid)
        fallback = first_seen[vid]

        if info:
            crud.create_video(
                db,
                study_id=study_id,
                video_id=vid,
                title=info.get("title") or fallback.title,
                description=info.get("description"),
                channel_id=info.get("channel_id"),
                channel_title=info.get("channel_title") or fallback.channel_title,
                published_at=info.get("published_at") or fallback.published_at,
                duration_seconds=info.get("duration_seconds"),
                view_count=info.get("view_count"),
                like_count=info.get("like_count"),
                tags_json=info.get("tags") or [],
                thumbnail_url=info.get("thumbnail_url") or fallback.thumbnail_url,
                video_url=info.get("video_url") or fallback.video_url,
                metadata_json={"source": "videos.list"},
            )
        else:
            # Deleted/private video, or the metadata fetch failed outright --
            # keep a usable row from the search result rather than dropping it.
            unavailable.append(vid)
            crud.create_video(
                db,
                study_id=study_id,
                video_id=vid,
                title=fallback.title,
                channel_title=fallback.channel_title,
                published_at=fallback.published_at,
                thumbnail_url=fallback.thumbnail_url,
                video_url=fallback.video_url,
                metadata_json={"metadata_unavailable": True},
            )

    db.commit()

    return DeduplicationOutcome(
        raw_count=len(raw_results),
        unique_count=len(first_seen),
        newly_created=len(missing_ids),
        metadata_unavailable=unavailable,
    )
