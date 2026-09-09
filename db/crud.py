"""
Data-access functions. Pages/services should go through here rather than
building queries inline, so business rules (timestamps, audit logging) live
in one place.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    AccuracyClaim,
    AccuracyReviewStatus,
    AuditLog,
    FullSearchRun,
    InformationDomainCode,
    OlderAdultNeedCode,
    PilotSearchResult,
    PilotSearchRun,
    PresentationCode,
    Reviewer,
    ScreeningDecision,
    SearchQuery,
    SearchResultRaw,
    SearchStrategyApproval,
    Study,
    Video,
    VideoCoding,
    utcnow,
)

# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def log_audit_event(
    db: Session,
    action_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    study_id: int | None = None,
    reviewer_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        study_id=study_id,
        reviewer_id=reviewer_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=details or {},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_audit_log(db: Session, study_id: int | None = None) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if study_id is not None:
        stmt = stmt.where(AuditLog.study_id == study_id)
    return list(db.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Studies
# ---------------------------------------------------------------------------


def create_study(db: Session, **fields: Any) -> Study:
    study = Study(**fields)
    db.add(study)
    db.commit()
    db.refresh(study)
    log_audit_event(db, "study_created", "study", study.id, study_id=study.id)
    return study


def get_study(db: Session, study_id: int) -> Study | None:
    return db.get(Study, study_id)


def list_studies(db: Session) -> list[Study]:
    stmt = select(Study).order_by(Study.updated_at.desc())
    return list(db.execute(stmt).scalars().all())


def update_study(db: Session, study_id: int, **fields: Any) -> Study | None:
    study = db.get(Study, study_id)
    if study is None:
        return None
    for key, value in fields.items():
        setattr(study, key, value)
    study.updated_at = utcnow()
    db.commit()
    db.refresh(study)
    log_audit_event(db, "study_updated", "study", study.id, study_id=study.id, details=fields)
    return study


def delete_study(db: Session, study_id: int) -> bool:
    study = db.get(Study, study_id)
    if study is None:
        return False
    db.delete(study)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Reviewers
# ---------------------------------------------------------------------------


def create_reviewer(db: Session, **fields: Any) -> Reviewer:
    reviewer = Reviewer(**fields)
    db.add(reviewer)
    db.commit()
    db.refresh(reviewer)
    return reviewer


def get_reviewer(db: Session, reviewer_id: int) -> Reviewer | None:
    return db.get(Reviewer, reviewer_id)


def list_reviewers(db: Session) -> list[Reviewer]:
    stmt = select(Reviewer).order_by(Reviewer.name)
    return list(db.execute(stmt).scalars().all())


def update_reviewer(db: Session, reviewer_id: int, **fields: Any) -> Reviewer | None:
    reviewer = db.get(Reviewer, reviewer_id)
    if reviewer is None:
        return None
    for key, value in fields.items():
        setattr(reviewer, key, value)
    db.commit()
    db.refresh(reviewer)
    return reviewer


def delete_reviewer(db: Session, reviewer_id: int) -> bool:
    reviewer = db.get(Reviewer, reviewer_id)
    if reviewer is None:
        return False
    db.delete(reviewer)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Search queries
# ---------------------------------------------------------------------------


def create_search_query(db: Session, study_id: int, **fields: Any) -> SearchQuery:
    query = SearchQuery(study_id=study_id, **fields)
    db.add(query)
    db.commit()
    db.refresh(query)
    log_audit_event(
        db, "query_added", "search_query", query.id, study_id=study_id,
        details={"query_text": query.query_text},
    )
    return query


def get_search_query(db: Session, query_id: int) -> SearchQuery | None:
    return db.get(SearchQuery, query_id)


def list_search_queries(
    db: Session,
    study_id: int,
    active_only: bool = False,
    category: str | None = None,
    state_territory: str | None = None,
) -> list[SearchQuery]:
    stmt = select(SearchQuery).where(SearchQuery.study_id == study_id)
    if active_only:
        stmt = stmt.where(SearchQuery.is_active.is_(True))
    if category:
        stmt = stmt.where(SearchQuery.category == category)
    if state_territory:
        stmt = stmt.where(SearchQuery.state_territory == state_territory)
    stmt = stmt.order_by(SearchQuery.created_at)
    return list(db.execute(stmt).scalars().all())


def update_search_query(db: Session, query_id: int, **fields: Any) -> SearchQuery | None:
    query = db.get(SearchQuery, query_id)
    if query is None:
        return None
    for key, value in fields.items():
        setattr(query, key, value)
    query.updated_at = utcnow()
    db.commit()
    db.refresh(query)
    log_audit_event(
        db, "query_edited", "search_query", query.id, study_id=query.study_id, details=fields
    )
    return query


def set_query_active(db: Session, query_id: int, is_active: bool) -> SearchQuery | None:
    query = update_search_query(db, query_id, is_active=is_active)
    if query is not None:
        log_audit_event(
            db,
            "query_disabled" if not is_active else "query_enabled",
            "search_query",
            query.id,
            study_id=query.study_id,
        )
    return query


def duplicate_search_query(db: Session, query_id: int) -> SearchQuery | None:
    original = db.get(SearchQuery, query_id)
    if original is None:
        return None
    copy = SearchQuery(
        study_id=original.study_id,
        category=original.category,
        query_text=f"{original.query_text} (copy)",
        state_territory=original.state_territory,
        notes=original.notes,
        is_active=True,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


def delete_search_query(db: Session, query_id: int) -> bool:
    query = db.get(SearchQuery, query_id)
    if query is None:
        return False
    db.delete(query)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Pilot search runs / results
# ---------------------------------------------------------------------------


def create_pilot_search_run(db: Session, study_id: int, **fields: Any) -> PilotSearchRun:
    run = PilotSearchRun(study_id=study_id, **fields)
    db.add(run)
    db.commit()
    db.refresh(run)
    log_audit_event(db, "pilot_run", "pilot_search_run", run.id, study_id=study_id)
    return run


def list_pilot_search_runs(db: Session, study_id: int) -> list[PilotSearchRun]:
    stmt = (
        select(PilotSearchRun)
        .where(PilotSearchRun.study_id == study_id)
        .order_by(PilotSearchRun.run_timestamp.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_pilot_search_run(db: Session, run_id: int) -> PilotSearchRun | None:
    return db.get(PilotSearchRun, run_id)


def add_pilot_search_result(db: Session, pilot_search_run_id: int, **fields: Any) -> PilotSearchResult:
    result = PilotSearchResult(pilot_search_run_id=pilot_search_run_id, **fields)
    db.add(result)
    return result


def list_pilot_search_results(
    db: Session,
    pilot_search_run_id: int,
    relevance_rating: str | None = None,
    query_id: int | None = None,
) -> list[PilotSearchResult]:
    stmt = select(PilotSearchResult).where(
        PilotSearchResult.pilot_search_run_id == pilot_search_run_id
    )
    if relevance_rating:
        stmt = stmt.where(PilotSearchResult.relevance_rating == relevance_rating)
    if query_id:
        stmt = stmt.where(PilotSearchResult.query_id == query_id)
    stmt = stmt.order_by(PilotSearchResult.query_id, PilotSearchResult.result_rank)
    return list(db.execute(stmt).scalars().all())


def get_pilot_search_result(db: Session, result_id: int) -> PilotSearchResult | None:
    return db.get(PilotSearchResult, result_id)


def update_pilot_result_relevance(
    db: Session,
    result_id: int,
    relevance_rating: str,
    irrelevance_reason: str | None,
    reviewer_notes: str | None,
    reviewer_id: int | None,
) -> PilotSearchResult | None:
    result = db.get(PilotSearchResult, result_id)
    if result is None:
        return None
    result.relevance_rating = relevance_rating
    result.irrelevance_reason = irrelevance_reason if relevance_rating == "Irrelevant" else None
    result.reviewer_notes = reviewer_notes
    result.reviewer_id = reviewer_id
    result.reviewed_at = utcnow()
    db.commit()
    db.refresh(result)
    log_audit_event(
        db,
        "pilot_relevance_assessed",
        "pilot_search_result",
        result.id,
        reviewer_id=reviewer_id,
        details={"relevance_rating": relevance_rating},
    )
    return result


# ---------------------------------------------------------------------------
# Search strategy approval
# ---------------------------------------------------------------------------


def create_search_strategy_approval(db: Session, study_id: int, **fields: Any) -> SearchStrategyApproval:
    approval = SearchStrategyApproval(study_id=study_id, **fields)
    db.add(approval)
    db.commit()
    db.refresh(approval)
    log_audit_event(
        db, "search_strategy_approved", "search_strategy_approval", approval.id, study_id=study_id
    )
    return approval


def list_search_strategy_approvals(db: Session, study_id: int) -> list[SearchStrategyApproval]:
    stmt = (
        select(SearchStrategyApproval)
        .where(SearchStrategyApproval.study_id == study_id)
        .order_by(SearchStrategyApproval.approved_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_latest_approval(db: Session, study_id: int) -> SearchStrategyApproval | None:
    approvals = list_search_strategy_approvals(db, study_id)
    return approvals[0] if approvals else None


# ---------------------------------------------------------------------------
# Full search runs / raw results / deduplicated videos (Phase 3)
# ---------------------------------------------------------------------------


def create_full_search_run(db: Session, study_id: int, **fields: Any) -> FullSearchRun:
    run = FullSearchRun(study_id=study_id, **fields)
    db.add(run)
    db.commit()
    db.refresh(run)
    log_audit_event(db, "full_search_run", "full_search_run", run.id, study_id=study_id)
    return run


def list_full_search_runs(db: Session, study_id: int) -> list[FullSearchRun]:
    stmt = (
        select(FullSearchRun)
        .where(FullSearchRun.study_id == study_id)
        .order_by(FullSearchRun.run_timestamp.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_full_search_run(db: Session, run_id: int) -> FullSearchRun | None:
    return db.get(FullSearchRun, run_id)


def add_search_result_raw(db: Session, full_search_run_id: int, **fields: Any) -> SearchResultRaw:
    result = SearchResultRaw(full_search_run_id=full_search_run_id, **fields)
    db.add(result)
    return result


def list_search_results_raw(
    db: Session,
    study_id: int,
    full_search_run_id: int | None = None,
) -> list[SearchResultRaw]:
    stmt = select(SearchResultRaw).join(
        FullSearchRun, SearchResultRaw.full_search_run_id == FullSearchRun.id
    ).where(FullSearchRun.study_id == study_id)
    if full_search_run_id is not None:
        stmt = stmt.where(SearchResultRaw.full_search_run_id == full_search_run_id)
    stmt = stmt.order_by(SearchResultRaw.query_id, SearchResultRaw.result_rank)
    return list(db.execute(stmt).scalars().all())


def count_search_results_raw(db: Session, study_id: int, full_search_run_id: int | None = None) -> int:
    return len(list_search_results_raw(db, study_id, full_search_run_id))


def get_video_by_youtube_id(db: Session, study_id: int, video_id: str) -> Video | None:
    stmt = select(Video).where(Video.study_id == study_id, Video.video_id == video_id)
    return db.execute(stmt).scalars().first()


def create_video(db: Session, study_id: int, **fields: Any) -> Video:
    video = Video(study_id=study_id, **fields)
    db.add(video)
    return video


def list_videos(db: Session, study_id: int) -> list[Video]:
    stmt = select(Video).where(Video.study_id == study_id).order_by(Video.created_at)
    return list(db.execute(stmt).scalars().all())


def get_video(db: Session, video_pk: int) -> Video | None:
    return db.get(Video, video_pk)


def list_included_videos(db: Session, study_id: int) -> list[Video]:
    """Videos with a screening decision of 'Include' -- the only ones that
    enter the coding workflow (handover doc section 14)."""
    stmt = (
        select(Video)
        .join(ScreeningDecision, ScreeningDecision.video_id == Video.id)
        .where(Video.study_id == study_id, ScreeningDecision.decision == "Include")
        .order_by(Video.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def list_raw_results_for_video(db: Session, study_id: int, video_id: str) -> list[SearchResultRaw]:
    """All raw search-result occurrences (across queries/runs) for one YouTube video."""
    stmt = (
        select(SearchResultRaw)
        .join(FullSearchRun, SearchResultRaw.full_search_run_id == FullSearchRun.id)
        .where(FullSearchRun.study_id == study_id, SearchResultRaw.video_id == video_id)
        .order_by(SearchResultRaw.result_rank)
    )
    return list(db.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Screening decisions (Phase 4)
# ---------------------------------------------------------------------------


def get_screening_decision(db: Session, video_pk: int) -> ScreeningDecision | None:
    stmt = select(ScreeningDecision).where(ScreeningDecision.video_id == video_pk)
    return db.execute(stmt).scalars().first()


def list_screening_decisions(db: Session, study_id: int) -> dict[int, ScreeningDecision]:
    """video_id (PK) -> its screening decision, for batch status lookups."""
    stmt = select(ScreeningDecision).where(ScreeningDecision.study_id == study_id)
    rows = db.execute(stmt).scalars().all()
    return {row.video_id: row for row in rows}


def upsert_screening_decision(
    db: Session,
    study_id: int,
    video_pk: int,
    reviewer_id: int | None,
    decision: str,
    exclusion_reason: str | None,
    notes: str | None,
) -> ScreeningDecision:
    """One screening decision per video: create on first save, otherwise edit
    it in place (screened_at is preserved from the first save; updated_at
    tracks the latest edit via the model's onupdate)."""
    existing = get_screening_decision(db, video_pk)
    if existing is None:
        existing = ScreeningDecision(
            study_id=study_id,
            video_id=video_pk,
            reviewer_id=reviewer_id,
            decision=decision,
            exclusion_reason=exclusion_reason if decision == "Exclude" else None,
            notes=notes,
            screened_at=utcnow(),
        )
        db.add(existing)
        action = "screening_decision_created"
    else:
        existing.reviewer_id = reviewer_id
        existing.decision = decision
        existing.exclusion_reason = exclusion_reason if decision == "Exclude" else None
        existing.notes = notes
        action = "screening_decision_edited"

    db.commit()
    db.refresh(existing)
    log_audit_event(
        db,
        action,
        "screening_decision",
        existing.id,
        study_id=study_id,
        reviewer_id=reviewer_id,
        details={"video_id": video_pk, "decision": decision},
    )
    return existing


# ---------------------------------------------------------------------------
# Video coding (Phase 5)
# ---------------------------------------------------------------------------


def get_video_coding(db: Session, video_pk: int) -> VideoCoding | None:
    stmt = select(VideoCoding).where(VideoCoding.video_id == video_pk)
    return db.execute(stmt).scalars().first()


def list_video_codings(db: Session, study_id: int) -> dict[int, VideoCoding]:
    """video_id (PK) -> its coding record, for batch status lookups."""
    stmt = select(VideoCoding).where(VideoCoding.study_id == study_id)
    rows = db.execute(stmt).scalars().all()
    return {row.video_id: row for row in rows}


def upsert_video_coding(
    db: Session,
    study_id: int,
    video_pk: int,
    reviewer_id: int | None,
    transport_modes: list[str],
    jurisdictions: list[str],
    uploader_type: str | None,
    intended_audience: str | None,
    older_adult_targeted: str | None,
    notes: str | None,
    status: str,
) -> VideoCoding:
    """One coding record per video: create on first save, otherwise edit it
    in place (coded_at is preserved from the first save)."""
    existing = get_video_coding(db, video_pk)
    if existing is None:
        existing = VideoCoding(
            study_id=study_id,
            video_id=video_pk,
            reviewer_id=reviewer_id,
            transport_modes_json=transport_modes,
            jurisdictions_json=jurisdictions,
            uploader_type=uploader_type,
            intended_audience=intended_audience,
            older_adult_targeted=older_adult_targeted,
            notes=notes,
            status=status,
            coded_at=utcnow(),
        )
        db.add(existing)
        db.flush()  # assign existing.id for the sub-table upserts that follow
        action = "video_coding_created"
    else:
        existing.reviewer_id = reviewer_id
        existing.transport_modes_json = transport_modes
        existing.jurisdictions_json = jurisdictions
        existing.uploader_type = uploader_type
        existing.intended_audience = intended_audience
        existing.older_adult_targeted = older_adult_targeted
        existing.notes = notes
        existing.status = status
        action = "video_coding_edited"

    log_audit_event(
        db, action, "video_coding", None, study_id=study_id, reviewer_id=reviewer_id,
        details={"video_id": video_pk, "status": status},
    )
    return existing


def list_information_domain_codes(db: Session, video_coding_id: int) -> dict[str, InformationDomainCode]:
    stmt = select(InformationDomainCode).where(
        InformationDomainCode.video_coding_id == video_coding_id
    )
    return {row.domain_name: row for row in db.execute(stmt).scalars().all()}


def upsert_information_domain_code(
    db: Session, video_coding_id: int, domain_name: str, value: str, notes: str | None
) -> InformationDomainCode:
    stmt = select(InformationDomainCode).where(
        InformationDomainCode.video_coding_id == video_coding_id,
        InformationDomainCode.domain_name == domain_name,
    )
    existing = db.execute(stmt).scalars().first()
    if existing is None:
        existing = InformationDomainCode(
            video_coding_id=video_coding_id, domain_name=domain_name, value=value, notes=notes
        )
        db.add(existing)
    else:
        existing.value = value
        existing.notes = notes
    return existing


def list_older_adult_need_codes(db: Session, video_coding_id: int) -> dict[str, OlderAdultNeedCode]:
    stmt = select(OlderAdultNeedCode).where(OlderAdultNeedCode.video_coding_id == video_coding_id)
    return {row.need_name: row for row in db.execute(stmt).scalars().all()}


def upsert_older_adult_need_code(
    db: Session, video_coding_id: int, need_name: str, value: str, notes: str | None
) -> OlderAdultNeedCode:
    stmt = select(OlderAdultNeedCode).where(
        OlderAdultNeedCode.video_coding_id == video_coding_id,
        OlderAdultNeedCode.need_name == need_name,
    )
    existing = db.execute(stmt).scalars().first()
    if existing is None:
        existing = OlderAdultNeedCode(
            video_coding_id=video_coding_id, need_name=need_name, value=value, notes=notes
        )
        db.add(existing)
    else:
        existing.value = value
        existing.notes = notes
    return existing


def list_presentation_codes(db: Session, video_coding_id: int) -> dict[str, PresentationCode]:
    stmt = select(PresentationCode).where(PresentationCode.video_coding_id == video_coding_id)
    return {row.item_name: row for row in db.execute(stmt).scalars().all()}


def upsert_presentation_code(
    db: Session, video_coding_id: int, item_name: str, value: str, notes: str | None
) -> PresentationCode:
    stmt = select(PresentationCode).where(
        PresentationCode.video_coding_id == video_coding_id,
        PresentationCode.item_name == item_name,
    )
    existing = db.execute(stmt).scalars().first()
    if existing is None:
        existing = PresentationCode(
            video_coding_id=video_coding_id, item_name=item_name, value=value, notes=notes
        )
        db.add(existing)
    else:
        existing.value = value
        existing.notes = notes
    return existing


# ---------------------------------------------------------------------------
# Accuracy claims (Phase 6)
# ---------------------------------------------------------------------------


def create_accuracy_claim(db: Session, study_id: int, video_pk: int, **fields: Any) -> AccuracyClaim:
    claim = AccuracyClaim(study_id=study_id, video_id=video_pk, **fields)
    db.add(claim)
    db.commit()
    db.refresh(claim)
    log_audit_event(
        db, "accuracy_claim_added", "accuracy_claim", claim.id, study_id=study_id,
        reviewer_id=claim.reviewer_id, details={"video_id": video_pk, "category": claim.category},
    )
    return claim


def list_accuracy_claims(db: Session, study_id: int, video_pk: int) -> list[AccuracyClaim]:
    stmt = (
        select(AccuracyClaim)
        .where(AccuracyClaim.study_id == study_id, AccuracyClaim.video_id == video_pk)
        .order_by(AccuracyClaim.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def count_accuracy_claims(db: Session, study_id: int) -> dict[int, int]:
    """video_id (PK) -> number of claims recorded, for batch status lookups."""
    stmt = select(AccuracyClaim.video_id).where(AccuracyClaim.study_id == study_id)
    counts: dict[int, int] = {}
    for (video_pk,) in db.execute(stmt).all():
        counts[video_pk] = counts.get(video_pk, 0) + 1
    return counts


def get_accuracy_claim(db: Session, claim_id: int) -> AccuracyClaim | None:
    return db.get(AccuracyClaim, claim_id)


def update_accuracy_claim(db: Session, claim_id: int, **fields: Any) -> AccuracyClaim | None:
    claim = db.get(AccuracyClaim, claim_id)
    if claim is None:
        return None
    for key, value in fields.items():
        setattr(claim, key, value)
    claim.updated_at = utcnow()
    db.commit()
    db.refresh(claim)
    log_audit_event(
        db, "accuracy_claim_edited", "accuracy_claim", claim.id, study_id=claim.study_id,
        reviewer_id=claim.reviewer_id, details=fields,
    )
    return claim


def delete_accuracy_claim(db: Session, claim_id: int) -> bool:
    claim = db.get(AccuracyClaim, claim_id)
    if claim is None:
        return False
    study_id = claim.study_id
    video_pk = claim.video_id
    db.delete(claim)
    db.commit()
    log_audit_event(
        db, "accuracy_claim_deleted", "accuracy_claim", claim_id, study_id=study_id,
        details={"video_id": video_pk},
    )
    return True


def get_accuracy_review_status(db: Session, video_pk: int) -> AccuracyReviewStatus | None:
    stmt = select(AccuracyReviewStatus).where(AccuracyReviewStatus.video_id == video_pk)
    return db.execute(stmt).scalars().first()


def list_accuracy_review_statuses(db: Session, study_id: int) -> dict[int, AccuracyReviewStatus]:
    """video_id (PK) -> its review-completion record, for batch status lookups."""
    stmt = select(AccuracyReviewStatus).where(AccuracyReviewStatus.study_id == study_id)
    rows = db.execute(stmt).scalars().all()
    return {row.video_id: row for row in rows}


def set_accuracy_review_complete(
    db: Session, study_id: int, video_pk: int, reviewer_id: int | None, is_complete: bool
) -> AccuracyReviewStatus:
    existing = get_accuracy_review_status(db, video_pk)
    if existing is None:
        existing = AccuracyReviewStatus(
            study_id=study_id,
            video_id=video_pk,
            reviewer_id=reviewer_id,
            is_complete=is_complete,
            completed_at=utcnow() if is_complete else None,
        )
        db.add(existing)
    else:
        existing.reviewer_id = reviewer_id
        existing.is_complete = is_complete
        existing.completed_at = utcnow() if is_complete else None
    db.commit()
    db.refresh(existing)
    log_audit_event(
        db,
        "accuracy_review_marked_complete" if is_complete else "accuracy_review_reopened",
        "accuracy_review_status",
        existing.id,
        study_id=study_id,
        reviewer_id=reviewer_id,
        details={"video_id": video_pk},
    )
    return existing
