# YouTube Transport Research Tool

## Coding Agent Handover / Product Specification

## 1. Project overview

Build a research workflow web application for a study analysing YouTube videos about **how to use public transport and alternative transport services in Australia**.

The research asks:

> What information is provided in YouTube videos showing people how to use public transport and alternative transport services in Australia, is that information correct/current, and does it reflect the type of information older adults need to use these services?

This is **not** a general-purpose YouTube analytics platform.

It is a **research data collection, screening, coding, accuracy-assessment, and export tool**.

The initial version should support a reproducible manual content-analysis workflow. AI/LLM-based coding can be added later after a manually coded dataset exists.

---

# 2. Research objectives

The tool should support assessment of three primary outcomes.

## 2.1 Information coverage

Determine what practical information is provided in each video, including:

- Journey planning
- Routes/destinations
- Timetables/frequency
- Fares/payment
- Concessions
- Booking/eligibility
- Finding the stop/station/pickup point
- Boarding
- Transfers/connections
- Getting off
- Accessibility
- Assistance
- Service disruptions
- Emergency/help information

## 2.2 Accuracy and currentness

Determine whether factual instructions provided in videos are:

- Correct
- Correct but incomplete
- Outdated
- Incorrect
- Unverifiable

Accuracy should be assessed against relevant official Australian transport authority or service-provider information.

## 2.3 Relevance to older adults

Determine whether videos address practical information needs likely to be important to older adults, including:

- Physical accessibility
- Walking requirements
- Seating/rest
- Toilets
- Costs/concessions
- Safety
- Staff/driver assistance
- Mobility aids
- Digital requirements
- Non-digital alternatives
- Service disruptions and contingency planning
- Clear step-by-step instructions

The tool should also capture how information is presented, such as captions, readability, audio clarity, pace, visual demonstrations, jargon, and help/contact information.

---

# 3. Core design principle

The YouTube API is primarily used to:

1. Systematically retrieve videos
2. Preserve a reproducible search strategy
3. Store search rankings and metadata
4. Support deduplication

The actual research analysis is primarily **manual video content analysis**.

Researchers should watch the video itself rather than relying only on transcripts, because important transport instructions may be visual.

Examples include:

- Where to tap a travel card
- Which button to press
- Where to wait
- How to board
- Where accessibility ramps/lifts are located
- How signage appears
- How to navigate transfers

---

# 4. Recommended technical stack

## MVP

- Python
- Streamlit
- SQLite
- SQLAlchemy
- pandas
- google-api-python-client
- Plotly or native Streamlit charts
- python-dotenv or equivalent for configuration

## Future upgrade path

If the project later requires several researchers working simultaneously:

- PostgreSQL
- Authentication
- Role-based access
- Deployment via Docker/cloud hosting

Do not introduce these complexities into the initial MVP unless required.

---

# 5. High-level workflow

The intended research workflow is:

```text
Create study
    ↓
Define search strategy
    ↓
Run pilot search
    ↓
Evaluate search performance
    ↓
Refine queries
    ↓
Approve search strategy
    ↓
Run full search
    ↓
Store raw search results
    ↓
Deduplicate videos
    ↓
Screen videos
    ↓
Code included videos
    ↓
Assess factual accuracy
    ↓
Review study progress
    ↓
Export analysis-ready data
```

---

# 6. Application navigation

Use a persistent left sidebar.

Recommended pages:

1. Home
2. Study setup
3. Search strategy
4. Pilot search
5. Full search results
6. Screening
7. Video coding
8. Accuracy assessment
9. Dashboard
10. Export
11. Settings

The UI should be clean, minimal, research-oriented, and optimised for repeated coding work.

---

# 7. Study setup

## Purpose

Create and manage the research project.

## Fields

- Study name
- Description
- Country
- Language
- Search date
- Default number of results per query
- Search order
- Notes

Default country:

```text
Australia
```

Default language:

```text
English
```

## Study search status

Each study should have one of the following states:

- Draft
- Pilot testing
- Ready for full search
- Full search completed

## Acceptance criteria

The researcher can:

- Create a study
- Edit study details
- Save the study
- Reopen it later
- See its search status
- Move between workflow stages

---

# 8. Search strategy

## Purpose

Allow the researcher to define a reproducible set of search queries.

Example queries:

```text
how to use public transport Australia
how to catch a bus Australia
how to use trains Australia
how to use ferry Australia
how to use light rail Australia
community transport Australia how to use
how to use on demand transport Australia
accessible public transport Australia
public transport seniors Australia
how to catch a bus NSW
how to use public transport Victoria
```

## Query fields

Each search query should store:

- Query text
- Category
- Optional state/territory
- Notes
- Active/inactive
- Created timestamp
- Updated timestamp

## Example categories

- General public transport
- Bus
- Train
- Metro
- Tram/light rail
- Ferry
- Community transport
- On-demand transport
- Accessible transport
- Older adults
- State-specific
- Other

## States and territories

Support:

- Australia-wide
- NSW
- VIC
- QLD
- SA
- WA
- TAS
- ACT
- NT

## Features

Researchers should be able to:

- Add a query
- Edit a query
- Delete a query
- Duplicate a query
- Disable a query without deleting it
- Bulk import queries from CSV if convenient
- Filter queries by category/state

---

# 9. Pilot search / search validation

## Purpose

Researchers must be able to evaluate whether the initial search strategy is retrieving sufficiently relevant videos **without running the full search**.

This is a core research feature.

The intended workflow is:

```text
Draft queries
    ↓
Pilot small sample
    ↓
Review relevance
    ↓
Refine search terms
    ↓
Repeat pilot if needed
    ↓
Approve final strategy
    ↓
Run full search
```

## Pilot settings

Allow the researcher to select:

- One or more active queries
- Number of pilot results per query
- Search order
- Other parameters used by the full search

Suggested result-count options:

- 5
- 10
- 20

The pilot must use the same search logic as the full search.

## Pilot result assessment

For each returned video, allow classification as:

- Relevant
- Potentially relevant
- Irrelevant
- Not yet reviewed

## Irrelevance reasons

Optional reason:

- Not Australian
- Not instructional
- Wrong transport topic
- Travel/tourism content
- News/media
- Transport enthusiast content
- Promotional/advertising
- Not English
- Other

## Show for each pilot result

- Thumbnail
- Title
- Description
- Channel
- Published date
- Search query
- Search rank
- Video URL
- Embedded/open-video option

## Search performance summary

Automatically calculate per query:

- Results reviewed
- Relevant
- Potentially relevant
- Irrelevant
- Relevant percentage
- Relevant + potentially relevant percentage

Example:

| Query | Reviewed | Relevant | Potential | Irrelevant | Relevant % |
| --- | ---: | ---: | ---: | ---: | ---: |
| how to use public transport Australia | 10 | 8 | 1 | 1 | 80% |
| public transport seniors Australia | 10 | 3 | 2 | 5 | 30% |
| how to catch a bus Australia | 10 | 9 | 0 | 1 | 90% |

Do **not** automatically decide whether a query is acceptable.

The researcher makes the final judgement.

## Additional diagnostics

Where possible, show:

- Duplicate videos across pilot queries
- Common irrelevance reasons
- Transport modes represented
- States/territories represented
- Uploader types represented
- Query overlap

These diagnostics help identify searches that are:

- Too broad
- Too narrow
- Highly duplicative
- Missing transport modes
- Missing jurisdictions
- Retrieving irrelevant material

## Query refinement

From the pilot page, allow researchers to:

- Edit a query
- Disable a query
- Add a new query
- Duplicate and modify a query
- Re-run selected queries only

Do not overwrite prior pilot runs.

Preserve the pilot history as an audit trail.

Example:

```text
Version 1
public transport older people Australia
→ low relevance

Version 2
how to use public transport seniors Australia
→ improved relevance

Version 3
final query approved
```

## Search strategy approval

Provide a clear action:

```text
Approve search strategy
```

When approved:

- Save the active query set
- Save search parameters
- Save approval timestamp
- Update study status to `Ready for full search`

The tool may display a warning if the researcher changes approved queries later.

Changing the approved strategy should not be prohibited, but it should be logged.

## Important data rule

Pilot results must be separate from the main study dataset.

Pilot videos must **not automatically enter the full study sample**.

The full search should retrieve results again using the approved strategy.

---

# 10. YouTube API integration

Use the YouTube Data API v3.

## Search

Use:

```text
search.list
```

Primary purpose:

- Retrieve video IDs
- Preserve result rank
- Associate videos with query
- Associate results with search run

Typical parameters may include:

- type=video
- maxResults
- order
- regionCode=AU where appropriate
- relevanceLanguage=en where appropriate
- q=query

Do not assume `regionCode=AU` means the content itself is Australian. Geographic relevance is still determined during screening.

## Metadata

Use:

```text
videos.list
```

Retrieve where available:

- Video ID
- Title
- Description
- Channel ID
- Channel title
- Published date
- Duration
- Tags
- View count
- Like count
- Thumbnail URLs
- Caption availability if exposed
- Other relevant metadata

Batch metadata requests where possible to reduce API usage.

## API error handling

Handle:

- Invalid API key
- Quota exceeded
- Deleted/private videos
- Network errors
- Empty search results
- Partial metadata
- Missing statistics

Display useful error messages.

Do not crash the full workflow because one video is unavailable.

---

# 11. Search runs and reproducibility

Every pilot and full search should have a search-run record.

Store:

- Study ID
- Run ID
- Run type: pilot/full
- Timestamp
- Search parameters
- Queries used
- Results requested per query
- API settings
- Optional researcher notes

For each raw result store:

- Search run
- Query
- Video ID
- Search rank

This is important for reproducibility.

---

# 12. Full search results

## Purpose

Run the approved search strategy and preserve all results.

## Features

- Run all approved active queries
- Run selected queries if needed
- Save raw results
- Fetch metadata
- Display search results
- Deduplicate
- Show raw and unique counts

Recommended tabs:

- Raw results
- Unique videos
- Search log

## Raw search data

Preserve every result occurrence.

If one video appears under five search terms, save five raw-search-result records.

## Deduplicated master list

Create one master video record per unique YouTube `video_id` per study.

Do not discard information about which searches retrieved that video.

## Useful indicators

Show:

```text
Raw results: 437
Unique videos: 231
Duplicate occurrences: 206
```

---

# 13. Screening

## Purpose

Determine which unique videos are eligible for content analysis.

## Layout

Recommended:

Left/main panel:

- Embedded YouTube video
- Title
- Channel
- Publish date
- Description
- Duration
- Search queries that retrieved the video

Right panel:

- Screening form

## Screening decisions

- Include
- Exclude
- Unsure

## Exclusion reasons

- Not Australian
- Not instructional
- Not transport related
- News/media
- Travel vlog
- Advertisement/promotional only
- Transport enthusiast content
- Not English
- Duplicate/re-upload
- Unavailable
- Other

## Optional fields

- Screening notes
- Reviewer
- Timestamp

## Navigation

Provide:

- Previous
- Save
- Save and next
- Next
- Jump to video
- Resume last unscreened

## Filters

Allow:

- Not screened
- Included
- Excluded
- Unsure
- Reviewer
- Transport category if already assigned

## Acceptance criteria

Screening decisions:

- Persist immediately
- Can be edited
- Are timestamped
- Can be exported

---

# 14. Video coding

Only included videos should enter the normal coding workflow.

The coding screen should be divided into clear tabs or sections.

---

## 14.1 Video characteristics

Fields:

### Transport mode

Allow one or more where appropriate:

- Bus
- Train
- Metro
- Tram/light rail
- Ferry
- Regional coach
- Community transport
- On-demand transport
- Accessible taxi
- Taxi/rideshare
- Multimodal
- Other

### Jurisdiction

Allow:

- National
- NSW
- VIC
- QLD
- SA
- WA
- TAS
- ACT
- NT
- Multiple jurisdictions
- Unclear

### Uploader type

- Government / transport authority
- Transport operator
- Community organisation
- Commercial organisation
- Media
- Individual creator
- Other
- Unclear

### Audience

- General public
- Older adults
- People with disability
- Tourists
- New users
- Other
- Unclear

### Specifically aimed at older adults?

- Yes
- No
- Unclear

### Notes

Free text.

---

# 15. Information coverage coding

For each domain use:

- Present
- Absent
- Not applicable
- Unclear if needed

Domains:

- Journey planning
- Routes/destinations
- Timetables/frequency
- Fares/payment
- Concessions
- Booking
- Eligibility
- Finding stop/station/pickup point
- Boarding
- Transfers/connections
- Getting off
- Accessibility features
- Assistance available
- Disruptions / what to do if problems occur
- Emergency/help information

The schema should make it easy to add or modify domains later.

Avoid hard-coding the questionnaire in a way that makes amendments difficult.

---

# 16. Older-adult needs coding

Use:

- Addressed
- Not addressed
- Not applicable
- Unclear if needed

Domains:

- Physical accessibility / mobility
- Walking requirements
- Seating/rest
- Toilets
- Costs/concessions
- Personal safety
- Assistance from staff/driver
- Mobility aids
- Digital requirements / smartphone dependence
- Non-digital alternatives
- Service disruptions / contingency planning
- Clear step-by-step guidance

Again, design so domains can be extended later.

---

# 17. Presentation / communication coding

Capture whether information itself is presented in a usable way.

Suggested fields:

- Captions available
- Clear audio
- Readable on-screen text
- Visual demonstration provided
- Appropriate pace
- Jargon/acronyms explained
- Clear sequence
- Step-by-step structure
- Contact/help details provided

Possible response set:

- Yes
- No
- Not applicable
- Unclear

Allow optional notes.

---

# 18. Accuracy assessment

## Purpose

Assess factual/instructional claims at claim level rather than relying on one global video-quality score.

A video may contain multiple factual claims.

Example:

```text
Claim:
"You need an Opal card to catch the bus."

Category:
Payment

Official source:
[URL]

Assessment:
Correct
```

## Claim fields

- Video ID
- Reviewer
- Claim text
- Claim category
- Official source URL
- Assessment
- Notes
- Timestamp

## Claim categories

- Journey planning
- Routes
- Timetables
- Payment
- Fares
- Concessions
- Booking
- Eligibility
- Accessibility
- Assistance
- Transfers
- Disruptions
- Other

## Accuracy assessment values

- Correct
- Correct but incomplete
- Outdated
- Incorrect
- Unverifiable

Outdated should remain separate from incorrect.

A video may have been accurate when uploaded but no longer be correct for a present-day user.

## Interface

Researchers should be able to:

- Add claim
- Edit claim
- Delete claim
- Add source URL
- Open source URL in new tab
- Add notes
- Mark accuracy review complete for the video

---

# 19. Reviewer support

Although V1 does not need authentication, include a simple reviewer model.

Researchers should be able to create/select reviewer profiles.

Fields:

- Reviewer ID
- Name
- Initials
- Optional email

Store reviewer ID on:

- Pilot relevance assessments
- Screening decisions
- Video coding
- Accuracy claims

---

# 20. Double coding and reliability

This can be implemented after the core workflow but should be anticipated in the schema.

Potential workflow:

- Randomly assign 20–30% of videos to two reviewers
- Store separate coding records
- Compare responses
- Flag disagreements

Later dashboard features may include:

- Percentage agreement
- Cohen's kappa for suitable categorical variables
- List of disagreements
- Resolution status

Do not block the MVP on advanced reliability calculations.

---

# 21. Dashboard

## Study overview

Show top-line counters:

- Raw videos retrieved
- Unique videos
- Videos screened
- Videos included
- Videos excluded
- Videos coded
- Accuracy reviews completed
- Pilot searches completed

Example:

```text
437 raw results
231 unique videos
190 screened
96 included
73 coded
41 accuracy reviews completed
```

## Suggested charts

- Videos by transport mode
- Videos by jurisdiction
- Videos by uploader type
- Information domains covered
- Older-adult needs addressed
- Accuracy assessment distribution
- Screening exclusion reasons

## Pilot search dashboard

Include:

- Query relevance rate
- Duplicate rate
- Irrelevance reasons
- Number of pilot iterations
- Approved query count

The dashboard is primarily descriptive.

Do not build advanced inferential statistics into V1.

---

# 22. Export

## Required export datasets

Provide separate exports for:

1. Studies
2. Search queries
3. Pilot search runs
4. Pilot search results
5. Full search runs
6. Raw search results
7. Deduplicated videos
8. Screening decisions
9. Video characteristics
10. Information coverage coding
11. Older-adult-needs coding
12. Presentation coding
13. Accuracy claims
14. Reviewers

## Formats

Required:

- CSV

Nice to have:

- JSON
- Single Excel workbook with separate sheets

CSV should be the priority.

## Analysis compatibility

Exports should be straightforward to use in:

- R
- Python
- Stata/SPSS if required later

Use stable IDs and sensible column names.

---

# 23. Search/audit log

The tool should preserve enough information to reconstruct how the final search strategy was developed.

Log:

- Query added
- Query edited
- Query disabled
- Pilot run
- Pilot relevance assessment
- Search strategy approved
- Approved strategy edited
- Full search run
- Screening/coding edits if practical

A simple audit table is sufficient.

Do not overengineer event sourcing.

---

# 24. Suggested database schema

## studies

```text
id
name
description
country
language
default_results_per_query
search_order
search_status
created_at
updated_at
```

## reviewers

```text
id
name
initials
email_optional
created_at
```

## search_queries

```text
id
study_id
category
query_text
state_territory
notes
is_active
created_at
updated_at
```

## pilot_search_runs

```text
id
study_id
run_timestamp
results_per_query
search_order
parameters_json
notes
```

## pilot_search_results

```text
id
pilot_search_run_id
query_id
video_id
result_rank
title
description
channel_title
published_at
thumbnail_url
video_url
relevance_rating
irrelevance_reason
reviewer_id
reviewer_notes
reviewed_at
raw_json
```

## search_strategy_approvals

```text
id
study_id
approved_at
reviewer_id
query_snapshot_json
parameters_json
notes
```

## full_search_runs

```text
id
study_id
run_timestamp
approval_id
parameters_json
notes
```

## search_results_raw

```text
id
full_search_run_id
query_id
video_id
result_rank
title
channel_title
published_at
thumbnail_url
video_url
raw_json
```

## videos

```text
id
study_id
video_id
title
description
channel_id
channel_title
published_at
duration_seconds
view_count
like_count
tags_json
thumbnail_url
video_url
metadata_json
created_at
updated_at
```

Unique constraint:

```text
(study_id, video_id)
```

## screening_decisions

```text
id
study_id
video_id
reviewer_id
decision
exclusion_reason
notes
screened_at
updated_at
```

## video_coding

```text
id
study_id
video_id
reviewer_id
transport_modes_json
jurisdictions_json
uploader_type
intended_audience
older_adult_targeted
notes
status
coded_at
updated_at
```

## information_domain_codes

```text
id
video_coding_id
domain_name
value
notes
```

## older_adult_need_codes

```text
id
video_coding_id
need_name
value
notes
```

## presentation_codes

```text
id
video_coding_id
item_name
value
notes
```

## accuracy_claims

```text
id
study_id
video_id
reviewer_id
claim_text
category
official_source_url
assessment
notes
created_at
updated_at
```

## accuracy_review_status

```text
id
study_id
video_id
reviewer_id
is_complete
completed_at
```

## audit_log

```text
id
study_id
reviewer_id
action_type
entity_type
entity_id
details_json
created_at
```

---

# 25. Data model principle

Do not store everything in one giant table.

Use relational tables internally and produce flattened tables during export.

Important relationships:

```text
Study
 ├── Search queries
 │    ├── Pilot search results
 │    └── Full search results
 │
 ├── Videos
 │    ├── Screening decisions
 │    ├── Video coding
 │    │    ├── Information domains
 │    │    ├── Older-adult needs
 │    │    └── Presentation coding
 │    └── Accuracy claims
 │
 └── Reviewers
```

---

# 26. Video status model

Useful derived statuses:

- Not screened
- Screening unsure
- Excluded
- Included
- Coding not started
- Coding in progress
- Coding complete
- Accuracy review not started
- Accuracy review in progress
- Accuracy review complete

Avoid storing too many redundant status fields if they can be derived reliably.

---

# 27. UI guidance

The visual direction should resemble a clean research dashboard.

## Sidebar

Navigation items with simple icons.

## Main layout

Prefer:

- White/light background
- Clear card sections
- Compact forms
- Tables
- Progress counters
- Minimal visual clutter

## Screening/coding screens

Optimise for repeated use.

Keep the video visible while coding if possible.

Recommended desktop layout:

```text
┌───────────────────────────────┬──────────────────────────────┐
│                               │                              │
│       YouTube video           │      Coding form             │
│                               │                              │
│                               │                              │
├───────────────────────────────┴──────────────────────────────┤
│             Previous | Save | Save & Next                   │
└──────────────────────────────────────────────────────────────┘
```

For long coding forms, tabs are preferable.

---

# 28. Search results UI

Recommended tabs:

```text
Raw results | Unique videos | Search log
```

Raw-result columns:

- Query
- Rank
- Video title
- Channel
- Published
- Views
- Status

Unique-video view:

- Video
- Number of queries retrieving it
- Best rank
- Screening status
- Coding status

---

# 29. Pilot search UI

This is an important page.

Suggested structure:

## Header

- Study name
- Pilot run selector
- Number of results per query
- Run pilot button

## Query summary

Table:

| Query | Results | Reviewed | Relevant % | Duplicates | Status |
|---|---:|---:|---:|---:|---|

## Result review

For each result:

```text
[Thumbnail]

Title
Channel
Published
Query
Rank

( ) Relevant
( ) Potentially relevant
( ) Irrelevant

Irrelevance reason: [dropdown]

Notes: [...]
```

## Actions

- Save
- Save and next
- Edit query
- Re-run selected query
- Compare pilot runs
- Approve search strategy

---

# 30. Coding configuration

Where practical, place coding-domain definitions in configuration/constants rather than deeply embedding them in UI code.

For example:

```python
INFORMATION_DOMAINS = [
    "Journey planning",
    "Routes/destinations",
    "Timetables/frequency",
    ...
]
```

This will allow the research team to refine the coding framework after pilot testing without rewriting the application architecture.

---

# 31. Security and secrets

YouTube API credentials must not be committed to source control.

Use:

```text
.env
```

Example:

```text
YOUTUBE_API_KEY=...
```

Provide:

```text
.env.example
```

Do not include real credentials.

---

# 32. API quota awareness

YouTube search requests can consume substantial API quota.

Therefore:

- Do not repeatedly rerun identical searches unnecessarily
- Cache/store successful search runs
- Clearly distinguish pilot vs full search
- Warn before running large full searches
- Batch metadata lookups
- Show estimated number of API search calls where practical

Do not implement complex quota optimisation prematurely, but avoid obvious waste.

---

# 33. Data persistence

Data must persist between Streamlit sessions.

Do not rely on Streamlit session state as the primary data store.

Use database persistence for:

- Studies
- Queries
- Pilot ratings
- Search results
- Screening
- Coding
- Accuracy assessments

Use session state only for UI navigation/current selections.

---

# 34. Error recovery

The researcher should not lose work if:

- Browser refreshes
- Streamlit reruns
- Video becomes unavailable
- API request fails
- One metadata request returns incomplete data

Save forms explicitly and/or autosave when safe.

---

# 35. MVP development order

## Phase 1 — Foundation

Build:

- Project structure
- Database connection
- Models
- Study setup
- Reviewer selection
- Search strategy CRUD

Success condition:

A researcher can create a study and define queries.

## Phase 2 — Pilot search

Build:

- YouTube API integration
- Pilot search runs
- Pilot result storage
- Relevance rating
- Query-level performance summary
- Query refinement
- Search strategy approval

Success condition:

A researcher can test and refine search terms without running the full search.

## Phase 3 — Full search

Build:

- Full approved search
- Raw result storage
- Metadata enrichment
- Deduplication
- Search-results UI

Success condition:

A reproducible final search can be executed and preserved.

## Phase 4 — Screening

Build:

- Embedded video
- Eligibility form
- Exclusion reasons
- Navigation
- Filters
- Persistent decisions

Success condition:

Researchers can screen the deduplicated dataset efficiently.

## Phase 5 — Coding

Build:

- Video characteristics
- Information coverage
- Older-adult needs
- Presentation coding
- Save/resume

Success condition:

Included videos can be fully coded.

## Phase 6 — Accuracy

Build:

- Claim-level data entry
- Source URL
- Accuracy classification
- Multiple claims per video
- Accuracy-review status

Success condition:

Researchers can create a structured accuracy dataset.

## Phase 7 — Dashboard and export

Build:

- Study progress counters
- Basic charts
- CSV exports
- JSON export if easy
- Audit/search log

Success condition:

The study team can monitor progress and export analysis-ready data.

---

# 36. Testing requirements

Add basic automated tests for:

- Database creation
- CRUD operations
- Search result deduplication
- Query snapshot/approval behaviour
- Pilot calculations
- Export generation
- YouTube metadata normalisation

Mock YouTube API responses in tests.

Do not make unit tests depend on a live API key.

---

# 37. Example pilot relevance calculation

For a query:

```text
Reviewed = 10
Relevant = 7
Potentially relevant = 2
Irrelevant = 1
```

Calculate:

```text
strict_relevance_rate = 7 / 10 = 70%
broad_relevance_rate = (7 + 2) / 10 = 90%
```

Show both if useful.

Do not automatically decide whether 70% or 90% is "good enough".

That is a research decision.

---

# 38. Example information-coverage record

Video:

```text
How to catch a bus in Australia
```

Coding:

```text
Journey planning             Present
Routes/destinations          Present
Timetables/frequency         Present
Fares/payment                Present
Concessions                  Absent
Booking/eligibility          Not applicable
Finding stop/station         Present
Boarding                     Present
Transfers/connections        Absent
Getting off                  Present
Accessibility                Absent
Assistance                   Present
Disruptions                  Absent
Emergency/help               Absent
```

---

# 39. Example older-adult-needs record

```text
Physical accessibility              Not addressed
Walking requirements                Not addressed
Seating/rest                        Addressed
Toilets                             Not applicable
Cost/concessions                    Addressed
Safety                              Addressed
Staff/driver assistance             Addressed
Mobility aids                       Not addressed
Digital requirements                Addressed
Non-digital alternatives            Not addressed
Disruptions/contingency planning    Not addressed
Step-by-step guidance               Addressed
```

---

# 40. Example accuracy claims

```text
Claim:
"You must tap on when boarding."

Category:
Payment

Assessment:
Correct

Official source:
https://...

Notes:
Current official guidance confirms this.
```

Another:

```text
Claim:
"Seniors travel free after 9 am."

Category:
Concessions

Assessment:
Incorrect

Official source:
https://...
```

---

# 41. Export naming conventions

Use clear machine-readable filenames.

Examples:

```text
study_001_search_queries.csv
study_001_pilot_results.csv
study_001_raw_search_results.csv
study_001_unique_videos.csv
study_001_screening.csv
study_001_video_coding.csv
study_001_information_domains.csv
study_001_older_adult_needs.csv
study_001_accuracy_claims.csv
study_001_reviewers.csv
```

---

# 42. Non-functional requirements

The application should be:

- Reliable
- Reproducible
- Easy to maintain
- Easy for researchers to learn
- Fast enough for repeated screening/coding
- Modular
- Well documented

Prioritise working research functionality over visual polish.

---

# 43. Out of scope for MVP

Do not implement unless specifically requested later:

- Automated LLM coding
- Automated transcript extraction from arbitrary videos
- Automated fact-checking
- Comment analysis
- Sentiment analysis
- Network analysis
- Advanced machine learning
- Recommendation algorithms
- Complex user permissions
- Public-facing deployment
- Real-time multi-user collaboration
- Statistical modelling

---

# 44. Future enhancements

Potential later additions:

- AI-assisted pre-coding
- Human vs LLM agreement studies
- Transcript import where legally/technically available
- Automatic content summaries
- Automatic claim extraction for human verification
- Inter-rater reliability dashboard
- Adjudication workflow
- Random double-coding assignment
- Excel workbook export
- REDCap-style codebook import/export
- State-level coverage heatmaps
- Search-strategy version comparison
- Automatic methods/report generation

These should not delay the MVP.

---

# 45. Suggested repository structure

```text
youtube_transport_research_tool/
├── app.py
├── pages/
│   ├── 01_home.py
│   ├── 02_study_setup.py
│   ├── 03_search_strategy.py
│   ├── 04_pilot_search.py
│   ├── 05_search_results.py
│   ├── 06_screening.py
│   ├── 07_video_coding.py
│   ├── 08_accuracy_assessment.py
│   ├── 09_dashboard.py
│   └── 10_export.py
│
├── db/
│   ├── database.py
│   ├── models.py
│   ├── crud.py
│   └── migrations/
│
├── services/
│   ├── youtube_api.py
│   ├── pilot_service.py
│   ├── search_service.py
│   ├── deduplication.py
│   ├── screening_service.py
│   ├── coding_service.py
│   ├── accuracy_service.py
│   └── export_service.py
│
├── components/
│   ├── video_player.py
│   ├── navigation.py
│   ├── forms.py
│   └── metrics.py
│
├── utils/
│   ├── constants.py
│   ├── validators.py
│   ├── helpers.py
│   └── logging.py
│
├── tests/
│   ├── test_database.py
│   ├── test_deduplication.py
│   ├── test_pilot_search.py
│   └── test_exports.py
│
├── data/
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── LICENSE
```

---

# 46. Suggested first implementation milestone

The first genuinely useful milestone should support:

1. Create study
2. Add search queries
3. Configure YouTube API key
4. Run a pilot search
5. Review first 5–20 videos per query
6. Mark relevant/potentially relevant/irrelevant
7. View per-query relevance statistics
8. Edit/refine queries
9. Re-run the pilot
10. Approve the final search strategy

Do this before building the full screening/coding platform.

This gives the research team an immediately useful tool and validates the API/search workflow early.

---

# 47. Definition of MVP success

The MVP is successful if a researcher can complete this workflow without manually editing the database:

```text
Create study
→ Define queries
→ Pilot queries
→ Evaluate relevance
→ Refine queries
→ Approve search
→ Run full search
→ Deduplicate
→ Screen videos
→ Code included videos
→ Record factual claims
→ Assess accuracy
→ Export clean data
```

---

# 48. Coding-agent implementation instructions

Please build this application incrementally.

## Priorities

Prioritise, in this order:

1. Correct database/data model
2. Reliable persistence
3. Pilot-search workflow
4. Stable YouTube API integration
5. Reproducible full search
6. Efficient screening
7. Structured coding
8. Accuracy assessment
9. Clean exports
10. Dashboard/polish

## Development approach

- Do not overengineer.
- Keep components modular.
- Use type hints where practical.
- Separate UI, business logic, and database access.
- Avoid large monolithic Streamlit page files.
- Store configurable coding domains centrally.
- Add useful validation and error messages.
- Preserve the research audit trail.
- Never discard raw search data when deduplicating.
- Never mix pilot-search results into the final study dataset automatically.
- Do not implement AI features until the manual workflow works end-to-end.

## UX priority

The researcher may review and code dozens or hundreds of videos.

Optimise repeated tasks.

For example:

- sensible defaults
- keyboard-friendly controls if practical
- Save and Next
- Resume last unfinished video
- visible progress
- minimal unnecessary clicks

---

# 49. Initial task for the coding agent

Start by implementing **Phases 1 and 2 only**:

### Phase 1

- Repository scaffold
- SQLite database
- SQLAlchemy models
- Study CRUD
- Reviewer CRUD
- Search-query CRUD
- Streamlit navigation

### Phase 2

- YouTube API client
- Pilot-search execution
- Pilot-result persistence
- Relevance-review UI
- Query-level relevance calculations
- Pilot-run history
- Query refinement
- Search-strategy approval

Once these work end-to-end, proceed to the full-search and screening phases.

Do not build placeholder AI functionality.

---

# 50. Final product intent

The tool should ultimately function as a lightweight research platform for conducting a transparent and reproducible content analysis of Australian YouTube videos about public and alternative transport.

The most important methodological features are:

- Reproducible search strategy
- Pilot testing of search quality before the full search
- Preservation of raw search rankings
- Explicit deduplication
- Structured screening
- Structured content coding
- Older-adult-needs assessment
- Claim-level accuracy checking
- Researcher attribution
- Clean analysis-ready exports

The product should feel like a purpose-built research tool, not a generic social-media dashboard.
