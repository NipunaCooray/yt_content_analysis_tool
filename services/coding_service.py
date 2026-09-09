"""
Video coding workflow logic (Phase 5): saving characteristics + the three
domain-coding sections in one transaction, and deriving coding status/
progress. See handover doc sections 14-17, 26.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from db import crud
from db.models import VideoCoding

STATUS_NOT_STARTED = "Not started"
STATUS_IN_PROGRESS = "In progress"
STATUS_COMPLETE = "Complete"


def coding_status(coding: VideoCoding | None) -> str:
    if coding is None or not coding.status:
        return STATUS_NOT_STARTED
    return coding.status


@dataclass
class CodingProgress:
    total: int
    not_started: int
    in_progress: int
    complete: int


def compute_progress(video_pks: list[int], codings: dict[int, VideoCoding]) -> CodingProgress:
    counts = {STATUS_NOT_STARTED: 0, STATUS_IN_PROGRESS: 0, STATUS_COMPLETE: 0}
    for pk in video_pks:
        counts[coding_status(codings.get(pk))] += 1
    return CodingProgress(
        total=len(video_pks),
        not_started=counts[STATUS_NOT_STARTED],
        in_progress=counts[STATUS_IN_PROGRESS],
        complete=counts[STATUS_COMPLETE],
    )


def save_video_coding(
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
    information_domain_values: dict[str, tuple[str, str | None]],
    older_adult_need_values: dict[str, tuple[str, str | None]],
    presentation_values: dict[str, tuple[str, str | None]],
    mark_complete: bool,
) -> VideoCoding:
    """Save characteristics + all three domain-coding sections for one video
    in a single transaction. Values are dicts of {name: (value, notes)}."""
    status = STATUS_COMPLETE if mark_complete else STATUS_IN_PROGRESS

    coding = crud.upsert_video_coding(
        db,
        study_id=study_id,
        video_pk=video_pk,
        reviewer_id=reviewer_id,
        transport_modes=transport_modes,
        jurisdictions=jurisdictions,
        uploader_type=uploader_type,
        intended_audience=intended_audience,
        older_adult_targeted=older_adult_targeted,
        notes=notes,
        status=status,
    )

    for domain, (value, domain_notes) in information_domain_values.items():
        crud.upsert_information_domain_code(db, coding.id, domain, value, domain_notes)
    for need, (value, need_notes) in older_adult_need_values.items():
        crud.upsert_older_adult_need_code(db, coding.id, need, value, need_notes)
    for item, (value, item_notes) in presentation_values.items():
        crud.upsert_presentation_code(db, coding.id, item, value, item_notes)

    db.commit()
    db.refresh(coding)
    return coding
