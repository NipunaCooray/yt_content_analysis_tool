"""
CSV/JSON export generation (Phase 7): one flattened, analysis-ready table
per dataset in handover doc section 22. Internal tables stay relational
(section 25); flattening happens only here, at export time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
from sqlalchemy.orm import Session

from db import crud
from utils.constants import INFORMATION_COVERAGE_ITEMS, OLDER_ADULT_NEED_ITEMS
from utils.helpers import study_export_code


def _join_list(value) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


# ---------------------------------------------------------------------------
# Dataset builders -- each returns a flat pandas DataFrame for one study.
# ---------------------------------------------------------------------------


def studies_df(db: Session, study_id: int) -> pd.DataFrame:
    study = crud.get_study(db, study_id)
    if study is None:
        return pd.DataFrame()
    return pd.DataFrame([{
        "id": study.id,
        "name": study.name,
        "description": study.description,
        "country": study.country,
        "language": study.language,
        "search_date": study.search_date,
        "default_results_per_query": study.default_results_per_query,
        "search_order": study.search_order,
        "search_status": study.search_status,
        "publication_filter_type": study.publication_filter_type,
        "published_after": study.published_after,
        "published_before": study.published_before,
        "notes": study.notes,
        "created_at": study.created_at,
        "updated_at": study.updated_at,
    }])


def search_queries_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_search_queries(db, study_id)
    return pd.DataFrame([{
        "id": q.id,
        "category": q.category,
        "query_text": q.query_text,
        "state_territory": q.state_territory,
        "is_active": q.is_active,
        "notes": q.notes,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
    } for q in rows])


def pilot_search_runs_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_pilot_search_runs(db, study_id)
    return pd.DataFrame([{
        "id": r.id,
        "run_timestamp": r.run_timestamp,
        "status": r.status,
        "started_at": r.started_at,
        "completed_at": r.completed_at,
        "error_message": r.error_message,
        "results_per_query": r.results_per_query,
        "search_order": r.search_order,
        "publication_filter_type": (r.parameters_json or {}).get("publication_filter_type"),
        "published_after": (r.parameters_json or {}).get("published_after"),
        "published_before": (r.parameters_json or {}).get("published_before"),
        "reviewer_id": r.reviewer_id,
        "notes": r.notes,
    } for r in rows])


def pilot_search_results_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_all_pilot_results_for_study(db, study_id)
    query_lookup = {q.id: q.query_text for q in crud.list_search_queries(db, study_id)}
    return pd.DataFrame([{
        "id": r.id,
        "pilot_search_run_id": r.pilot_search_run_id,
        "query_id": r.query_id,
        "query_text": query_lookup.get(r.query_id),
        "video_id": r.video_id,
        "result_rank": r.result_rank,
        "title": r.title,
        "channel_title": r.channel_title,
        "published_at": r.published_at,
        "video_url": r.video_url,
        "relevance_rating": r.relevance_rating,
        "irrelevance_reason": r.irrelevance_reason,
        "reviewer_id": r.reviewer_id,
        "reviewer_notes": r.reviewer_notes,
        "reviewed_at": r.reviewed_at,
    } for r in rows])


def full_search_runs_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_full_search_runs(db, study_id)
    return pd.DataFrame([{
        "id": r.id,
        "run_timestamp": r.run_timestamp,
        "status": r.status,
        "started_at": r.started_at,
        "completed_at": r.completed_at,
        "error_message": r.error_message,
        "approval_id": r.approval_id,
        "results_per_query": (r.parameters_json or {}).get("results_per_query"),
        "search_order": (r.parameters_json or {}).get("search_order"),
        "publication_filter_type": (r.parameters_json or {}).get("publication_filter_type"),
        "published_after": (r.parameters_json or {}).get("published_after"),
        "published_before": (r.parameters_json or {}).get("published_before"),
        "notes": r.notes,
    } for r in rows])


def raw_search_results_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_search_results_raw(db, study_id)
    query_lookup = {q.id: q.query_text for q in crud.list_search_queries(db, study_id)}
    return pd.DataFrame([{
        "id": r.id,
        "full_search_run_id": r.full_search_run_id,
        "query_id": r.query_id,
        "query_text": query_lookup.get(r.query_id),
        "video_id": r.video_id,
        "result_rank": r.result_rank,
        "title": r.title,
        "channel_title": r.channel_title,
        "published_at": r.published_at,
        "video_url": r.video_url,
    } for r in rows])


def unique_videos_df(db: Session, study_id: int) -> pd.DataFrame:
    from services import coding_service, screening_service
    from services.deduplication import best_rank_per_video, queries_per_video

    videos = crud.list_videos(db, study_id)
    raw_results = crud.list_search_results_raw(db, study_id)
    q_per_video = queries_per_video(raw_results)
    best_rank = best_rank_per_video(raw_results)
    decisions = crud.list_screening_decisions(db, study_id)
    codings = crud.list_video_codings(db, study_id)

    return pd.DataFrame([{
        "id": v.id,
        "video_id": v.video_id,
        "title": v.title,
        "channel_id": v.channel_id,
        "channel_title": v.channel_title,
        "published_at": v.published_at,
        "duration_seconds": v.duration_seconds,
        "view_count": v.view_count,
        "like_count": v.like_count,
        "tags": _join_list(v.tags_json),
        "video_url": v.video_url,
        "queries_found_by": len(q_per_video.get(v.video_id, set())),
        "best_search_rank": best_rank.get(v.video_id),
        "screening_status": screening_service.screening_status(decisions.get(v.id)),
        "coding_status": coding_service.coding_status(codings.get(v.id)),
    } for v in videos])


def screening_df(db: Session, study_id: int) -> pd.DataFrame:
    videos = crud.list_videos(db, study_id)
    decisions = crud.list_screening_decisions(db, study_id)
    rows = []
    for v in videos:
        d = decisions.get(v.id)
        rows.append({
            "video_pk": v.id,
            "video_id": v.video_id,
            "title": v.title,
            "decision": d.decision if d else None,
            "exclusion_reason": d.exclusion_reason if d else None,
            "reviewer_id": d.reviewer_id if d else None,
            "notes": d.notes if d else None,
            "screened_at": d.screened_at if d else None,
            "updated_at": d.updated_at if d else None,
        })
    return pd.DataFrame(rows)


def video_characteristics_df(db: Session, study_id: int) -> pd.DataFrame:
    videos = {v.id: v for v in crud.list_videos(db, study_id)}
    codings = crud.list_video_codings(db, study_id)
    return pd.DataFrame([{
        "video_pk": video_pk,
        "video_id": videos[video_pk].video_id if video_pk in videos else None,
        "title": videos[video_pk].title if video_pk in videos else None,
        "transport_modes": _join_list(c.transport_modes_json),
        "jurisdictions": _join_list(c.jurisdictions_json),
        "uploader_type": c.uploader_type,
        "intended_audience": c.intended_audience,
        "older_adult_targeted": c.older_adult_targeted,
        "notes": c.notes,
        "accuracy_notes": c.accuracy_notes,
        "status": c.status,
        "reviewer_id": c.reviewer_id,
        "coded_at": c.coded_at,
        "updated_at": c.updated_at,
    } for video_pk, c in codings.items()])


def _item_code_rows(db: Session, study_id: int, rows, legacy: bool = False) -> list[tuple[dict, object]]:
    """Pair each item-code row with its study/video context.

    Current-framework exports keep only rows belonging to each video's
    single coding record. Legacy archives keep every historical row --
    including any per-reviewer duplicates from the double-coding era -- and
    say which reviewer each came from."""
    videos = {v.id: v for v in crud.list_videos(db, study_id)}
    codings = (
        {c.id: c for c in crud.list_all_video_codings_for_study(db, study_id)} if legacy
        else {c.id: c for c in crud.list_video_codings(db, study_id).values()}
    )
    out = []
    for r in rows:
        coding = codings.get(r.video_coding_id)
        if coding is None and not legacy:
            continue
        video = videos.get(coding.video_id) if coding else None
        context = {
            "study_id": study_id,
            "video_pk": coding.video_id if coding else None,
            "video_id": video.video_id if video else None,
            "title": video.title if video else None,
        }
        if legacy:
            context["reviewer_id"] = coding.reviewer_id if coding else None
        out.append((context, r))
    return out


def _framework_order(items) -> dict[str, int]:
    return {item.key: i for i, item in enumerate(items)}


def information_domains_df(db: Session, study_id: int) -> pd.DataFrame:
    """Revised information-coverage framework, long format: one row per
    (video, item). Category/label come from the central
    framework config by stable key; legacy-framework rows are excluded (see
    legacy_information_domains_df)."""
    items = {i.key: i for i in INFORMATION_COVERAGE_ITEMS}
    order = _framework_order(INFORMATION_COVERAGE_ITEMS)
    rows = [r for r in crud.list_all_information_domain_codes_for_study(db, study_id) if r.domain_name in items]
    rows.sort(key=lambda r: (r.video_coding_id, order[r.domain_name]))
    return pd.DataFrame([{
        **context,
        "category": items[r.domain_name].category,
        "item_key": r.domain_name,
        "item_label": items[r.domain_name].label,
        "value": r.value,
        "notes": r.notes,
    } for context, r in _item_code_rows(db, study_id, rows)])


def older_adult_needs_df(db: Session, study_id: int) -> pd.DataFrame:
    """Revised older-adult-needs framework (four Yes/No items, each with its
    own note), one row per (video, need)."""
    items = {i.key: i for i in OLDER_ADULT_NEED_ITEMS}
    order = _framework_order(OLDER_ADULT_NEED_ITEMS)
    rows = [r for r in crud.list_all_older_adult_need_codes_for_study(db, study_id) if r.need_name in items]
    rows.sort(key=lambda r: (r.video_coding_id, order[r.need_name]))
    return pd.DataFrame([{
        **context,
        "need_key": r.need_name,
        "need_label": items[r.need_name].label,
        "mentioned": r.value,
        "notes": r.notes,
    } for context, r in _item_code_rows(db, study_id, rows)])


# Legacy (pre-revision) coding: preserved and archived as-is, never mapped
# onto the revised framework.


def _legacy_codes_df(db: Session, study_id: int, rows, name_field: str) -> pd.DataFrame:
    return pd.DataFrame([{
        **context,
        name_field: getattr(r, name_field),
        "value": r.value,
        "notes": r.notes,
    } for context, r in _item_code_rows(db, study_id, rows, legacy=True)])


def legacy_information_domains_df(db: Session, study_id: int) -> pd.DataFrame:
    current = {i.key for i in INFORMATION_COVERAGE_ITEMS}
    rows = [r for r in crud.list_all_information_domain_codes_for_study(db, study_id) if r.domain_name not in current]
    return _legacy_codes_df(db, study_id, rows, "domain_name")


def legacy_older_adult_needs_df(db: Session, study_id: int) -> pd.DataFrame:
    current = {i.key for i in OLDER_ADULT_NEED_ITEMS}
    rows = [r for r in crud.list_all_older_adult_need_codes_for_study(db, study_id) if r.need_name not in current]
    return _legacy_codes_df(db, study_id, rows, "need_name")


def legacy_presentation_coding_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_all_presentation_codes_for_study(db, study_id)
    return _legacy_codes_df(db, study_id, rows, "item_name")


def legacy_accuracy_claims_df(db: Session, study_id: int) -> pd.DataFrame:
    """Claim-level accuracy assessment, archived as-is (no longer collected;
    never mapped into video_coding.accuracy_notes)."""
    videos = {v.id: v for v in crud.list_videos(db, study_id)}
    rows = crud.list_accuracy_claims_for_study(db, study_id)
    return pd.DataFrame([{
        "id": c.id,
        "video_pk": c.video_id,
        "video_id": videos[c.video_id].video_id if c.video_id in videos else None,
        "title": videos[c.video_id].title if c.video_id in videos else None,
        "claim_text": c.claim_text,
        "category": c.category,
        "official_source_url": c.official_source_url,
        "assessment": c.assessment,
        "notes": c.notes,
        "reviewer_id": c.reviewer_id,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    } for c in rows])


def reviewers_df(db: Session, study_id: int) -> pd.DataFrame:
    # Reviewers aren't study-scoped in the schema -- export the full roster.
    rows = crud.list_reviewers(db)
    return pd.DataFrame([{
        "id": r.id,
        "name": r.name,
        "initials": r.initials,
        "email": r.email,
        "created_at": r.created_at,
    } for r in rows])


@dataclass
class ExportDataset:
    key: str
    label: str
    filename_suffix: str
    builder: Callable[[Session, int], pd.DataFrame]
    # The datasets from handover doc section 22 (presentation coding and
    # accuracy claims have since been removed -- their legacy rows are
    # archived below).
    required: bool = True


EXPORT_DATASETS: list[ExportDataset] = [
    ExportDataset("studies", "Studies", "studies", studies_df),
    ExportDataset("search_queries", "Search queries", "search_queries", search_queries_df),
    ExportDataset("pilot_search_runs", "Pilot search runs", "pilot_search_runs", pilot_search_runs_df),
    ExportDataset("pilot_search_results", "Pilot search results", "pilot_results", pilot_search_results_df),
    ExportDataset("full_search_runs", "Full search runs", "full_search_runs", full_search_runs_df),
    ExportDataset("raw_search_results", "Raw search results", "raw_search_results", raw_search_results_df),
    ExportDataset("unique_videos", "Deduplicated videos", "unique_videos", unique_videos_df),
    ExportDataset("screening", "Screening decisions", "screening", screening_df),
    ExportDataset("video_characteristics", "Video characteristics", "video_coding", video_characteristics_df),
    ExportDataset("information_domains", "Information coverage coding", "information_domains", information_domains_df),
    ExportDataset("older_adult_needs", "Older-adult-needs coding", "older_adult_needs", older_adult_needs_df),
    ExportDataset("reviewers", "Reviewers", "reviewers", reviewers_df),
    ExportDataset(
        "legacy_information_domains", "Legacy information coverage coding (archived)",
        "legacy_information_domains", legacy_information_domains_df, required=False,
    ),
    ExportDataset(
        "legacy_older_adult_needs", "Legacy older-adult-needs coding (archived)",
        "legacy_older_adult_needs", legacy_older_adult_needs_df, required=False,
    ),
    ExportDataset(
        "legacy_presentation_coding", "Legacy presentation coding (archived)",
        "legacy_presentation_coding", legacy_presentation_coding_df, required=False,
    ),
    ExportDataset(
        "legacy_accuracy_claims", "Legacy accuracy claims (archived)",
        "legacy_accuracy_claims", legacy_accuracy_claims_df, required=False,
    ),
]


def build_dataframe(db: Session, study_id: int, dataset: ExportDataset) -> pd.DataFrame:
    return dataset.builder(db, study_id)


def export_filename(study_id: int, dataset: ExportDataset, ext: str) -> str:
    return f"{study_export_code(study_id)}_{dataset.filename_suffix}.{ext}"


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_json_bytes(df: pd.DataFrame) -> bytes:
    return df.to_json(orient="records", date_format="iso", indent=2).encode("utf-8")


def build_zip_export(
    db: Session, study_id: int, dataframes: dict[str, pd.DataFrame] | None = None
) -> bytes:
    """Every dataset as a CSV, bundled into one in-memory ZIP file.

    `dataframes`, if given, is a {dataset.key: DataFrame} map of already-built
    datasets (e.g. from the caller's own per-dataset cache) -- pass it to
    avoid rebuilding every dataset a second time just for the ZIP, since the
    Export page also renders each one as a preview.
    """
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for dataset in EXPORT_DATASETS:
            df = dataframes[dataset.key] if dataframes is not None else build_dataframe(db, study_id, dataset)
            filename = export_filename(study_id, dataset, "csv")
            zf.writestr(filename, df.to_csv(index=False))
    return buffer.getvalue()
