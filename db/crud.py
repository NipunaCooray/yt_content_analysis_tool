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
    AuditLog,
    PilotSearchResult,
    PilotSearchRun,
    Reviewer,
    SearchQuery,
    SearchStrategyApproval,
    Study,
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
