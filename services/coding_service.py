"""
Video coding workflow logic (Phase 5): saving characteristics + the
information-coverage and older-adult-needs sections in one transaction, and
deriving coding status/progress. See handover doc sections 14-16, 26.

The coding framework itself (items, stable keys, response values) lives in
utils.constants; this module only validates against it. Presentation coding
was removed after researcher user testing and is never written here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from db import crud
from db.models import VideoCoding
from utils.constants import (
    INFORMATION_COVERAGE_ITEMS,
    INFORMATION_COVERAGE_VALUES,
    OLDER_ADULT_NEED_ITEMS,
    OLDER_ADULT_NEED_VALUES,
)

_COVERAGE_KEYS = {item.key for item in INFORMATION_COVERAGE_ITEMS}
_NEED_KEYS = {item.key for item in OLDER_ADULT_NEED_ITEMS}

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


def missing_for_completion(
    information_domain_values: dict[str, str | None],
    older_adult_need_values: dict[str, str | None],
) -> list[str]:
    """Labels of current-framework items still uncoded -- a video can only be
    marked complete once this is empty. Values are {item_key: value}."""
    missing = [
        f"Information coverage: {item.label}"
        for item in INFORMATION_COVERAGE_ITEMS
        if not information_domain_values.get(item.key)
    ]
    missing += [
        f"Older-adult needs: {item.label}"
        for item in OLDER_ADULT_NEED_ITEMS
        if not older_adult_need_values.get(item.key)
    ]
    return missing


def _validate(values: dict, known_keys: set[str], allowed: list[str], section: str) -> None:
    unknown = set(values) - known_keys
    if unknown:
        # Guards against writing rows under legacy (pre-revision) names.
        raise ValueError(f"Unknown {section} item key(s): {sorted(unknown)}")
    for key, (value, _notes) in values.items():
        if value is not None and value not in allowed:
            raise ValueError(f"Invalid {section} value {value!r} for {key}")


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
    accuracy_notes: str | None,
    information_domain_values: dict[str, tuple[str | None, str | None]],
    older_adult_need_values: dict[str, tuple[str | None, str | None]],
    mark_complete: bool,
) -> VideoCoding:
    """Save characteristics + both domain-coding sections for one video in a
    single transaction. Values are dicts of {item_key: (value, notes)}, with
    value None for an item not coded yet.

    mark_complete is only honoured once every current-framework item is
    coded (see missing_for_completion); otherwise the work is still saved,
    as in progress. Check the returned record's status to tell which.
    accuracy_notes is optional free text and never affects completion.
    """
    _validate(information_domain_values, _COVERAGE_KEYS, INFORMATION_COVERAGE_VALUES,
              "information coverage")
    _validate(older_adult_need_values, _NEED_KEYS, OLDER_ADULT_NEED_VALUES, "older-adult needs")

    missing = missing_for_completion(
        {k: v for k, (v, _) in information_domain_values.items()},
        {k: v for k, (v, _) in older_adult_need_values.items()},
    )
    status = STATUS_COMPLETE if mark_complete and not missing else STATUS_IN_PROGRESS

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
        accuracy_notes=accuracy_notes,
        status=status,
    )

    for key, (value, item_notes) in information_domain_values.items():
        crud.upsert_information_domain_code(db, coding.id, key, value, item_notes)
    for key, (value, need_notes) in older_adult_need_values.items():
        # The note answers "If Yes, what did they mention?" -- it's hidden
        # for any other answer, so don't keep a stale one behind a "No".
        crud.upsert_older_adult_need_code(
            db, coding.id, key, value, need_notes if value == "Yes" else None
        )

    db.commit()
    db.refresh(coding)
    return coding
