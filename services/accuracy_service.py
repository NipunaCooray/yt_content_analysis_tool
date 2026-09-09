"""
Claim-level accuracy assessment logic (Phase 6): deriving a per-video review
status and study-wide progress. See handover doc section 18.
"""

from __future__ import annotations

from dataclasses import dataclass

from db.models import AccuracyReviewStatus

STATUS_NOT_STARTED = "Not started"
STATUS_IN_PROGRESS = "In progress"
STATUS_COMPLETE = "Complete"


def accuracy_status(review_status: AccuracyReviewStatus | None, claim_count: int) -> str:
    if review_status is not None and review_status.is_complete:
        return STATUS_COMPLETE
    if claim_count > 0:
        return STATUS_IN_PROGRESS
    return STATUS_NOT_STARTED


@dataclass
class AccuracyProgress:
    total: int
    not_started: int
    in_progress: int
    complete: int


def compute_progress(
    video_pks: list[int],
    review_statuses: dict[int, AccuracyReviewStatus],
    claim_counts: dict[int, int],
) -> AccuracyProgress:
    counts = {STATUS_NOT_STARTED: 0, STATUS_IN_PROGRESS: 0, STATUS_COMPLETE: 0}
    for pk in video_pks:
        status = accuracy_status(review_statuses.get(pk), claim_counts.get(pk, 0))
        counts[status] += 1
    return AccuracyProgress(
        total=len(video_pks),
        not_started=counts[STATUS_NOT_STARTED],
        in_progress=counts[STATUS_IN_PROGRESS],
        complete=counts[STATUS_COMPLETE],
    )
