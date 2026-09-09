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
        "results_per_query": r.results_per_query,
        "search_order": r.search_order,
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
        "approval_id": r.approval_id,
        "results_per_query": (r.parameters_json or {}).get("results_per_query"),
        "search_order": (r.parameters_json or {}).get("search_order"),
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
    from services import accuracy_service, coding_service, screening_service
    from services.deduplication import best_rank_per_video, queries_per_video

    videos = crud.list_videos(db, study_id)
    raw_results = crud.list_search_results_raw(db, study_id)
    q_per_video = queries_per_video(raw_results)
    best_rank = best_rank_per_video(raw_results)
    decisions = crud.list_screening_decisions(db, study_id)
    codings = crud.list_video_codings(db, study_id)
    review_statuses = crud.list_accuracy_review_statuses(db, study_id)
    claim_counts = crud.count_accuracy_claims(db, study_id)

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
        "accuracy_status": accuracy_service.accuracy_status(
            review_statuses.get(v.id), claim_counts.get(v.id, 0)
        ),
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
        "status": c.status,
        "reviewer_id": c.reviewer_id,
        "coded_at": c.coded_at,
        "updated_at": c.updated_at,
    } for video_pk, c in codings.items()])


def _domain_codes_df(db: Session, study_id: int, rows, name_field: str) -> pd.DataFrame:
    videos = {v.id: v for v in crud.list_videos(db, study_id)}
    codings_by_id = {c.id: c for c in crud.list_video_codings(db, study_id).values()}
    out = []
    for r in rows:
        coding = codings_by_id.get(r.video_coding_id)
        video = videos.get(coding.video_id) if coding else None
        out.append({
            "video_pk": coding.video_id if coding else None,
            "video_id": video.video_id if video else None,
            "title": video.title if video else None,
            name_field: getattr(r, name_field),
            "value": r.value,
            "notes": r.notes,
        })
    return pd.DataFrame(out)


def information_domains_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_all_information_domain_codes_for_study(db, study_id)
    return _domain_codes_df(db, study_id, rows, "domain_name")


def older_adult_needs_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_all_older_adult_need_codes_for_study(db, study_id)
    return _domain_codes_df(db, study_id, rows, "need_name")


def presentation_coding_df(db: Session, study_id: int) -> pd.DataFrame:
    rows = crud.list_all_presentation_codes_for_study(db, study_id)
    return _domain_codes_df(db, study_id, rows, "item_name")


def accuracy_claims_df(db: Session, study_id: int) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# Reliability datasets (Phase 8) -- additive, beyond the 14 required datasets.
# screening.csv/video_coding.csv above are the canonical (one-per-video)
# records used throughout the tool; these carry every reviewer's
# independent record plus the computed agreement statistics, for reporting
# reliability in the methods section (study-initiation guide section 57).
# ---------------------------------------------------------------------------


def screening_all_reviewers_df(db: Session, study_id: int) -> pd.DataFrame:
    videos = {v.id: v for v in crud.list_videos(db, study_id)}
    reviewer_names = {r.id: r.name for r in crud.list_reviewers(db)}
    rows = crud.list_all_screening_decisions_for_study(db, study_id)
    return pd.DataFrame([{
        "id": d.id,
        "video_pk": d.video_id,
        "video_id": videos[d.video_id].video_id if d.video_id in videos else None,
        "title": videos[d.video_id].title if d.video_id in videos else None,
        "reviewer_id": d.reviewer_id,
        "reviewer_name": reviewer_names.get(d.reviewer_id),
        "decision": d.decision,
        "exclusion_reason": d.exclusion_reason,
        "notes": d.notes,
        "screened_at": d.screened_at,
        "updated_at": d.updated_at,
    } for d in rows])


def video_coding_all_reviewers_df(db: Session, study_id: int) -> pd.DataFrame:
    videos = {v.id: v for v in crud.list_videos(db, study_id)}
    reviewer_names = {r.id: r.name for r in crud.list_reviewers(db)}
    rows = crud.list_all_video_codings_for_study(db, study_id)
    return pd.DataFrame([{
        "id": c.id,
        "video_pk": c.video_id,
        "video_id": videos[c.video_id].video_id if c.video_id in videos else None,
        "title": videos[c.video_id].title if c.video_id in videos else None,
        "reviewer_id": c.reviewer_id,
        "reviewer_name": reviewer_names.get(c.reviewer_id),
        "transport_modes": _join_list(c.transport_modes_json),
        "jurisdictions": _join_list(c.jurisdictions_json),
        "uploader_type": c.uploader_type,
        "intended_audience": c.intended_audience,
        "older_adult_targeted": c.older_adult_targeted,
        "notes": c.notes,
        "status": c.status,
        "coded_at": c.coded_at,
        "updated_at": c.updated_at,
    } for c in rows])


def reliability_summary_df(db: Session, study_id: int) -> pd.DataFrame:
    from services import reliability_service

    rows: list[dict] = []

    all_videos = crud.list_videos(db, study_id)
    double_screened = reliability_service.double_coded_videos(db, study_id, all_videos, "screening")
    if double_screened:
        stat, _ = reliability_service.screening_reliability(db, study_id, double_screened)
        rows.append({"stage": "Screening", "field": stat.field_name, "n_pairs": stat.n_pairs,
                     "agreement_pct": stat.percentage_agreement, "kappa": stat.kappa})

    included_videos = crud.list_included_videos(db, study_id)
    double_coded = reliability_service.double_coded_videos(db, study_id, included_videos, "coding")
    if double_coded:
        char_stats, _ = reliability_service.coding_characteristics_reliability(db, study_id, double_coded)
        for s in char_stats:
            rows.append({"stage": "Coding - characteristics", "field": s.field_name, "n_pairs": s.n_pairs,
                         "agreement_pct": s.percentage_agreement, "kappa": s.kappa})
        for label, stats in [
            ("Coding - information coverage", reliability_service.information_domain_reliability(db, double_coded)),
            ("Coding - older-adult needs", reliability_service.older_adult_need_reliability(db, double_coded)),
            ("Coding - presentation", reliability_service.presentation_reliability(db, double_coded)),
        ]:
            for s in stats:
                rows.append({"stage": label, "field": s.field_name, "n_pairs": s.n_pairs,
                             "agreement_pct": s.percentage_agreement, "kappa": s.kappa})

    return pd.DataFrame(rows)


@dataclass
class ExportDataset:
    key: str
    label: str
    filename_suffix: str
    builder: Callable[[Session, int], pd.DataFrame]
    required: bool = True  # the 14 datasets from handover doc section 22


EXPORT_DATASETS: list[ExportDataset] = [
    ExportDataset("studies", "Studies", "studies", studies_df),
    ExportDataset("search_queries", "Search queries", "search_queries", search_queries_df),
    ExportDataset("pilot_search_runs", "Pilot search runs", "pilot_search_runs", pilot_search_runs_df),
    ExportDataset("pilot_search_results", "Pilot search results", "pilot_results", pilot_search_results_df),
    ExportDataset("full_search_runs", "Full search runs", "full_search_runs", full_search_runs_df),
    ExportDataset("raw_search_results", "Raw search results", "raw_search_results", raw_search_results_df),
    ExportDataset("unique_videos", "Deduplicated videos", "unique_videos", unique_videos_df),
    ExportDataset("screening", "Screening decisions (canonical)", "screening", screening_df),
    ExportDataset("video_characteristics", "Video characteristics (canonical)", "video_coding", video_characteristics_df),
    ExportDataset("information_domains", "Information coverage coding", "information_domains", information_domains_df),
    ExportDataset("older_adult_needs", "Older-adult-needs coding", "older_adult_needs", older_adult_needs_df),
    ExportDataset("presentation_coding", "Presentation coding", "presentation_coding", presentation_coding_df),
    ExportDataset("accuracy_claims", "Accuracy claims", "accuracy_claims", accuracy_claims_df),
    ExportDataset("reviewers", "Reviewers", "reviewers", reviewers_df),
    ExportDataset(
        "screening_all_reviewers", "Screening decisions (all reviewers)", "screening_all_reviewers",
        screening_all_reviewers_df, required=False,
    ),
    ExportDataset(
        "video_coding_all_reviewers", "Video characteristics (all reviewers)", "video_coding_all_reviewers",
        video_coding_all_reviewers_df, required=False,
    ),
    ExportDataset(
        "reliability_summary", "Reliability summary (agreement/kappa)", "reliability_summary",
        reliability_summary_df, required=False,
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


def build_zip_export(db: Session, study_id: int) -> bytes:
    """All 14 datasets as CSVs bundled into one in-memory ZIP file."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for dataset in EXPORT_DATASETS:
            df = build_dataframe(db, study_id, dataset)
            filename = export_filename(study_id, dataset, "csv")
            zf.writestr(filename, df.to_csv(index=False))
    return buffer.getvalue()
