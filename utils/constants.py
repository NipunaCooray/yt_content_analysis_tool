"""
Central configuration for all controlled vocabularies used across the app.

Keep coding-domain lists here (not scattered in page/UI code) so the research
team can refine the coding framework after pilot testing without touching
application logic. See handover doc section 30.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------

DEFAULT_COUNTRY = "Australia"
DEFAULT_LANGUAGE = "English"

STUDY_SEARCH_STATUSES = [
    "Draft",
    "Pilot testing",
    "Ready for full search",
    "Full search completed",
]

# ---------------------------------------------------------------------------
# Search queries / strategy
# ---------------------------------------------------------------------------

QUERY_CATEGORIES = [
    "General public transport",
    "Bus",
    "Train",
    "Metro",
    "Tram/light rail",
    "Ferry",
    "Community transport",
    "On-demand transport",
    "Accessible transport",
    "Older adults",
    "State-specific",
    "Other",
]

STATES_TERRITORIES = [
    "Australia-wide",
    "NSW",
    "VIC",
    "QLD",
    "SA",
    "WA",
    "TAS",
    "ACT",
    "NT",
]

SEARCH_ORDER_OPTIONS = [
    "relevance",
    "date",
    "rating",
    "viewCount",
    "title",
]

PILOT_RESULT_COUNT_OPTIONS = [5, 10, 20]

# Publication-date filter for search.list (search-run parameter, not a
# coding vocabulary, but kept here with the other search-strategy constants).
PUBLICATION_FILTER_ALL_TIME = "all_time"
PUBLICATION_FILTER_AFTER = "after"
PUBLICATION_FILTER_BEFORE = "before"
PUBLICATION_FILTER_BETWEEN = "between"

PUBLICATION_PERIOD_LABELS = {
    PUBLICATION_FILTER_ALL_TIME: "All time",
    PUBLICATION_FILTER_AFTER: "After a date",
    PUBLICATION_FILTER_BEFORE: "Before a date",
    PUBLICATION_FILTER_BETWEEN: "Between two dates",
}
PUBLICATION_PERIOD_OPTIONS = list(PUBLICATION_PERIOD_LABELS.keys())

# ---------------------------------------------------------------------------
# Pilot relevance assessment
# ---------------------------------------------------------------------------

RELEVANCE_RATINGS = [
    "Not yet reviewed",
    "Relevant",
    "Potentially relevant",
    "Irrelevant",
]

IRRELEVANCE_REASONS = [
    "Not Australian",
    "Not instructional",
    "Wrong transport topic",
    "Travel/tourism content",
    "News/media",
    "Transport enthusiast content",
    "Promotional/advertising",
    "Not English",
    "Other",
]

# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

SCREENING_DECISIONS = ["Include", "Exclude", "Unsure"]

EXCLUSION_REASONS = [
    "Not Australian",
    "Not instructional",
    "Not transport related",
    "News/media",
    "Travel vlog",
    "Advertisement/promotional only",
    "Transport enthusiast content",
    "Not English",
    "Duplicate/re-upload",
    "Unavailable",
    "Other",
]

# ---------------------------------------------------------------------------
# Video coding - characteristics
# ---------------------------------------------------------------------------

TRANSPORT_MODES = [
    "Bus",
    "Train",
    "Metro",
    "Tram/light rail",
    "Ferry",
    "Regional coach",
    "Community transport",
    "On-demand transport",
    "Accessible taxi",
    "Taxi/rideshare",
    "Multimodal",
    "Other",
]

JURISDICTIONS = [
    "National",
    "NSW",
    "VIC",
    "QLD",
    "SA",
    "WA",
    "TAS",
    "ACT",
    "NT",
    "Multiple jurisdictions",
    "Unclear",
]

UPLOADER_TYPES = [
    "Government / transport authority",
    "Transport operator",
    "Community organisation",
    "Commercial organisation",
    "Media",
    "Individual creator",
    "Other",
    "Unclear",
]

AUDIENCE_TYPES = [
    "General public",
    "Older adults",
    "People with disability",
    "Tourists",
    "New users",
    "Other",
    "Unclear",
]

YES_NO_UNCLEAR = ["Yes", "No", "Unclear"]

# ---------------------------------------------------------------------------
# Information coverage coding (revised after researcher user testing)
# ---------------------------------------------------------------------------
#
# Each item has a stable `key` -- that is what's stored (in
# information_domain_codes.domain_name), so `label` wording can be refined
# later without breaking saved data. Category and label are derived from
# this list at read/export time, never stored.
#
# Legacy rows from the previous 15-domain framework (stored under their
# human-readable names, e.g. "Fares/payment") are left in place in the same
# table. They are never auto-mapped onto these keys -- the frameworks don't
# correspond one-to-one -- and are exported separately as legacy data.


@dataclass(frozen=True)
class CodingItem:
    key: str
    label: str
    category: str | None = None


INFORMATION_COVERAGE_CATEGORIES = [
    "General Public Transport Information",
    "Journey Planning",
    "Payment",
    "Stop / Station / Platform / Wharf Information",
    "Riding the Service",
    "During the Trip",
    "Transfers and Connections",
    "Miscellaneous",
]

_GENERAL, _JOURNEY, _PAYMENT, _STOP, _RIDING, _TRIP, _TRANSFERS, _MISC = INFORMATION_COVERAGE_CATEGORIES

INFORMATION_COVERAGE_ITEMS = [
    CodingItem("general_modes_available", "What types of modes are available", _GENERAL),
    CodingItem("general_benefits", "Benefits of taking public transport", _GENERAL),
    CodingItem("general_better_than_driving", "When/why public transport is better than driving", _GENERAL),
    CodingItem("journey_destination_selection", "Destination selection", _JOURNEY),
    CodingItem("journey_route_planner", "Using app/website to plan route", _JOURNEY),
    CodingItem("journey_identify_routes_stops", "How to identify routes, stops, transfer points", _JOURNEY),
    CodingItem("journey_reading_timetables", "Reading timetables/schedules", _JOURNEY),
    CodingItem("journey_estimate_travel_times", "Estimate travel times", _JOURNEY),
    CodingItem("payment_how_to_pay", "How to pay", _PAYMENT),
    CodingItem("payment_when_to_pay", "When to pay", _PAYMENT),
    CodingItem("payment_what_to_use", "What to use to pay", _PAYMENT),
    CodingItem("payment_fares_concessions", "Fare cost and other concessions", _PAYMENT),
    CodingItem("stop_find_correct", "How to find correct stop / station / platform / wharf", _STOP),
    CodingItem("stop_exit_correct", "How to exit correct stop / station / platform / wharf", _STOP),
    CodingItem("riding_accessibility_features", "Accessibility features", _RIDING),
    CodingItem(
        "riding_specific_rules",
        "Any specific rules, e.g. requesting service, priority seating, boarding requirements",
        _RIDING,
    ),
    CodingItem("riding_etiquette", "Etiquette when taking service", _RIDING),
    CodingItem("trip_announcements", "Announcements — visual and/or audio", _TRIP),
    CodingItem("trip_safety", "Safety considerations", _TRIP),
    CodingItem("trip_request_stop", "How to request a stop — if applicable", _TRIP),
    CodingItem("trip_preparing_to_get_off", "Preparing to get off", _TRIP),
    CodingItem("transfers_navigate_multimodal", "Steps to navigate multimodal connections / transfers", _TRANSFERS),
    CodingItem("transfers_find_connections", "How to find connections", _TRANSFERS),
    CodingItem("transfers_reading_times", "Reading transfer times", _TRANSFERS),
    CodingItem("transfers_missed_connection", "What to do if a connection / transfer is missed", _TRANSFERS),
    CodingItem("misc_emergency_contacts", "Emergency contact points", _MISC),
    CodingItem("misc_contact_staff", "How to contact staff", _MISC),
    CodingItem("misc_staff_help", "What staff can help with", _MISC),
    CodingItem("misc_wrong_service", "What to do if the wrong service is caught", _MISC),
    CodingItem("misc_delay", "What to do if there is a delay", _MISC),
]

INFORMATION_COVERAGE_VALUES = ["Present", "Absent", "Not applicable", "Unclear"]

# ---------------------------------------------------------------------------
# Older-adult needs coding (revised after researcher user testing)
# ---------------------------------------------------------------------------
#
# Same stable-key storage as information coverage above (keys are stored in
# older_adult_need_codes.need_name; legacy 12-need rows are left in place).
# Each item has its own optional "If Yes, what did they mention?" note.

OLDER_ADULT_NEEDS_PROMPT = "Does the video mention information on the following?"
OLDER_ADULT_NEEDS_NOTE_PROMPT = "If Yes, what did they mention?"

OLDER_ADULT_NEED_ITEMS = [
    CodingItem("older_journey_planning", "Journey Planning"),
    CodingItem("older_payment", "Payment"),
    CodingItem("older_accessibility_safety", "Accessibility and safety"),
    CodingItem("older_assistance_seeking", "Assistance seeking"),
]

OLDER_ADULT_NEED_VALUES = ["Yes", "No"]

# Presentation / communication coding was removed after researcher user
# testing. Existing presentation_codes rows are preserved (and exported as
# legacy data) but no new ones are collected.

# ---------------------------------------------------------------------------
# Accuracy assessment (handover doc section 18)
# ---------------------------------------------------------------------------

CLAIM_CATEGORIES = [
    "Journey planning",
    "Routes",
    "Timetables",
    "Payment",
    "Fares",
    "Concessions",
    "Booking",
    "Eligibility",
    "Accessibility",
    "Assistance",
    "Transfers",
    "Disruptions",
    "Other",
]

ACCURACY_VALUES = [
    "Correct",
    "Correct but incomplete",
    "Outdated",
    "Incorrect",
    "Unverifiable",
]

# ---------------------------------------------------------------------------
# Coding / review status
# ---------------------------------------------------------------------------

CODING_STATUSES = ["Not started", "In progress", "Complete"]

# ---------------------------------------------------------------------------
# Search-run durability (PostgreSQL migration): a PilotSearchRun/FullSearchRun
# row is created as soon as the run starts and updated as it progresses, so
# the audit trail survives a crash or Streamlit Cloud restart mid-run.
# ---------------------------------------------------------------------------

RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_PARTIAL = "partial"
