"""
SQLAlchemy ORM models implementing the schema in handover doc section 24.

Controlled-vocabulary fields (decision/rating/category values, etc.) are
plain String columns validated against utils.constants in the service/UI
layer, not enforced as DB-level enums -- this keeps the coding framework
easy to extend without a migration (see handover doc section 15/30).
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime.datetime:
    # Naive UTC datetime (SQLite DateTime columns aren't timezone-aware; keeping
    # every stored timestamp naive-UTC avoids naive/aware comparison errors).
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Core / study setup
# ---------------------------------------------------------------------------


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(100), default="Australia")
    language: Mapped[str] = mapped_column(String(100), default="English")
    search_date: Mapped[datetime.date | None] = mapped_column(DateTime)
    default_results_per_query: Mapped[int] = mapped_column(Integer, default=10)
    search_order: Mapped[str] = mapped_column(String(50), default="relevance")
    search_status: Mapped[str] = mapped_column(String(50), default="Draft")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    search_queries: Mapped[list["SearchQuery"]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )


class Reviewer(Base):
    __tablename__ = "reviewers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    initials: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Search strategy
# ---------------------------------------------------------------------------


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    query_text: Mapped[str] = mapped_column(String(500), nullable=False)
    state_territory: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    study: Mapped["Study"] = relationship(back_populates="search_queries")


class PilotSearchRun(Base):
    __tablename__ = "pilot_search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    run_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    results_per_query: Mapped[int] = mapped_column(Integer, default=10)
    search_order: Mapped[str] = mapped_column(String(50), default="relevance")
    parameters_json: Mapped[dict | None] = mapped_column(JSON)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    results: Mapped[list["PilotSearchResult"]] = relationship(
        back_populates="pilot_search_run", cascade="all, delete-orphan"
    )


class PilotSearchResult(Base):
    __tablename__ = "pilot_search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pilot_search_run_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_search_runs.id"), nullable=False
    )
    query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(String(50), nullable=False)
    result_rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    channel_title: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    video_url: Mapped[str | None] = mapped_column(String(500))
    relevance_rating: Mapped[str] = mapped_column(String(50), default="Not yet reviewed")
    irrelevance_reason: Mapped[str | None] = mapped_column(String(100))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    raw_json: Mapped[dict | None] = mapped_column(JSON)

    pilot_search_run: Mapped["PilotSearchRun"] = relationship(back_populates="results")
    query: Mapped["SearchQuery"] = relationship()


class SearchStrategyApproval(Base):
    __tablename__ = "search_strategy_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    approved_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    query_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    parameters_json: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Full search (Phase 3 - schema present now, UI built later)
# ---------------------------------------------------------------------------


class FullSearchRun(Base):
    __tablename__ = "full_search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    run_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("search_strategy_approvals.id"))
    parameters_json: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)


class SearchResultRaw(Base):
    __tablename__ = "search_results_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_search_run_id: Mapped[int] = mapped_column(
        ForeignKey("full_search_runs.id"), nullable=False
    )
    query_id: Mapped[int] = mapped_column(ForeignKey("search_queries.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(String(50), nullable=False)
    result_rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    channel_title: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    video_url: Mapped[str | None] = mapped_column(String(500))
    raw_json: Mapped[dict | None] = mapped_column(JSON)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("study_id", "video_id", name="uq_study_video"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    channel_id: Mapped[str | None] = mapped_column(String(100))
    channel_title: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    view_count: Mapped[int | None] = mapped_column(Integer)
    like_count: Mapped[int | None] = mapped_column(Integer)
    tags_json: Mapped[list | None] = mapped_column(JSON)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    video_url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    study: Mapped["Study"] = relationship(back_populates="videos")


# ---------------------------------------------------------------------------
# Screening (Phase 4)
# ---------------------------------------------------------------------------


class ScreeningDecision(Base):
    __tablename__ = "screening_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    decision: Mapped[str | None] = mapped_column(String(20))
    exclusion_reason: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    screened_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# Coding (Phase 5)
# ---------------------------------------------------------------------------


class VideoCoding(Base):
    __tablename__ = "video_coding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    transport_modes_json: Mapped[list | None] = mapped_column(JSON)
    jurisdictions_json: Mapped[list | None] = mapped_column(JSON)
    uploader_type: Mapped[str | None] = mapped_column(String(100))
    intended_audience: Mapped[str | None] = mapped_column(String(100))
    older_adult_targeted: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Not started")
    coded_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class InformationDomainCode(Base):
    __tablename__ = "information_domain_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_coding_id: Mapped[int] = mapped_column(ForeignKey("video_coding.id"), nullable=False)
    domain_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)


class OlderAdultNeedCode(Base):
    __tablename__ = "older_adult_need_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_coding_id: Mapped[int] = mapped_column(ForeignKey("video_coding.id"), nullable=False)
    need_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)


class PresentationCode(Base):
    __tablename__ = "presentation_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_coding_id: Mapped[int] = mapped_column(ForeignKey("video_coding.id"), nullable=False)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Accuracy assessment (Phase 6)
# ---------------------------------------------------------------------------


class AccuracyClaim(Base):
    __tablename__ = "accuracy_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    official_source_url: Mapped[str | None] = mapped_column(String(1000))
    assessment: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class AccuracyReviewStatus(Base):
    __tablename__ = "accuracy_review_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int | None] = mapped_column(ForeignKey("studies.id"))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
