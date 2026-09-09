"""
Screening workflow logic (Phase 4): deriving a per-video screening status
and summarising study-wide screening progress. See handover doc section 13.
"""

from __future__ import annotations

from dataclasses import dataclass

from db.models import ScreeningDecision, Video

STATUS_NOT_SCREENED = "Not screened"
STATUS_INCLUDED = "Included"
STATUS_EXCLUDED = "Excluded"
STATUS_UNSURE = "Unsure"

_DECISION_TO_STATUS = {
    "Include": STATUS_INCLUDED,
    "Exclude": STATUS_EXCLUDED,
    "Unsure": STATUS_UNSURE,
}


def screening_status(decision: ScreeningDecision | None) -> str:
    if decision is None or not decision.decision:
        return STATUS_NOT_SCREENED
    return _DECISION_TO_STATUS.get(decision.decision, STATUS_NOT_SCREENED)


@dataclass
class ScreeningProgress:
    total: int
    not_screened: int
    included: int
    excluded: int
    unsure: int


def compute_progress(videos: list[Video], decisions: dict[int, ScreeningDecision]) -> ScreeningProgress:
    counts = {STATUS_NOT_SCREENED: 0, STATUS_INCLUDED: 0, STATUS_EXCLUDED: 0, STATUS_UNSURE: 0}
    for v in videos:
        counts[screening_status(decisions.get(v.id))] += 1
    return ScreeningProgress(
        total=len(videos),
        not_screened=counts[STATUS_NOT_SCREENED],
        included=counts[STATUS_INCLUDED],
        excluded=counts[STATUS_EXCLUDED],
        unsure=counts[STATUS_UNSURE],
    )
