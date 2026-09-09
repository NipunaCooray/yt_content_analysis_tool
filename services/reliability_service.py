"""
Inter-rater reliability for double-coded videos (Phase 8): percentage
agreement and Cohen's kappa for screening decisions and coding fields.
See handover doc section 20 and the study-initiation guide sections 32/42/43.

Reviewer-scoped screening/coding records already exist in the database (see
db/crud.py); this module only reads them and computes statistics -- it never
writes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from db import crud
from db.models import Video
from utils.constants import INFORMATION_DOMAINS, OLDER_ADULT_NEEDS, PRESENTATION_ITEMS

# ---------------------------------------------------------------------------
# Generic agreement statistics
# ---------------------------------------------------------------------------


def percentage_agreement(pairs: list[tuple[str, str]]) -> float | None:
    """% of pairs where both reviewers gave the same value."""
    if not pairs:
        return None
    agree = sum(1 for a, b in pairs if a == b)
    return round(agree / len(pairs) * 100, 1)


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters over categorical pairs. None if there
    aren't enough pairs, or if fewer than two categories appear (kappa is
    undefined for a constant variable)."""
    if not pairs:
        return None
    n = len(pairs)
    categories = sorted({v for pair in pairs for v in pair})
    if len(categories) < 2:
        return None

    po = sum(1 for a, b in pairs if a == b) / n
    count_a = Counter(a for a, _ in pairs)
    count_b = Counter(b for _, b in pairs)
    pe = sum((count_a.get(c, 0) / n) * (count_b.get(c, 0) / n) for c in categories)

    if pe >= 1:
        return 1.0 if po == 1 else 0.0
    return round((po - pe) / (1 - pe), 3)


def jaccard_similarity(pairs: list[tuple[frozenset, frozenset]]) -> float | None:
    """Average set-overlap for multi-select fields (transport modes,
    jurisdictions), where exact-match kappa isn't the right measure."""
    if not pairs:
        return None
    scores = []
    for a, b in pairs:
        if not a and not b:
            scores.append(1.0)
            continue
        union = a | b
        if not union:
            continue
        scores.append(len(a & b) / len(union))
    if not scores:
        return None
    return round(sum(scores) / len(scores) * 100, 1)


@dataclass
class FieldReliability:
    field_name: str
    n_pairs: int
    percentage_agreement: float | None
    kappa: float | None  # None for set-valued fields (jaccard used instead)


@dataclass
class Disagreement:
    video_pk: int
    video_title: str
    field_name: str
    reviewer_a_name: str
    reviewer_a_value: str
    reviewer_b_name: str
    reviewer_b_value: str


# ---------------------------------------------------------------------------
# Pair building
# ---------------------------------------------------------------------------


def _first_two(records: list) -> tuple | None:
    """The first two chronologically-recorded records, if at least two exist."""
    if len(records) < 2:
        return None
    return records[0], records[1]


def double_coded_videos(
    db: Session, study_id: int, videos: list[Video], stage: str
) -> list[Video]:
    """Videos that actually have 2+ independent reviewer records for the
    given stage ('screening' or 'coding') -- not just videos selected into
    the sample, but ones a second reviewer has actually completed."""
    result = []
    for v in videos:
        records = (
            crud.list_screening_decisions_for_video(db, v.id) if stage == "screening"
            else crud.list_video_codings_for_video(db, v.id)
        )
        if len(records) >= 2:
            result.append(v)
    return result


def screening_reliability(
    db: Session, study_id: int, videos: list[Video]
) -> tuple[FieldReliability, list[Disagreement]]:
    pairs: list[tuple[str, str]] = []
    disagreements: list[Disagreement] = []
    reviewer_names = {r.id: r.name for r in crud.list_reviewers(db)}

    for v in videos:
        records = crud.list_screening_decisions_for_video(db, v.id)
        found = _first_two(records)
        if not found:
            continue
        a, b = found
        if not a.decision or not b.decision:
            continue
        pairs.append((a.decision, b.decision))
        if a.decision != b.decision:
            disagreements.append(Disagreement(
                video_pk=v.id, video_title=v.title or v.video_id, field_name="Screening decision",
                reviewer_a_name=reviewer_names.get(a.reviewer_id, "Unknown"),
                reviewer_a_value=a.decision,
                reviewer_b_name=reviewer_names.get(b.reviewer_id, "Unknown"),
                reviewer_b_value=b.decision,
            ))

    stat = FieldReliability(
        field_name="Screening decision", n_pairs=len(pairs),
        percentage_agreement=percentage_agreement(pairs), kappa=cohens_kappa(pairs),
    )
    return stat, disagreements


# Single-value coding characteristic fields worth a kappa.
_CODING_CATEGORICAL_FIELDS = ["uploader_type", "intended_audience", "older_adult_targeted"]
_CODING_FIELD_LABELS = {
    "uploader_type": "Uploader type",
    "intended_audience": "Audience",
    "older_adult_targeted": "Aimed at older adults?",
}
_CODING_SET_FIELDS = ["transport_modes_json", "jurisdictions_json"]
_CODING_SET_LABELS = {
    "transport_modes_json": "Transport mode(s)",
    "jurisdictions_json": "Jurisdiction(s)",
}


def coding_characteristics_reliability(
    db: Session, study_id: int, videos: list[Video]
) -> tuple[list[FieldReliability], list[Disagreement]]:
    reviewer_names = {r.id: r.name for r in crud.list_reviewers(db)}
    field_pairs: dict[str, list[tuple[str, str]]] = {f: [] for f in _CODING_CATEGORICAL_FIELDS}
    set_pairs: dict[str, list[tuple[frozenset, frozenset]]] = {f: [] for f in _CODING_SET_FIELDS}
    disagreements: list[Disagreement] = []

    for v in videos:
        records = crud.list_video_codings_for_video(db, v.id)
        found = _first_two(records)
        if not found:
            continue
        a, b = found

        for field_name in _CODING_CATEGORICAL_FIELDS:
            va, vb = getattr(a, field_name), getattr(b, field_name)
            if not va or not vb:
                continue
            field_pairs[field_name].append((va, vb))
            if va != vb:
                disagreements.append(Disagreement(
                    video_pk=v.id, video_title=v.title or v.video_id,
                    field_name=_CODING_FIELD_LABELS[field_name],
                    reviewer_a_name=reviewer_names.get(a.reviewer_id, "Unknown"), reviewer_a_value=va,
                    reviewer_b_name=reviewer_names.get(b.reviewer_id, "Unknown"), reviewer_b_value=vb,
                ))

        for field_name in _CODING_SET_FIELDS:
            va = frozenset(getattr(a, field_name) or [])
            vb = frozenset(getattr(b, field_name) or [])
            set_pairs[field_name].append((va, vb))
            if va != vb:
                disagreements.append(Disagreement(
                    video_pk=v.id, video_title=v.title or v.video_id,
                    field_name=_CODING_SET_LABELS[field_name],
                    reviewer_a_name=reviewer_names.get(a.reviewer_id, "Unknown"),
                    reviewer_a_value=", ".join(sorted(va)) or "(none)",
                    reviewer_b_name=reviewer_names.get(b.reviewer_id, "Unknown"),
                    reviewer_b_value=", ".join(sorted(vb)) or "(none)",
                ))

    stats = [
        FieldReliability(
            field_name=_CODING_FIELD_LABELS[f], n_pairs=len(pairs),
            percentage_agreement=percentage_agreement(pairs), kappa=cohens_kappa(pairs),
        )
        for f, pairs in field_pairs.items()
    ]
    stats += [
        FieldReliability(
            field_name=_CODING_SET_LABELS[f], n_pairs=len(pairs),
            percentage_agreement=jaccard_similarity(pairs), kappa=None,
        )
        for f, pairs in set_pairs.items()
    ]
    return stats, disagreements


def _domain_code_reliability(
    db: Session, videos: list[Video], names: list[str], list_codes_fn
) -> list[FieldReliability]:
    field_pairs: dict[str, list[tuple[str, str]]] = {name: [] for name in names}

    for v in videos:
        codings = crud.list_video_codings_for_video(db, v.id)
        found = _first_two(codings)
        if not found:
            continue
        coding_a, coding_b = found
        codes_a = list_codes_fn(db, coding_a.id)
        codes_b = list_codes_fn(db, coding_b.id)
        for name in names:
            ca, cb = codes_a.get(name), codes_b.get(name)
            if ca and cb and ca.value and cb.value:
                field_pairs[name].append((ca.value, cb.value))

    return [
        FieldReliability(
            field_name=name, n_pairs=len(pairs),
            percentage_agreement=percentage_agreement(pairs), kappa=cohens_kappa(pairs),
        )
        for name, pairs in field_pairs.items()
    ]


def information_domain_reliability(db: Session, videos: list[Video]) -> list[FieldReliability]:
    return _domain_code_reliability(
        db, videos, INFORMATION_DOMAINS, crud.list_information_domain_codes
    )


def older_adult_need_reliability(db: Session, videos: list[Video]) -> list[FieldReliability]:
    return _domain_code_reliability(
        db, videos, OLDER_ADULT_NEEDS, crud.list_older_adult_need_codes
    )


def presentation_reliability(db: Session, videos: list[Video]) -> list[FieldReliability]:
    return _domain_code_reliability(
        db, videos, PRESENTATION_ITEMS, crud.list_presentation_codes
    )
