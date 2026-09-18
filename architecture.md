# architecture.md

# Personal Admission Journey — Backend Architecture

## 1. Product definition

This project is a real recommendation and admission-journey backend for **international high-school students applying to bachelor's programs in the United States**.

Initial catalog coverage is **100 deliberately varied U.S. universities**. The first 100 are a coverage boundary, not demo-only logic and not a ranking. Adding university 101 must be a data operation, not a code change to the recommendation engine.

The product must eventually take a user through:

1. profile/questionnaire;
2. diagnostic;
3. program discovery when the user is unsure of a major;
4. university + program recommendations;
5. comparison;
6. personal admission roadmap;
7. one immediate next action and progress tracking.

The first user interface is the CLI. A Django web interface/API comes after the CLI journey works. Because Django is already the confirmed destination, **Django is used from the beginning for persistence and migrations**, while HTTP views are deliberately postponed. This avoids building an ORM layer twice.

---

## 2. Non-goals and hard boundaries

The system is **not**:

- an LLM that invents a university list from a prompt;
- an admission-probability calculator;
- a guarantee of admission;
- a ranking of U.S. universities;
- a static hand-authored result for one jury profile;
- a catalog with unsupported or silently guessed facts;
- a scraper that bypasses authentication, bot protections, or site restrictions.

The system must never convert "unknown" into "not required", "0", "free", "test optional", or any other factual claim.

---

## 3. Architectural principles

### 3.1 Facts first, inference second

The core flow is:

```text
authoritative sources
        ↓
source documents + provenance
        ↓
validated normalized facts
        ↓
eligibility / fit calculations
        ↓
recommendations
        ↓
explanations / roadmap wording
```

The LLM is never the factual authority.

### 3.2 Deterministic core, optional LLM assistance

The recommendation engine must work if the Alem/Gemma service is unavailable.

Gemma4 may help with:

- extracting structured facts from supplied official page text;
- translating free-form interests into a structured interest profile;
- rewriting already-computed recommendation reasons into natural language;
- rewriting an already-computed roadmap into natural language.

Gemma4 must not:

- choose universities from general model knowledge;
- invent requirements, costs, deadlines, scholarships, or programs;
- calculate or claim admission probabilities;
- override deterministic eligibility/scoring rules;
- silently fill missing values.

### 3.3 Provenance is part of the domain model

Every recommendation-critical factual record must be traceable to a source.

At minimum store:

- source URL;
- source/publisher type;
- retrieval timestamp;
- academic year/admission cycle when applicable;
- evidence snippet or structured-source locator;
- extraction method;
- content hash when a page was fetched;
- validation/status state.

### 3.4 Unknown is a first-class state

Use explicit statuses such as:

```text
verified
not_found
not_required
not_reported
conflicting
stale
unverified
extraction_failed
```

A nullable numeric field alone is not enough to describe factual state.

### 3.5 One data model, multiple transports

The CLI and later Django HTTP layer call the same application services.

```text
CLI ────────┐
            ▼
      application services
            ▲
Django HTTP ┘
            │
            ▼
      repositories / ORM
            │
            ▼
         database
```

No recommendation rules belong in CLI commands or Django views.

---

## 4. Technology choices

### Runtime

- Python 3.11+
- Django
- SQLite for local/CLI development
- PostgreSQL-compatible model design for later deployment

SQLite is not treated as a demo-only database. The persistence layer is Django ORM, so switching the deployed database is configuration/migration work rather than a recommendation-engine rewrite.

### CLI

- Typer for command structure
- Rich for readable terminal output
- packaged console command: `admission`

The CLI initializes Django and calls application services. Django management commands may exist for maintenance, but the main product CLI should be coherent and user-facing.

### Validation / typed contracts

- Pydantic v2 for:
  - CLI input/output DTOs;
  - imported structured records;
  - LLM extraction schemas;
  - deterministic dataset export validation.

### External HTTP / extraction

- `httpx` for normal HTTP fetching;
- `trafilatura` for extracting useful text/metadata from normal HTML;
- Playwright only as a fallback for pages whose needed content genuinely requires JavaScript;
- `RapidFuzz` for assisted institution-name reconciliation, never for silently accepting an ambiguous match.

### LLM

Alem OpenAI-compatible API:

```text
base URL: https://llm.alem.ai/v1
model:    gemma4
```

Use the OpenAI Python client behind an internal adapter.

Environment configuration:

```text
ALEM_API_KEY
ALEM_BASE_URL
ALEM_MODEL
```

Defaults may be supplied for base URL/model, but never for the API key.

Do not commit secrets.

### Testing

- pytest
- pytest-django

Network calls must not be required by normal unit tests. Use fixtures/mocks for repeatable tests. Live-source validation is a separate explicit operation.

---

## 5. Repository structure

Target structure:

```text
.
├── AGENTS.md
├── architecture.md
├── plan.md
├── README.md
├── pyproject.toml
├── manage.py
├── .env.example
├── .gitignore
│
├── data/
│   ├── seed/
│   │   └── university_coverage_100.json
│   ├── canonical/
│   │   ├── institutions.jsonl
│   │   ├── programs.jsonl
│   │   ├── admissions.jsonl
│   │   ├── english_requirements.jsonl
│   │   ├── costs.jsonl
│   │   ├── deadlines.jsonl
│   │   └── sources.jsonl
│   └── source_seeds/
│       └── official_urls.jsonl
│
├── src/
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── ...
│   │
│   └── admission/
│       ├── catalog/
│       │   ├── apps.py
│       │   ├── models.py
│       │   ├── repositories.py
│       │   ├── schemas.py
│       │   ├── readiness.py
│       │   ├── exporters.py
│       │   └── ingestion/
│       │       ├── ipeds.py
│       │       ├── scorecard.py
│       │       ├── fetcher.py
│       │       ├── extraction.py
│       │       ├── matching.py
│       │       └── validators.py
│       │
│       ├── profiles/
│       │   ├── models.py
│       │   ├── schemas.py
│       │   └── services.py
│       │
│       ├── recommendations/
│       │   ├── eligibility.py
│       │   ├── scoring.py
│       │   ├── diversification.py
│       │   ├── explanations.py
│       │   └── services.py
│       │
│       ├── journey/
│       │   ├── diagnostic.py
│       │   ├── roadmap.py
│       │   ├── next_action.py
│       │   └── services.py
│       │
│       ├── llm/
│       │   ├── client.py
│       │   ├── schemas.py
│       │   └── prompts.py
│       │
│       └── cli/
│           ├── app.py
│           ├── data.py
│           └── journey.py
│
└── tests/
    ├── catalog/
    ├── profiles/
    ├── recommendations/
    ├── journey/
    └── fixtures/
```

Do not create empty future modules merely to match this tree. Create a path when the task that owns it begins.

---

## 6. Canonical dataset vs runtime database

### 6.1 Runtime database

Django ORM is the runtime persistence layer.

SQLite database files are generated local artifacts and are not the reviewable source of truth for the shipped catalog.

### 6.2 Versioned canonical data

Normalized catalog facts are exported deterministically to `data/canonical/*.jsonl`.

This serves four purposes:

1. Git can review factual changes.
2. Review ZIPs contain inspectable data, not opaque SQLite bytes.
3. A clean environment can rebuild the database.
4. Dataset changes and code changes can be reviewed separately.

Requirements for deterministic export:

- stable sort order;
- stable key order where practical;
- no random IDs in exported records;
- no volatile "exported at" timestamp that rewrites every row;
- UTF-8;
- one logical record per JSONL line.

### 6.3 Raw source cache

Downloaded HTML and large extracted page bodies are cache artifacts, not canonical Git data.

Suggested local path:

```text
.var/source_cache/
```

It must be gitignored.

Canonical exported source metadata still includes URL, retrieval timestamp, hash, evidence, status, and extraction method.

---

## 7. Data model

Exact Django field names may evolve, but the following domain entities and boundaries are required.

### 7.1 Institution

Canonical institutional identity.

Core fields:

```text
id
ipeds_unitid                 unique canonical external identifier
name
state
city
country                      always US in current product scope
ownership                    public/private_nonprofit/etc.
official_website
operating_status
bachelors_granting
latitude                     optional
longitude                    optional
```

Aliases are separate records.

Never use the institution name as the primary identity.

### 7.2 InstitutionAlias

```text
institution
alias
alias_type
source
```

Used for matching historical/common/campus names.

### 7.3 ProgramOffering

Represents a bachelor's-level field/program supported by evidence.

```text
institution
cip_code
cip_title
credential_level
program_name                 optional when only normalized CIP evidence exists
status
academic_year
source
evidence
```

IPEDS/College Scorecard field-of-study/completions data can establish normalized CIP coverage. Exact current program names may later be enriched from official catalogs.

Do not claim a specific named degree from a CIP code alone.

### 7.4 AdmissionSnapshot

A time-scoped admissions/statistics record.

Possible fields:

```text
institution
admission_cycle_or_data_year
admission_rate
sat_ebrw_25
sat_ebrw_75
sat_math_25
sat_math_75
act_composite_25
act_composite_75
test_data_status
source
```

Absence of SAT/ACT data does not imply test-optional.

### 7.5 StandardizedTestPolicy

Separate policy record because "scores not reported" and "test optional" are different facts.

```text
institution
applicant_scope
cycle
sat_policy
act_policy
status
source
evidence
```

### 7.6 EnglishRequirement

One record per accepted test/policy item.

```text
institution
applicant_scope              international_undergraduate
cycle
test_type                    IELTS/TOEFL/DET/etc.
minimum_score
minimum_subscores            optional structured field
conditional_admission        explicit only when verified
waiver_policy                optional
status
source
evidence
```

Important:

```text
minimum_score = null + status=not_found
```

is different from:

```text
minimum_score = null + status=not_required
```

### 7.7 CostSnapshot

International-student financial comparison must prefer official international/nonresident cost information over generic domestic net-price metrics.

```text
institution
academic_year
scope                        international_undergraduate / nonresident_undergraduate
currency                     USD
tuition
mandatory_fees
housing_food
books_supplies
insurance
personal_transport
total_cost
value_kind                   published_total / calculated_from_published_components
status
source
evidence
```

If a total is calculated, retain the published component values and calculation rule.

Do not treat College Scorecard "average net price" as an international student's expected price.

### 7.8 Deadline

```text
institution
cycle
term
applicant_scope
deadline_type
deadline_date
rolling
status
source
evidence
```

Recommendation readiness does not require every deadline, but journey readiness does.

### 7.9 FinancialAidPolicy / Scholarship

Initially keep this conservative.

Facts may describe:

- international aid available: yes/no/unknown;
- merit scholarship available: yes/no/unknown;
- deterministic published scholarship rule if one truly exists;
- source/evidence.

Do not estimate an award that the source does not guarantee.

### 7.10 SourceDocument

```text
url
publisher
source_type
retrieved_at
http_status
content_hash
title
extraction_method
prompt_version              when LLM extraction was used
model_name                  when LLM extraction was used
```

### 7.11 DataIssue / ReviewItem

Used for:

```text
ambiguous institution match
conflicting sources
parse failure
unsupported page
stale requirement
missing readiness-critical fact
suspicious numeric value
```

Batch jobs continue past per-university errors and create review items instead of aborting the whole run.

---

## 8. Source policy

### 8.1 Source priority by fact type

Use the source that is authoritative for the fact, not one universal priority list.

**Institution identity / federal statistics / admissions distributions**
- IPEDS / NCES
- College Scorecard when useful

**International English policy**
- official university international admissions/admissions page

**International/nonresident cost**
- official university cost-of-attendance, bursar, or international-student financial page

**Current application deadline**
- official university admissions page

**Program existence**
- current official academic catalog/program page when exact current degree naming matters;
- recent IPEDS/Scorecard CIP evidence is acceptable for normalized field coverage but must be represented honestly.

**Scholarship/aid rule**
- official university scholarship/financial aid page only for recommendation-critical claims.

### 8.2 Conflicts

Do not silently choose between contradictory sources.

Store the conflict, identify both sources, and set status to `conflicting` until a rule or manual review resolves it.

### 8.3 Source freshness

Every time-sensitive record stores its year/cycle and retrieval time.

"Latest" is not a database value. Store the actual cycle/year used.

When importing from IPEDS, record the exact release/data year. Do not hardcode a year into recommendation logic.

---

## 9. Ingestion pipeline

### 9.1 Stage A — seed resolution

Input:

```text
data/seed/university_coverage_100.json
```

Resolve every entry to canonical IPEDS identity.

Matching sequence:

1. exact/known identifier;
2. exact normalized name + state;
3. alias;
4. RapidFuzz-assisted candidate generation;
5. manual review if still ambiguous.

A fuzzy score alone must never finalize a questionable identity.

### 9.2 Stage B — structured official datasets

Prefer openly downloadable IPEDS files for foundational data because they are reproducible and do not require a private API key.

College Scorecard may supplement where useful. If it is used via API, its key belongs in environment configuration and the importer must cache/retry responsibly.

Importers must be:

- idempotent;
- year-aware;
- validated;
- able to process a subset of institutions;
- able to resume after failure.

### 9.3 Stage C — official university page discovery

Start from the official domain.

Preferred discovery:

1. curated `data/source_seeds/official_urls.jsonl`;
2. official sitemap/robots-listed sitemaps;
3. internal-link discovery constrained to the official domain.

Search terms can include:

```text
international undergraduate
english proficiency
IELTS
TOEFL
Duolingo
cost of attendance
international student cost
nonresident tuition
undergraduate admissions deadline
```

Do not build a general web crawler.

### 9.4 Stage D — page fetch

Default:

```text
httpx → raw HTML
```

Then:

```text
Trafilatura → extracted content
```

Fallback to Playwright only if needed for a page whose necessary content is JavaScript-rendered.

Use:

- timeouts;
- bounded retries;
- identifiable user agent;
- low concurrency;
- caching;
- robots/site restrictions;
- no authentication bypass.

### 9.5 Stage E — structured extraction

Gemma receives the source text, source URL, and a narrow extraction schema.

Example conceptual request:

```text
Extract only English-proficiency facts explicitly supported by SOURCE_TEXT.
Return null/unknown when not stated.
For each extracted fact return a short evidence span from SOURCE_TEXT.
Do not use outside knowledge.
```

Gemma output is a candidate, not a database fact.

### 9.6 Stage F — validation

Before persistence:

- Pydantic schema validation;
- numeric range checks;
- enum checks;
- date/cycle validation;
- evidence-presence check against extracted source text;
- source-domain check where required;
- conflict detection against current facts.

Examples:

```text
0 <= IELTS <= 9
400 <= SAT total <= 1600
1 <= ACT <= 36
cost >= 0
deadline parses as a date
```

Do not assume every valid test score is an integer; preserve correct scale precision.

### 9.7 Stage G — persistence + deterministic export

Persist validated facts via Django ORM and update canonical JSONL exports.

One university failing enrichment must not destroy already-valid data for the other 99.

---

## 10. Recommendation-ready contract

A university is `recommendation_ready` only when all required conditions below are satisfied.

### Required

1. canonical institution identity is resolved;
2. institution is in the United States and bachelor's-granting;
3. operating status is acceptable;
4. at least one supported bachelor's program/CIP field is present;
5. official international undergraduate English-proficiency policy has been verified;
6. a current-enough official international/nonresident cost record exists;
7. there is at least one usable academic-positioning signal **or** an explicit verified/unavailable state explaining why standardized admissions statistics are unavailable;
8. every fact actually used by the recommender has provenance;
9. no unresolved conflict exists on a readiness-critical fact.

### Not required for recommendation readiness

- exact scholarship amount;
- SAT/ACT score if the institution does not report/use it;
- every program-specific deadline;
- every campus preference attribute;
- essay prompts.

### Journey-ready additional requirements

For roadmap generation, require at least:

1. verified current deadline or verified rolling-admission state;
2. general undergraduate/international application process source;
3. verified general required-document information.

Readiness is computed from data, not manually toggled to pass an acceptance test.

---

## 11. Applicant profile architecture

Profile fields are grouped by purpose.

### Stage / identity

```text
age_or_grade
graduation_year
citizenship_country
intended_intake
degree_level = bachelor
target_country = US
```

Do not collect data that is not needed for the journey.

### Academics

```text
gpa_value
gpa_scale
curriculum
subject_grades optional
```

Never compare GPA scales without an explicit normalization rule.

### Exams

```text
IELTS
TOEFL
Duolingo English Test
SAT
ACT
test dates / planned retakes optional
```

### Goals

Two paths:

```text
known major
```

or:

```text
help me choose
```

### Interests

Structured after collection into interest tags/program-family preferences.

### Financial

```text
annual_family_budget
budget_scope = tuition_only | total_cost
needs_aid
allow_aid_dependent_options
hard_maximum boolean
```

### Preferences

Examples:

```text
states/regions
urban/suburban/rural
institution size
public/private preference
climate optional
```

### Application readiness

Examples:

```text
transcript status
passport status
recommendations status
essay status
```

---

## 12. Program discovery

Free-form interests are mapped to normalized program families before universities are ranked.

```text
free-form interests
      ↓
structured interest profile
      ↓
program families / CIP areas
      ↓
actual ProgramOffering records
      ↓
university-program candidates
```

Gemma may create a structured interest interpretation, but the mapping output must be schema-valid and the final candidate set comes from the catalog.

Do not rank a university for a major it does not have evidence for.

---

## 13. Recommendation engine

The unit being evaluated is:

```text
Applicant × Institution × Program
```

### 13.1 Hard eligibility / exclusion

Hard rules must be separate from ranking.

Examples:

- program/degree is unavailable;
- verified English minimum is not met and no verified conditional path is acceptable;
- applicant explicitly sets a hard budget maximum and forbids aid-dependent options;
- a relevant deadline has already passed when the engine is running for a specific application cycle.

An unknown value is not automatically a failure. It produces uncertainty/warning and may reduce data confidence.

### 13.2 Fit dimensions

Keep dimensions independently inspectable:

```text
academic_fit
english_fit
program_fit
financial_fit
preference_fit
data_confidence
```

An internal aggregate ranking score may order candidates, but its components must remain available.

### 13.3 Academic positioning, not admission chance

Allowed descriptions include evidence-based states such as:

```text
below_reported_range
within_reported_range
above_reported_range
requirement_met
insufficient_data
```

Never output:

```text
"You have a 72% chance of admission."
```

unless a future separately validated statistical model genuinely supports that claim. No such model exists in the current architecture.

Acceptance rate is institutional context, not the applicant's probability.

### 13.4 English fit

Compare like with like against verified policy.

Example:

```text
Applicant IELTS 7.0
Verified minimum 6.5
→ meets_published_minimum
```

Do not infer that satisfying English proficiency means the student is academically competitive.

### 13.5 Financial fit

Compare the applicant's stated budget scope to an appropriately scoped cost record.

Useful output states:

```text
within_budget_without_aid
over_budget_aid_available
over_budget
affordability_uncertain
insufficient_cost_data
```

Do not subtract speculative scholarship values.

### 13.6 Program fit

Based on:

- known major match; or
- structured interest-to-program-family match.

Program fit must refer to an actual catalog offering.

### 13.7 Preference fit

Location, institution size/type, setting, and other soft preferences affect ordering but should not normally act as hard filters unless the applicant explicitly marks them hard.

### 13.8 Data confidence

Data confidence describes evidence quality/completeness, not admission likelihood.

Examples:

```text
high
medium
low
```

or a normalized internal score with transparent components.

---

## 14. Recommendation diversification

A raw score sort can produce repetitive results.

Diversification should avoid:

- five programs at the same institution occupying the list;
- five nearly identical institutions when similarly good alternatives exist.

The service should return institution-level recommendations with one primary program and optional alternate program(s).

Possible descriptive buckets may be used only if they are defined from factual positioning and are not presented as admission guarantees. Avoid labels that imply precise chances.

---

## 15. Explanations

The engine first creates structured reasons:

```json
{
  "dimension": "english",
  "status": "positive",
  "fact": "Applicant IELTS 7.0; verified minimum 6.5",
  "source_ids": ["..."]
}
```

Natural-language rendering can then be:

- deterministic templates; or
- Gemma rewriting the supplied reasons.

Gemma is prohibited from adding a fact that is not in the structured reason context.

Every factual statement exposed to the user should be traceable to stored sources.

---

## 16. Roadmap

Roadmap generation is rule-based first.

Examples:

```text
English minimum not met
→ add English retake/improvement task

required transcript not ready
→ add transcript task

deadline exists
→ schedule application work before deadline

financial documents required
→ add financial-document task
```

Roadmap task model:

```text
id
category
title
reason
priority
status
due_date optional
blocking boolean
source_ids
```

Gemma may improve wording, not invent requirements.

---

## 17. Next action

Do not simply return the first roadmap row.

Next action is selected using deterministic priority signals such as:

```text
blocking status
urgency
importance across target applications
dependency order
```

The result must explain why that action is next.

---

## 18. CLI target

Dataset commands:

```text
admission data seed
admission data import-ipeds
admission data import-scorecard
admission data discover-sources
admission data enrich-english
admission data enrich-costs
admission data validate
admission data readiness
admission data status
admission data export
```

Every batch command should support a subset/filter where practical.

Journey commands:

```text
admission profile create
admission diagnose
admission recommend
admission compare
admission roadmap
admission journey
```

Exact syntax can evolve, but one coherent CLI must exist.

---

## 19. Later Django HTTP layer

Once CLI journey behavior is accepted:

- expose the same application services through Django;
- do not duplicate recommendation calculations in serializers/views;
- persist profiles, favorites, roadmap progress, and selected targets;
- add request validation at the transport boundary;
- source/citation information remains part of API responses.

The web layer is a consumer of the backend, not a second implementation.

---

## 20. Error handling

### Source unavailable

- retry only within bounded policy;
- record fetch failure;
- preserve older verified data with its date if present;
- mark freshness appropriately;
- do not replace valid data with null because a refresh failed.

### Extraction fails

- keep source document metadata;
- create review issue;
- do not persist candidate facts.

### Ambiguous institution match

- no automatic final mapping;
- create review issue.

### Conflicting values

- retain conflict/provenance;
- do not silently overwrite.

### LLM unavailable

- extraction job may be deferred/reported;
- recommendation engine itself remains functional with stored data.

### One bad institution

- batch continues;
- exit/report communicates partial failure;
- command is safe to rerun.

---

## 21. Idempotency and reproducibility

Data commands must be safe to rerun.

Use stable natural identifiers such as:

```text
IPEDS UNITID
institution + CIP + credential level + data year
institution + test type + applicant scope + cycle
institution + cost scope + academic year
```

Do not create duplicate records merely because an importer runs twice.

Store importer/extractor version metadata when useful for debugging.

---

## 22. Security and privacy

- secrets only from environment/configuration;
- `.env` is never committed;
- `.env.example` contains names, not secrets;
- never include API keys in task reports or ZIPs;
- no arbitrary code execution from downloaded pages;
- no authentication bypass;
- no collection of unnecessary sensitive applicant data;
- logs must not dump secrets;
- fetched content is treated as untrusted input.

---

## 23. Current verified external assumptions

At architecture time:

- Alem exposes Gemma4 through an OpenAI-compatible chat-completions API.
- IPEDS provides institutional characteristics, pricing, admissions, enrollment, completions/CIP, and related U.S. postsecondary datasets and downloadable data files.
- Trafilatura supports extracting main web content and metadata from downloaded HTML.
- RapidFuzz is an open-source fuzzy string matching library suitable for candidate matching.

Code must not assume current dataset release years forever. Importers record the actual release/year they consume.

---

## 24. Definition of "fully working" for the initial scope

The project is fully working within its declared coverage when:

- arbitrary supported applicant profiles can be entered;
- recommendations are computed dynamically;
- the system evaluates real university/program data rather than hard-coded jury results;
- recommendation reasons correspond to actual profile fields and stored facts;
- changing budget, tests, or interests can materially change results where data supports it;
- unknowns are exposed honestly;
- the journey continues through comparison, roadmap, and next action;
- the same backend is callable from CLI and later Django HTTP;
- coverage is clearly stated as the current 100 institutions, not misrepresented as all U.S. universities.
