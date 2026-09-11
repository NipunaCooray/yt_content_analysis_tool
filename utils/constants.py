"""
Central configuration for all controlled vocabularies used across the app.

Keep coding-domain lists here (not scattered in page/UI code) so the research
team can refine the coding framework after pilot testing without touching
application logic. See handover doc section 30.
"""

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
# Information coverage coding (handover doc section 15)
# ---------------------------------------------------------------------------

INFORMATION_DOMAINS = [
    "Journey planning",
    "Routes/destinations",
    "Timetables/frequency",
    "Fares/payment",
    "Concessions",
    "Booking",
    "Eligibility",
    "Finding stop/station/pickup point",
    "Boarding",
    "Transfers/connections",
    "Getting off",
    "Accessibility features",
    "Assistance available",
    "Disruptions / what to do if problems occur",
    "Emergency/help information",
]

COVERAGE_VALUES = ["Present", "Absent", "Not applicable", "Unclear if needed"]

# ---------------------------------------------------------------------------
# Older-adult needs coding (handover doc section 16)
# ---------------------------------------------------------------------------

OLDER_ADULT_NEEDS = [
    "Physical accessibility / mobility",
    "Walking requirements",
    "Seating/rest",
    "Toilets",
    "Costs/concessions",
    "Personal safety",
    "Assistance from staff/driver",
    "Mobility aids",
    "Digital requirements / smartphone dependence",
    "Non-digital alternatives",
    "Service disruptions / contingency planning",
    "Clear step-by-step guidance",
]

NEED_VALUES = ["Addressed", "Not addressed", "Not applicable", "Unclear if needed"]

# ---------------------------------------------------------------------------
# Presentation / communication coding (handover doc section 17)
# ---------------------------------------------------------------------------

PRESENTATION_ITEMS = [
    "Captions available",
    "Clear audio",
    "Readable on-screen text",
    "Visual demonstration provided",
    "Appropriate pace",
    "Jargon/acronyms explained",
    "Clear sequence",
    "Step-by-step structure",
    "Contact/help details provided",
]

PRESENTATION_VALUES = ["Yes", "No", "Not applicable", "Unclear"]

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
