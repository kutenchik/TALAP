# plan.md

# Personal Admission Journey — Execution Plan

## How this plan is used

This is a sequential architect-controlled roadmap.

**Codex executes one task per run.**

After each task:

1. Codex produces `TASK-<NNN>-REPORT.md`.
2. Codex produces `TASK-<NNN>-CHANGES.zip` containing only files created/modified by that run plus the report.
3. The user sends the ZIP to the architect.
4. The architect reviews it.
5. Only after `PASS` does the architect authorize the next task.
6. If review fails, the architect supplies a focused fix-task.

Do not work ahead.

The plan intentionally uses small reviewable steps. The first major milestone is **100 recommendation-ready universities**. Recommendation logic begins only after that catalog milestone passes.

---

# Milestone A — 100 recommendation-ready universities

## TASK-001 — Resolve the 100 seed universities into real canonical institutions

### Goal

Turn the existing 100-name coverage seed into **100 canonical, real U.S. institution records backed by authoritative structured data**.

This is the first executor task.

It does **not** yet need to make all 100 recommendation-ready; it establishes the factual institutional foundation needed to enrich them safely.

### Required input

Existing seed manifest:

```text
university_coverage_100.json
```

Place/copy it into:

```text
data/seed/university_coverage_100.json
```

only if the repository does not already have an architect-approved equivalent.

### Implement only what this task needs

Minimal Django/catalog foundation required to:

- represent `Institution`;
- represent `InstitutionAlias` if needed for matching;
- represent structured source metadata needed by this import;
- import seed records;
- resolve them against authoritative IPEDS/NCES data;
- export deterministic canonical institution JSONL;
- show resolution status from CLI.

Do not build recommendations, profiles, roadmap, Django views, English extraction, or cost scraping yet.

### Data source

Prefer official downloadable IPEDS/NCES data for institutional identity and characteristics.

Record the exact data file/release year used.

Do not require a private API key for this task if the official downloadable files are sufficient.

### Required canonical fields

For every seed entry, resolve at minimum:

```text
IPEDS UNITID
canonical institution name
state
city
country = US
ownership/control
official website when present in official data
operating/status information available from source
bachelor's-granting eligibility/level evidence
source/data year
seed alias/name
```

### Matching requirements

- exact identifiers/names where possible;
- state must be used as a disambiguator;
- fuzzy matching may propose candidates;
- fuzzy matching must not silently finalize an ambiguous school;
- any unresolved record must become an explicit review item.

### CLI

Add the minimum commands needed for this task, for example:

```text
admission data seed
admission data import-ipeds
admission data status
admission data export
```

Exact naming can vary only if it remains coherent.

### Acceptance criteria

- [ ] exactly 100 seed entries are represented;
- [ ] exactly 100 are either canonically resolved or explicitly reported as unresolved — no silent drops;
- [ ] target for PASS is 100/100 canonical UNITID resolution;
- [ ] no duplicate UNITID is incorrectly assigned to multiple distinct seed universities;
- [ ] state/campus mismatches are checked;
- [ ] institutional facts come from authoritative structured source data;
- [ ] source release/year is recorded;
- [ ] canonical institution export is deterministic and reviewable;
- [ ] runtime SQLite file is not committed/included;
- [ ] targeted importer/matching/export tests pass;
- [ ] report includes a table/count of resolved, ambiguous, and unresolved entries.

### Targeted tests

Run only catalog foundation tests introduced/affected by this task.

A full suite is unnecessary unless project-wide bootstrap changes make it justified.

### Stop

Produce report + delta ZIP and stop.

---

## TASK-002 — Import bachelor's program/CIP coverage for all 100

### Goal

Attach normalized bachelor's-level field-of-study coverage to each canonical institution.

### Data source

Use authoritative IPEDS/NCES completions/CIP data and/or College Scorecard field-of-study data as appropriate.

Record source year and meaning precisely.

A recent CIP/completions record proves evidence of a field/award; it does not automatically justify inventing a current official degree title.

### Required behavior

- normalize CIP codes/titles;
- preserve credential/award level;
- restrict recommendation catalog to supported bachelor's-level evidence;
- idempotent import;
- deterministic `programs.jsonl`;
- report institutions with unexpectedly zero program coverage.

### Acceptance criteria

- [ ] all 100 institutions processed;
- [ ] program records use valid institution identities;
- [ ] no graduate-only record is represented as a bachelor's offering;
- [ ] CIP/source year preserved;
- [ ] duplicate imports do not create duplicate program rows;
- [ ] zero-program institutions are explicit issues, not silent omissions;
- [ ] targeted program import tests pass.

### Stop

Report + delta ZIP, then stop.

---

## TASK-003 — Import admissions statistics and standardized-test evidence

### Goal

Add authoritative admissions context for the 100 institutions.

### Import where available

```text
admission/applicant counts
admitted counts
admission rate
SAT EBRW 25/75
SAT Math 25/75
ACT composite 25/75
data year
```

Use explicit status when an institution does not report/apply a metric.

Do **not** infer test-optional policy merely from missing score distributions.

### Acceptance criteria

- [ ] all 100 processed;
- [ ] data year/source preserved;
- [ ] numeric validations enforced;
- [ ] absence is distinguished from zero;
- [ ] no admission-chance calculation exists;
- [ ] deterministic admissions export exists;
- [ ] targeted tests pass.

### Stop

Report + ZIP.

---

## TASK-004 — Build official-page fetch/extraction infrastructure and verify it on a pilot batch

### Goal

Implement the official-source pipeline before processing all 100.

### Scope

Build:

- source seed model/data format;
- official-domain constrained discovery;
- HTTP fetch/cache;
- Trafilatura extraction;
- Playwright fallback interface only if genuinely needed;
- Alem Gemma4 client adapter;
- Pydantic structured extraction;
- evidence verification;
- review issue creation;
- retry/error handling.

### Pilot

Use a small architect-specified or deterministic first batch of institutions to prove the pipeline for **English-proficiency requirements**.

Do not process all 100 in this task.

### Gemma configuration

```text
ALEM_API_KEY
ALEM_BASE_URL=https://llm.alem.ai/v1
ALEM_MODEL=gemma4
```

The API key must never enter Git/report/ZIP.

### Acceptance criteria

- [ ] LLM client is isolated behind adapter;
- [ ] source text is supplied to extraction prompt;
- [ ] extractor returns schema-valid candidate data;
- [ ] evidence must exist in source text before candidate persistence;
- [ ] missing fact remains unknown;
- [ ] failures create explicit issues;
- [ ] cached raw pages are gitignored;
- [ ] normal tests mock external network/LLM;
- [ ] pilot records contain official source provenance;
- [ ] targeted tests pass.

### Stop

Report + ZIP.

---

## TASK-005 — English requirements batch 1

### Goal

Populate/verify international undergraduate English policy for institutions 1–25 in deterministic seed order.

### Required extraction

As available:

```text
IELTS
TOEFL
Duolingo English Test
minimum scores
subscore requirements
waiver/alternative policy
conditional admission only if explicitly stated
cycle/current-policy status
official source
evidence
```

### Acceptance criteria

- [ ] all 25 attempted;
- [ ] each has verified records or explicit unresolved issue;
- [ ] no guessed requirements;
- [ ] source URL and retrieval date stored;
- [ ] evidence validation passes;
- [ ] dataset export updates only relevant records;
- [ ] targeted validation/tests pass.

### Stop

Report + ZIP.

---

## TASK-006 — English requirements batch 2

Process institutions 26–50 using the same contract as TASK-005.

Stop with report + ZIP.

---

## TASK-007 — English requirements batch 3

Process institutions 51–75 using the same contract as TASK-005.

Stop with report + ZIP.

---

## TASK-008 — English requirements batch 4

Process institutions 76–100 using the same contract as TASK-005.

At the end report:

```text
verified policy count
unresolved count
conflicting count
fetch/extraction failure count
```

Stop with report + ZIP.

---

## TASK-009 — Build official international/nonresident cost ingestion and verify a pilot batch

### Goal

Add the cost model/extractor/validation path without processing all 100 at once.

### Prefer

Official:

```text
international student cost
nonresident undergraduate cost of attendance
bursar tuition + required costs
```

### Store

As available:

```text
academic year
scope
tuition
mandatory fees
housing/food
insurance
books/supplies
personal/transport
published total
calculated total if necessary
currency
source
evidence
```

If calculating total from official components, store the components and calculation explicitly.

Do not use average domestic net price as expected international cost.

### Acceptance criteria

- [ ] schema and validation implemented;
- [ ] academic year required;
- [ ] source/evidence required;
- [ ] pilot records verified;
- [ ] calculation logic tested;
- [ ] missing components do not become zero unless source explicitly says zero;
- [ ] targeted tests pass.

### Stop

Report + ZIP.

---

## TASK-010 — Cost batch 1

Populate/verify institutions 1–25.

Stop with report + ZIP.

---

## TASK-011 — Cost batch 2

Populate/verify institutions 26–50.

Stop with report + ZIP.

---

## TASK-012 — Cost batch 3

Populate/verify institutions 51–75.

Stop with report + ZIP.

---

## TASK-013 — Cost batch 4

Populate/verify institutions 76–100.

Report verified/unresolved/conflicting/stale counts.

Stop with report + ZIP.

---

## TASK-014 — Verify standardized-test policy where recommendation logic needs it

### Goal

Separate actual SAT/ACT submission policy from availability of score statistics.

Use official admissions sources for current international/first-year policy where needed.

### Acceptance criteria

- [ ] missing IPEDS score data is never used as policy evidence;
- [ ] policy cycle/source/evidence stored;
- [ ] all 100 have verified policy or explicit unresolved state;
- [ ] targeted tests pass.

### Stop

Report + ZIP.

---

## TASK-015 — Recommendation-readiness engine and 100-school audit

### Goal

Implement the readiness contract from `architecture.md`, compute it from facts, and audit the full catalog.

### Required CLI

At least:

```text
admission data readiness
admission data status
admission data validate
```

Status must make gaps obvious.

### Acceptance criteria

- [ ] readiness is computed, not manually forced;
- [ ] every critical fact used has provenance;
- [ ] conflicts block readiness where required;
- [ ] validation covers all 100;
- [ ] report lists every non-ready institution and exact blockers;
- [ ] targeted tests pass.

### Passing target

The product goal is:

```text
100 / 100 recommendation_ready
```

If fewer than 100 are ready, this task must report `BLOCKED` rather than fake PASS. The architect will create focused data fix-tasks for remaining blockers.

### Stop

Report + ZIP.

---

# Milestone B — Applicant profile and diagnostic

Begin only after Milestone A is accepted.

## TASK-016 — Applicant profile schema and persistence

### Goal

Implement the supported applicant profile with typed validation and persistence.

Include:

- academic stage;
- GPA + scale;
- tests;
- intended intake;
- known-major vs help-me-choose path;
- interests;
- budget and budget scope;
- aid dependency preference;
- university preferences;
- application readiness fields.

### Requirements

- validate test ranges;
- preserve missing vs zero;
- no implicit GPA conversion across scales;
- JSON import/export for CLI convenience;
- Django persistence.

### Tests

Target profile validation/persistence tests only.

### Stop

Report + ZIP.

---

## TASK-017 — Interactive CLI questionnaire

### Goal

Create a usable CLI flow to create/edit a profile.

The CLI must explain ambiguous financial questions, especially:

```text
annual budget
tuition-only vs total cost
aid required
willingness to consider aid-dependent options
```

### Acceptance criteria

- [ ] complete profile can be entered without hand-editing JSON;
- [ ] invalid inputs are recoverable;
- [ ] saved profile can be reloaded;
- [ ] targeted CLI/profile tests pass.

### Stop

Report + ZIP.

---

## TASK-018 — Diagnostic service

### Goal

Produce a factual profile diagnostic:

```text
goal
strengths
constraints
missing information
financial constraints
test/English status
```

Do not recommend universities yet.

### Stop

Report + ZIP.

---

# Milestone C — Program discovery

## TASK-019 — Program-family taxonomy and deterministic matching

### Goal

Create the normalized mapping layer:

```text
interest tags → program families → CIP areas
```

Support known-major users without LLM.

No university ranking yet.

### Stop

Report + ZIP.

---

## TASK-020 — Gemma-assisted "help me choose" interpretation

### Goal

Use Alem/Gemma to turn free-form interests into a validated structured interest profile/program-family candidates.

Requirements:

- Pydantic output;
- bounded allowed taxonomy;
- no university recommendations in the prompt/output;
- deterministic fallback when LLM unavailable;
- targeted mocked tests.

### Stop

Report + ZIP.

---

# Milestone D — Recommendation engine

## TASK-021 — Candidate generation and hard eligibility

### Goal

Generate real `Applicant × Institution × Program` candidates and apply hard constraints.

Implement only eligibility/candidate generation.

### Key rules

- must have program evidence;
- English policy logic uses verified facts;
- unknown does not silently equal pass/fail;
- hard budget only when user explicitly chooses a hard maximum rule.

### Stop

Report + ZIP.

---

## TASK-022 — Academic and English fit dimensions

### Goal

Implement explainable positioning without admission probability.

States such as:

```text
below_reported_range
within_reported_range
above_reported_range
meets_published_minimum
insufficient_data
```

### Stop

Report + ZIP.

---

## TASK-023 — Financial fit

### Goal

Compare budget scope against correct official cost scope.

Output states such as:

```text
within_budget_without_aid
over_budget_aid_available
over_budget
affordability_uncertain
insufficient_cost_data
```

Do not estimate unverified aid.

### Stop

Report + ZIP.

---

## TASK-024 — Program/preference fit and aggregate ordering

### Goal

Implement:

```text
program_fit
preference_fit
data_confidence
internal ranking score
```

Keep dimensions independently inspectable.

Add scenario/regression tests proving that meaningful profile changes can affect ordering.

### Stop

Report + ZIP.

---

## TASK-025 — Recommendation diversification

### Goal

Prevent repetitive outputs such as many programs from one university or a near-duplicate top list.

Return institution-level recommendations with primary program + optional alternates.

### Stop

Report + ZIP.

---

## TASK-026 — Explainable recommendation output

### Goal

Create structured recommendation reasons/warnings with source IDs.

Implement deterministic natural-language rendering first.

Gemma rewriting may be added only as an optional layer that receives facts/reasons and cannot create new facts.

### Stop

Report + ZIP.

---

# Milestone E — Comparison and journey

## TASK-027 — Comparison service + CLI

Compare at least two selected recommendations on user-relevant dimensions:

```text
program
academic positioning
English
cost/budget
location/preferences
data confidence
important warnings
```

No fake winner label.

Stop with report + ZIP.

---

## TASK-028 — Current application deadlines and journey-ready data pipeline

### Goal

Collect/verify the deadline/application-process facts required for roadmap generation.

Process in reviewable batches if the architect splits this task after seeing catalog/source behavior.

A deadline must have:

```text
cycle
term
applicant scope
date or rolling state
official source
retrieval date
```

Stop with report + ZIP.

---

## TASK-029 — Roadmap rule engine

Generate tasks from verified requirements/profile gaps.

Examples:

```text
exam
document
deadline
academic preparation
application submission
financial document
```

LLM must not invent requirements.

Stop with report + ZIP.

---

## TASK-030 — Next-action selection and progress

Implement:

- roadmap task status;
- progress tracking;
- deterministic next-action selection based on blocker/urgency/dependencies;
- explanation for why it is next.

Stop with report + ZIP.

---

## TASK-031 — End-to-end CLI journey

### Goal

One coherent CLI scenario:

```text
questionnaire
→ diagnostic
→ program choice/discovery
→ recommendations
→ comparison
→ roadmap
→ next action
```

State persists across commands.

### Integration validation

This is a cross-cutting milestone. A broader test run is justified here.

Required scenario tests:

1. lower budget materially changes financial fit/recommendations where expected;
2. change CS interest to another field and program recommendations change;
3. lower English score causes verified minimum warnings/exclusions where applicable;
4. missing SAT does not automatically fail or become "test optional";
5. unknown catalog facts remain visible as uncertainty;
6. same valid input produces deterministic core ranking.

Stop with report + ZIP.

---

# Milestone F — Django web backend

Begin only after CLI journey is accepted.

Django ORM already exists; this milestone adds HTTP product surfaces, not a second backend.

## TASK-032 — Web/API transport for profile + diagnostic

Expose existing services.

No duplicated business logic.

Stop with report + ZIP.

---

## TASK-033 — Web/API transport for recommendations + comparison

Return structured recommendation reasons and source metadata needed by UI.

Stop with report + ZIP.

---

## TASK-034 — Web/API transport for roadmap + progress

Expose roadmap, next action, and progress mutations.

Stop with report + ZIP.

---

## TASK-035 — Web integration/error-state hardening

Cover:

```text
invalid profile
missing catalog data
LLM unavailable
source warning
no eligible program
budget too restrictive
stale requirement
```

No dead ends.

This is cross-cutting; broader tests may be justified.

Stop with report + ZIP.

---

# Milestone G — Submission hardening

## TASK-036 — Data/source audit

Audit all claims surfaced in the primary journey.

Ensure sources/statuses are exposed correctly and no unsupported deadline/cost/requirement is presented as fact.

Stop with report + ZIP.

---

## TASK-037 — README and technical notes

Document:

- problem/audience;
- solution;
- architecture;
- launch;
- CLI test scenario;
- later web launch;
- data sources;
- Alem/Gemma usage;
- open-source dependencies/components;
- data verification method;
- limitations;
- team roles;
- secrets/config.

Documentation must describe the real implementation, not planned features.

Stop with report + ZIP.

---

## TASK-038 — Final regression and release check

This is explicitly a large milestone task, so the full automated test suite is appropriate.

Also run:

- migration checks;
- catalog validation;
- 100-school readiness report;
- one full CLI journey;
- key Django journey checks if web layer is present;
- secret/leak sanity check;
- deterministic-data export check.

Report exact commands and results.

Stop with report + ZIP.

---

# Architect review rules between tasks

The architect reviews each ZIP for:

1. task scope compliance;
2. architecture compliance;
3. correctness;
4. data provenance;
5. tests and whether they were appropriately targeted;
6. unintended file changes;
7. security/secrets;
8. maintainability;
9. acceptance criteria.

Possible review result:

```text
PASS
```

The architect then supplies/authorizes the next task.

Or:

```text
FAIL
```

The architect supplies a focused fix-task such as:

```text
TASK-005-FIX-1
```

A fix-task must repair the rejected task only. It must not advance the plan.

---

# Immediate next executor task

The next Codex run is:

```text
TASK-001 — Resolve the 100 seed universities into real canonical institutions
```

Do not execute TASK-002 until the architect has reviewed TASK-001's delta ZIP and explicitly passed it.
