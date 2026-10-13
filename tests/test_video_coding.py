"""Phase 5: video coding -- characteristics (plus the optional free-text
accuracy notes), and the two domain-coding sections (information coverage,
older-adult needs) as revised after researcher user testing. Presentation
coding and the claim-level accuracy assessment were removed: legacy rows are
preserved, but no new ones are collected and completion doesn't need them."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from db import crud
from db.models import (
    AccuracyClaim,
    AccuracyReviewStatus,
    InformationDomainCode,
    OlderAdultNeedCode,
    PresentationCode,
)
from services import coding_service
from tests.coding_helpers import full_information_coverage, full_older_adult_needs
from utils.constants import (
    ACCURACY_NOTES_HELP,
    ACCURACY_NOTES_LABEL,
    INFORMATION_COVERAGE_CATEGORIES,
    INFORMATION_COVERAGE_ITEMS,
    OLDER_ADULT_NEED_ITEMS,
    OLDER_ADULT_NEED_VALUES,
)

# The framework exactly as requested in the user-testing modifications brief.
REQUESTED_FRAMEWORK = {
    "General Public Transport Information": [
        "What types of modes are available",
        "Benefits of taking public transport",
        "When/why public transport is better than driving",
    ],
    "Journey Planning": [
        "Destination selection",
        "Using app/website to plan route",
        "How to identify routes, stops, transfer points",
        "Reading timetables/schedules",
        "Estimate travel times",
    ],
    "Payment": [
        "How to pay",
        "When to pay",
        "What to use to pay",
        "Fare cost and other concessions",
    ],
    "Stop / Station / Platform / Wharf Information": [
        "How to find correct stop / station / platform / wharf",
        "How to exit correct stop / station / platform / wharf",
    ],
    "Riding the Service": [
        "Accessibility features",
        "Any specific rules",
        "Etiquette when taking service",
    ],
    "During the Trip": [
        "Announcements — visual and/or audio",
        "Safety considerations",
        "How to request a stop — if applicable",
        "Preparing to get off",
    ],
    "Transfers and Connections": [
        "Steps to navigate multimodal connections / transfers",
        "How to find connections",
        "Reading transfer times",
        "What to do if a connection / transfer is missed",
    ],
    "Miscellaneous": [
        "Emergency contact points",
        "How to contact staff",
        "What staff can help with",
        "What to do if the wrong service is caught",
        "What to do if there is a delay",
    ],
}
REQUESTED_NEEDS = ["Journey Planning", "Payment", "Accessibility and safety", "Assistance seeking"]


@pytest.fixture()
def study_with_included_video(db_session):
    study = crud.create_study(db_session, name="Coding test study")
    reviewer = crud.create_reviewer(db_session, name="Jane Doe", initials="JD")
    included = crud.create_video(
        db_session, study_id=study.id, video_id="vidIncluded", title="Included video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    excluded = crud.create_video(
        db_session, study_id=study.id, video_id="vidExcluded", title="Excluded video",
        channel_title="Chan", published_at=datetime.datetime(2024, 1, 1),
    )
    db_session.commit()
    db_session.refresh(included)
    db_session.refresh(excluded)

    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=included.id, reviewer_id=reviewer.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    crud.upsert_screening_decision(
        db_session, study_id=study.id, video_pk=excluded.id, reviewer_id=reviewer.id,
        decision="Exclude", exclusion_reason="Other", notes=None,
    )
    return study, reviewer, included, excluded


def _save(db_session, study, video, reviewer_id, info, needs, mark_complete=False, **characteristics):
    fields = dict(
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type=None,
        intended_audience=None, older_adult_targeted=None, notes=None, accuracy_notes=None,
    )
    fields.update(characteristics)
    return coding_service.save_video_coding(
        db_session, study_id=study.id, video_pk=video.id, reviewer_id=reviewer_id,
        information_domain_values=info, older_adult_need_values=needs,
        mark_complete=mark_complete, **fields,
    )


# ---------------------------------------------------------------------------
# Framework definition
# ---------------------------------------------------------------------------


def test_information_coverage_has_the_eight_requested_categories_in_order():
    assert INFORMATION_COVERAGE_CATEGORIES == list(REQUESTED_FRAMEWORK)


def test_information_coverage_has_every_requested_item_under_its_category():
    actual = {
        category: [i.label for i in INFORMATION_COVERAGE_ITEMS if i.category == category]
        for category in INFORMATION_COVERAGE_CATEGORIES
    }
    assert actual == REQUESTED_FRAMEWORK


def test_any_specific_rules_carries_its_examples_as_helper_text_only():
    item = next(i for i in INFORMATION_COVERAGE_ITEMS if i.key == "riding_specific_rules")
    assert item.label == "Any specific rules"
    for example in ["requesting the service", "priority seating", "boarding requirements",
                    "service-specific rules"]:
        assert example in item.help


def test_item_keys_are_unique_and_stable_identifiers():
    keys = [i.key for i in INFORMATION_COVERAGE_ITEMS] + [i.key for i in OLDER_ADULT_NEED_ITEMS]
    assert len(keys) == len(set(keys))
    assert all(k.isidentifier() and k == k.lower() for k in keys)
    assert "journey_route_planner" in keys


def test_older_adult_needs_is_exactly_four_yes_no_items():
    assert [i.label for i in OLDER_ADULT_NEED_ITEMS] == REQUESTED_NEEDS
    assert [i.key for i in OLDER_ADULT_NEED_ITEMS] == [
        "older_journey_planning", "older_payment", "older_accessibility_safety",
        "older_assistance_seeking",
    ]
    assert OLDER_ADULT_NEED_VALUES == ["Yes", "No"]


# ---------------------------------------------------------------------------
# Saving / reloading
# ---------------------------------------------------------------------------


def test_list_included_videos_only_returns_included(db_session, study_with_included_video):
    study, reviewer, included, excluded = study_with_included_video
    videos = crud.list_included_videos(db_session, study.id)
    assert [v.id for v in videos] == [included.id]


def test_coding_status_defaults_to_not_started():
    assert coding_service.coding_status(None) == coding_service.STATUS_NOT_STARTED


def test_information_coverage_values_and_notes_save_and_reload(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    info = full_information_coverage(
        "Absent", payment_how_to_pay=("Present", "Shows tapping an Opal card."),
        trip_request_stop=("Not applicable", None), misc_delay=("Unclear", None),
    )
    coding = _save(db_session, study, included, reviewer.id, info, full_older_adult_needs())

    codes = crud.list_information_domain_codes(db_session, coding.id)
    assert set(codes) == {i.key for i in INFORMATION_COVERAGE_ITEMS}
    assert codes["payment_how_to_pay"].value == "Present"
    assert codes["payment_how_to_pay"].notes == "Shows tapping an Opal card."
    assert codes["trip_request_stop"].value == "Not applicable"
    assert codes["misc_delay"].value == "Unclear"
    assert codes["journey_route_planner"].value == "Absent"


def test_uncoded_items_are_stored_as_uncoded_not_given_a_default(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    info = {i.key: (None, None) for i in INFORMATION_COVERAGE_ITEMS}
    info["payment_how_to_pay"] = ("Present", None)
    needs = {i.key: (None, None) for i in OLDER_ADULT_NEED_ITEMS}
    coding = _save(db_session, study, included, reviewer.id, info, needs)

    codes = crud.list_information_domain_codes(db_session, coding.id)
    assert codes["payment_how_to_pay"].value == "Present"
    assert codes["payment_when_to_pay"].value is None
    assert all(r.value is None for r in crud.list_older_adult_need_codes(db_session, coding.id).values())


def test_older_adult_needs_save_with_item_specific_notes(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    needs = full_older_adult_needs(
        older_journey_planning=("Yes", "Uses the trip planner app."),
        older_accessibility_safety=("Yes", "Mentions priority seating and step-free boarding."),
        older_payment=("No", None),
    )
    coding = _save(db_session, study, included, reviewer.id, full_information_coverage(), needs)

    codes = crud.list_older_adult_need_codes(db_session, coding.id)
    assert len(codes) == 4
    assert codes["older_journey_planning"].value == "Yes"
    assert codes["older_journey_planning"].notes == "Uses the trip planner app."
    # Each need keeps its own note -- one never overwrites another.
    assert codes["older_accessibility_safety"].notes == "Mentions priority seating and step-free boarding."
    assert codes["older_payment"].value == "No"
    assert codes["older_assistance_seeking"].value == "No"


def test_older_adult_need_note_is_dropped_when_answer_is_not_yes(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    _save(db_session, study, included, reviewer.id, full_information_coverage(),
          full_older_adult_needs(older_payment=("Yes", "Concession fares")))
    coding = _save(db_session, study, included, reviewer.id, full_information_coverage(),
                   full_older_adult_needs(older_payment=("No", "Concession fares")))
    assert crud.list_older_adult_need_codes(db_session, coding.id)["older_payment"].notes is None


def test_save_video_coding_upserts_in_place_without_duplicating_rows(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    first = _save(db_session, study, included, reviewer.id, full_information_coverage(),
                  full_older_adult_needs())
    second = _save(
        db_session, study, included, reviewer.id,
        full_information_coverage(payment_how_to_pay=("Present", "Changed my mind")),
        full_older_adult_needs(older_payment=("Yes", "Fares")), transport_modes=["Bus", "Ferry"],
    )

    assert first.id == second.id  # same coding record, edited in place
    assert second.transport_modes_json == ["Bus", "Ferry"]
    domain_codes = crud.list_information_domain_codes(db_session, second.id)
    assert len(domain_codes) == len(INFORMATION_COVERAGE_ITEMS)  # no duplicates
    assert domain_codes["payment_how_to_pay"].value == "Present"
    assert len(crud.list_older_adult_need_codes(db_session, second.id)) == 4
    assert len(crud.list_video_codings(db_session, study.id)) == 1


def test_reviewers_coding_the_same_video_stay_independent(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    other = crud.create_reviewer(db_session, name="Second", initials="SE")

    a = _save(db_session, study, included, reviewer.id,
              full_information_coverage(payment_how_to_pay=("Present", "A's note")),
              full_older_adult_needs(older_payment=("Yes", "A mentions fares")))
    b = _save(db_session, study, included, other.id,
              full_information_coverage(payment_how_to_pay=("Absent", None)),
              full_older_adult_needs(older_payment=("Yes", "B mentions concessions")))

    assert a.id != b.id
    a_info = crud.list_information_domain_codes(db_session, a.id)
    b_info = crud.list_information_domain_codes(db_session, b.id)
    assert (a_info["payment_how_to_pay"].value, a_info["payment_how_to_pay"].notes) == ("Present", "A's note")
    assert b_info["payment_how_to_pay"].value == "Absent"
    assert crud.list_older_adult_need_codes(db_session, a.id)["older_payment"].notes == "A mentions fares"
    assert crud.list_older_adult_need_codes(db_session, b.id)["older_payment"].notes == "B mentions concessions"


def test_unknown_or_legacy_item_keys_are_rejected(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    with pytest.raises(ValueError, match="information coverage"):
        _save(db_session, study, included, reviewer.id, {"Fares/payment": ("Present", None)}, {})
    with pytest.raises(ValueError, match="older-adult needs"):
        _save(db_session, study, included, reviewer.id, {}, {"Seating/rest": ("Addressed", None)})


def test_invalid_values_are_rejected(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    with pytest.raises(ValueError):
        _save(db_session, study, included, reviewer.id,
              {"payment_how_to_pay": ("Addressed", None)}, {})
    with pytest.raises(ValueError):
        _save(db_session, study, included, reviewer.id, {}, {"older_payment": ("Unclear", None)})


def test_accuracy_notes_save_edit_and_clear(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    note = "The video states that seniors travel free after 9 am, but this may be outdated."
    coding = _save(db_session, study, included, reviewer.id, {}, {}, accuracy_notes=note)
    assert crud.get_video_coding(db_session, included.id, reviewer.id).accuracy_notes == note

    _save(db_session, study, included, reviewer.id, {}, {}, accuracy_notes="Revised concern")
    assert crud.get_video_coding(db_session, included.id, reviewer.id).accuracy_notes == "Revised concern"

    _save(db_session, study, included, reviewer.id, {}, {}, accuracy_notes=None)
    reloaded = crud.get_video_coding(db_session, included.id, reviewer.id)
    assert reloaded.id == coding.id
    assert reloaded.accuracy_notes is None


def test_accuracy_notes_are_reviewer_specific(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    other = crud.create_reviewer(db_session, name="Second", initials="SE")
    _save(db_session, study, included, reviewer.id, {}, {}, accuracy_notes="A's concern")
    _save(db_session, study, included, other.id, {}, {}, accuracy_notes=None)
    assert crud.get_video_coding(db_session, included.id, reviewer.id).accuracy_notes == "A's concern"
    assert crud.get_video_coding(db_session, included.id, other.id).accuracy_notes is None


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def test_fully_coded_video_can_be_marked_complete_without_presentation(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    coding = _save(db_session, study, included, reviewer.id, full_information_coverage(),
                   full_older_adult_needs(), mark_complete=True)
    assert coding.status == coding_service.STATUS_COMPLETE


def test_completion_needs_no_accuracy_notes_or_accuracy_assessment(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    coding = _save(db_session, study, included, reviewer.id, full_information_coverage(),
                   full_older_adult_needs(), mark_complete=True, accuracy_notes=None)
    assert coding.status == coding_service.STATUS_COMPLETE
    assert db_session.query(AccuracyClaim).count() == 0
    assert db_session.query(AccuracyReviewStatus).count() == 0


def test_mark_complete_needs_every_older_adult_need_answered(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    needs = full_older_adult_needs()
    needs["older_assistance_seeking"] = (None, None)
    coding = _save(db_session, study, included, reviewer.id, full_information_coverage(), needs,
                   mark_complete=True)
    # The work is still saved, just not as complete.
    assert coding.status == coding_service.STATUS_IN_PROGRESS
    assert crud.list_older_adult_need_codes(db_session, coding.id)["older_payment"].value == "No"


def test_mark_complete_needs_every_information_coverage_item_coded(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    info = full_information_coverage()
    del info["misc_delay"]
    coding = _save(db_session, study, included, reviewer.id, info, full_older_adult_needs(),
                   mark_complete=True)
    assert coding.status == coding_service.STATUS_IN_PROGRESS


def test_missing_for_completion_names_the_uncoded_items():
    info = {k: v for k, (v, _) in full_information_coverage().items()}
    info["misc_delay"] = None
    needs = {k: v for k, (v, _) in full_older_adult_needs().items()}
    del needs["older_payment"]
    assert coding_service.missing_for_completion(info, needs) == [
        "Information coverage: What to do if there is a delay",
        "Older-adult needs: Payment",
    ]


def test_compute_progress_counts_by_status(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    _save(db_session, study, included, reviewer.id, full_information_coverage(),
          full_older_adult_needs(), mark_complete=True)
    codings = crud.list_video_codings(db_session, study.id)
    progress = coding_service.compute_progress([included.id], codings)
    assert progress.total == 1
    assert progress.complete == 1
    assert progress.not_started == 0


# ---------------------------------------------------------------------------
# Presentation removal / legacy data
# ---------------------------------------------------------------------------


def test_saving_never_creates_presentation_rows(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    _save(db_session, study, included, reviewer.id, full_information_coverage(),
          full_older_adult_needs(), mark_complete=True)
    assert db_session.query(PresentationCode).count() == 0
    assert not hasattr(crud, "upsert_presentation_code")


def test_legacy_rows_are_preserved_and_left_untouched_by_new_coding(db_session, study_with_included_video):
    study, reviewer, included, _ = study_with_included_video
    coding = _save(db_session, study, included, reviewer.id, {}, {})
    db_session.add_all([
        InformationDomainCode(video_coding_id=coding.id, domain_name="Fares/payment",
                              value="Present", notes="old"),
        OlderAdultNeedCode(video_coding_id=coding.id, need_name="Seating/rest", value="Addressed"),
        PresentationCode(video_coding_id=coding.id, item_name="Captions available", value="Yes"),
    ])
    db_session.commit()

    _save(db_session, study, included, reviewer.id,
          full_information_coverage(payment_how_to_pay=("Absent", None)),
          full_older_adult_needs(), mark_complete=True)

    info = crud.list_information_domain_codes(db_session, coding.id)
    assert (info["Fares/payment"].value, info["Fares/payment"].notes) == ("Present", "old")
    assert info["payment_how_to_pay"].value == "Absent"  # not auto-mapped from "Fares/payment"
    assert crud.list_older_adult_need_codes(db_session, coding.id)["Seating/rest"].value == "Addressed"
    assert db_session.query(PresentationCode).count() == 1


# ---------------------------------------------------------------------------
# Page (AppTest)
# ---------------------------------------------------------------------------

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "07_video_coding.py")


@pytest.fixture()
def coding_page(monkeypatch, tmp_path):
    """The video coding page, backed by a temp SQLite database holding one
    study, two reviewers and one included video."""
    import db.database as database
    from components.caching import invalidate_reviewer_options, invalidate_study_options

    saved = (database._engine, database._backend, database._SessionLocal, database._schema_ready)
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_backend", None)
    monkeypatch.setattr(database, "_SessionLocal", None)
    monkeypatch.setattr(database, "_schema_ready", False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "coding.db"))
    # The sidebar's study/reviewer lists are cached across runs; don't let a
    # previous test's database leak into this one.
    invalidate_study_options()
    invalidate_reviewer_options()

    database.init_db()
    session = database.get_session()
    study = crud.create_study(session, name="Coding page study")
    first = crud.create_reviewer(session, name="First", initials="FR")
    second = crud.create_reviewer(session, name="Second", initials="SR")
    video = crud.create_video(session, study_id=study.id, video_id="vid1", title="Catching the bus")
    session.commit()
    crud.upsert_screening_decision(
        session, study_id=study.id, video_pk=video.id, reviewer_id=first.id,
        decision="Include", exclusion_reason=None, notes=None,
    )
    ids = {"study": study.id, "first": first.id, "second": second.id, "video": video.id}
    session.close()

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PAGE, default_timeout=60)
    yield at, database.get_session, ids

    invalidate_study_options()
    invalidate_reviewer_options()
    (database._engine, database._backend, database._SessionLocal, database._schema_ready) = saved


def _click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [str(e) for e in at.exception]


def _control(at, label):
    return next(c for c in at.segmented_control if c.label == label)


def test_page_shows_three_tabs_and_no_presentation(coding_page):
    at, _, _ = coding_page
    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    assert [t.label for t in at.tabs] == ["Characteristics", "Information coverage", "Older-adult needs"]
    assert not any("presentation" in t.label.lower() for t in at.tabs)


def test_characteristics_tab_keeps_its_fields_and_adds_accuracy_notes_last(coding_page):
    at, _, _ = coding_page
    at.run()
    char_tab = at.tabs[0]
    assert [m.label for m in char_tab.multiselect] == ["Transport mode(s)", "Jurisdiction(s)"]
    assert [s.label for s in char_tab.selectbox] == ["Uploader type", "Audience"]
    assert [r.label for r in char_tab.radio] == ["Specifically aimed at older adults?"]
    assert [t.label for t in char_tab.text_area] == ["Notes", ACCURACY_NOTES_LABEL]
    assert char_tab.text_area[1].value == ""  # optional, starts empty
    assert any(c.value == ACCURACY_NOTES_HELP for c in char_tab.caption)


def test_accuracy_assessment_page_is_gone_from_navigation():
    root = Path(PAGE).parent.parent
    assert "accuracy" not in (root / "app.py").read_text().lower()
    assert not list((root / "pages").glob("*accuracy*"))


def test_page_renders_all_categories_and_items(coding_page):
    at, _, _ = coding_page
    at.run()
    group_labels = [e.label for e in at.expander if "coded" in e.label]
    assert [label.split(" · ")[0] for label in group_labels] == INFORMATION_COVERAGE_CATEGORIES
    control_labels = [c.label for c in at.segmented_control]
    for item in INFORMATION_COVERAGE_ITEMS:
        assert item.label in control_labels
    # 30 coverage items + 4 older-adult needs, all initially uncoded.
    assert len(at.segmented_control) == len(INFORMATION_COVERAGE_ITEMS) + 4
    assert all(c.value is None for c in at.segmented_control)


def test_page_shows_four_needs_with_note_only_on_yes(coding_page):
    at, _, _ = coding_page
    at.run()
    need_controls = [c for c in at.segmented_control if c.options == ["Yes", "No"]]
    assert [c.label for c in need_controls] == REQUESTED_NEEDS
    assert not any(t.label == "If Yes, what did they mention?" for t in at.text_area)

    _control(at, "Payment").set_value("Yes").run()
    assert [t.label for t in at.text_area if t.label == "If Yes, what did they mention?"] == [
        "If Yes, what did they mention?"
    ]
    _control(at, "Payment").set_value("No").run()
    assert not any(t.label == "If Yes, what did they mention?" for t in at.text_area)


def test_page_saves_and_reloads_coding(coding_page):
    at, get_session, ids = coding_page
    at.run()
    _control(at, "How to pay").set_value("Present")
    next(t for t in at.text_area if t.label == ACCURACY_NOTES_LABEL).input("Fare may be outdated.")
    _control(at, "Payment").set_value("Yes").run()
    next(t for t in at.text_area if t.label == "If Yes, what did they mention?").input("Opal fares")
    _click(at, "Save")

    session = get_session()
    coding = crud.get_video_coding(session, ids["video"], ids["first"])
    assert coding.status == coding_service.STATUS_IN_PROGRESS
    assert coding.accuracy_notes == "Fare may be outdated."
    assert crud.list_information_domain_codes(session, coding.id)["payment_how_to_pay"].value == "Present"
    need = crud.list_older_adult_need_codes(session, coding.id)["older_payment"]
    assert (need.value, need.notes) == ("Yes", "Opal fares")
    assert session.query(PresentationCode).count() == 0
    session.close()

    # A fresh session (no widget state) reloads the saved values.
    from streamlit.testing.v1 import AppTest

    fresh = AppTest.from_file(PAGE, default_timeout=60).run()
    assert _control(fresh, "How to pay").value == "Present"
    assert _control(fresh, "Payment").value == "Yes"
    assert any(t.value == "Opal fares" for t in fresh.text_area)
    assert next(t for t in fresh.text_area if t.label == ACCURACY_NOTES_LABEL).value == "Fare may be outdated."


def test_page_mark_complete_requires_full_coding(coding_page):
    at, get_session, ids = coding_page
    at.run()
    next(c for c in at.checkbox if c.label == "Mark this video's coding as complete").check()
    _click(at, "Save")

    assert any("not complete" in w.value for w in at.warning)
    session = get_session()
    assert crud.get_video_coding(session, ids["video"], ids["first"]).status == coding_service.STATUS_IN_PROGRESS
    session.close()

    for control in at.segmented_control:
        control.set_value(control.options[0])
    at.run()
    _click(at, "Save")

    session = get_session()
    assert crud.get_video_coding(session, ids["video"], ids["first"]).status == coding_service.STATUS_COMPLETE
    session.close()


def test_page_reviewers_code_independently(coding_page):
    at, get_session, ids = coding_page
    at.run()
    _control(at, "How to pay").set_value("Present").run()
    _click(at, "Save")

    from streamlit.testing.v1 import AppTest

    second = AppTest.from_file(PAGE, default_timeout=60)
    second.session_state["current_reviewer_id"] = ids["second"]
    second.run()
    assert _control(second, "How to pay").value is None  # first reviewer's coding isn't loaded
    _control(second, "How to pay").set_value("Absent").run()
    _click(second, "Save")

    session = get_session()
    first_coding = crud.get_video_coding(session, ids["video"], ids["first"])
    second_coding = crud.get_video_coding(session, ids["video"], ids["second"])
    assert crud.list_information_domain_codes(session, first_coding.id)["payment_how_to_pay"].value == "Present"
    assert crud.list_information_domain_codes(session, second_coding.id)["payment_how_to_pay"].value == "Absent"
    session.close()


def test_page_handles_legacy_coding_records(coding_page):
    at, get_session, ids = coding_page
    session = get_session()
    coding = crud.upsert_video_coding(
        session, study_id=ids["study"], video_pk=ids["video"], reviewer_id=ids["first"],
        transport_modes=["Bus"], jurisdictions=["NSW"], uploader_type=None, intended_audience=None,
        older_adult_targeted=None, notes=None, accuracy_notes=None,
            status=coding_service.STATUS_COMPLETE,
    )
    session.add_all([
        InformationDomainCode(video_coding_id=coding.id, domain_name="Fares/payment", value="Present"),
        OlderAdultNeedCode(video_coding_id=coding.id, need_name="Seating/rest", value="Addressed"),
        PresentationCode(video_coding_id=coding.id, item_name="Captions available", value="Yes"),
    ])
    session.commit()
    session.close()

    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    assert any("previous coding framework" in i.value for i in at.info)
    assert all(c.value is None for c in at.segmented_control)  # legacy values aren't auto-mapped
    assert next(c for c in at.checkbox if c.label == "Mark this video's coding as complete").value


@pytest.mark.parametrize("page", ["01_home.py", "10_dashboard.py", "09_reliability.py", "11_export.py"])
def test_dependent_pages_render_with_revised_and_legacy_coding(coding_page, page):
    """Home/Dashboard/Reliability/Export read the coding framework; they must
    work with double-coded revised data alongside legacy presentation and
    accuracy-assessment rows."""
    _, get_session, ids = coding_page
    session = get_session()
    study = crud.get_study(session, ids["study"])
    video = crud.get_video(session, ids["video"])
    first = _save(session, study, video, ids["first"],
                  full_information_coverage(payment_how_to_pay=("Present", None)),
                  full_older_adult_needs(older_payment=("Yes", "Fares")), mark_complete=True)
    _save(session, study, video, ids["second"], full_information_coverage(),
          full_older_adult_needs(), mark_complete=True)
    session.add_all([
        PresentationCode(video_coding_id=first.id, item_name="Captions available", value="Yes"),
        AccuracyClaim(study_id=ids["study"], video_id=ids["video"], reviewer_id=ids["first"],
                      claim_text="Seniors travel free", assessment="Outdated"),
        AccuracyReviewStatus(study_id=ids["study"], video_id=ids["video"], reviewer_id=ids["first"],
                             is_complete=True),
    ])
    session.commit()
    session.close()

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(PAGE).parent / page), default_timeout=60).run()
    assert not at.exception, [str(e) for e in at.exception]
    assert not any("presentation" in t.label.lower() for t in at.tabs)
    assert not any("accuracy" in m.label.lower() for m in at.metric)
    if page == "10_dashboard.py":
        assert next(m for m in at.metric if m.label == "Coded (started)").value == "1"
        assert next(m for m in at.metric if m.label == "Coding complete").value == "1"
    if page == "01_home.py":
        assert next(m for m in at.metric if m.label == "Coding complete").value == "1"
