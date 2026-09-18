# AGENTS.md

# Executor Rules

This repository uses a strict architect/executor/reviewer workflow.

- **ChatGPT in the architecture conversation is the architect/reviewer.**
- **Codex is the executor.**
- The user transfers each Codex task result back to the architect for review.
- Codex never decides to advance to the next task on its own.

These rules are mandatory unless the user explicitly overrides one for a specific run.

---

## 1. One task per run

Execute **exactly one numbered task** from `plan.md`, or one explicit fix-task supplied by the architect.

Do not:

- begin the next task;
- implement "while I am here" features;
- create future modules that are not needed by the current task;
- perform speculative refactors outside the current task;
- expand scope because another change seems useful.

When the current task's acceptance criteria are satisfied, stop and prepare the handoff.

If a prerequisite is missing, make only the minimum prerequisite change necessary for the current task and document it. If satisfying the prerequisite would materially expand scope, stop and report the blocker instead of silently doing multiple tasks.

---

## 2. Architect decisions are constraints

Read before work:

1. `architecture.md`
2. `AGENTS.md`
3. the current task in `plan.md`

If code and architecture disagree:

- do not silently redesign the system;
- prefer the architecture unless it is technically impossible;
- describe the conflict in the task report.

Do not replace major selected technologies without explicit approval.

Examples of locked decisions:

- Django is the persistence foundation from the beginning.
- CLI is built before the Django HTTP/user-interface layer.
- Django ORM owns runtime persistence.
- canonical dataset exports are reviewable text data, not only SQLite.
- Alem Gemma4 is accessed behind an internal adapter.
- recommendation logic is deterministic and must not depend on LLM availability.
- facts require provenance.
- no admission probability claims.
- unknown values must remain unknown.

---

## 3. Dataset integrity rules

### Never fabricate university data

Do not invent or "fill in a reasonable value" for:

- IELTS/TOEFL/DET requirements;
- SAT/ACT policies;
- SAT/ACT ranges;
- tuition or cost;
- deadlines;
- scholarships;
- admission rates;
- program availability;
- aid availability;
- any other recommendation-critical fact.

When data cannot be verified, store an explicit status such as:

```text
not_found
not_reported
unverified
conflicting
stale
extraction_failed
```

### Source every recommendation-critical fact

A usable fact must retain enough provenance to audit it:

```text
source URL/source identity
retrieval date
data year/cycle when relevant
evidence or structured-source locator
extraction method
```

### Official-source policy

Use the source policy in `architecture.md`.

Do not use blogs, ranking sites, random aggregators, or LLM memory as factual authority for recommendation-critical values when an official source is required.

### LLM extraction is candidate extraction

Gemma output is not truth.

Before persistence:

- validate schema;
- validate numeric ranges;
- verify evidence against supplied source content;
- detect conflicts;
- preserve unknowns.

Never ask Gemma "What is University X's IELTS requirement?" without supplying the actual source content being extracted.

### No readiness cheating

Do not set `recommendation_ready=true` merely to meet a count.

Readiness must be computed from the documented contract.

---

## 4. Data-fetching rules

- Respect site restrictions and robots instructions.
- Use low/bounded concurrency.
- Use timeouts.
- Use bounded retries.
- Cache downloaded content locally.
- Do not bypass authentication or bot protection.
- Do not scrape private/user data.
- Treat all downloaded content as untrusted.
- Prefer normal HTTP + Trafilatura.
- Use Playwright only when necessary for required JS-rendered content.
- Do not install or introduce a scraping dependency merely because it is popular; use it only when the current task needs it.

If a site blocks automated access, record the problem and use an allowed official alternative/manual source seed rather than attempting to defeat the block.

---

## 5. Secrets

Never:

- hardcode `ALEM_API_KEY`;
- commit `.env`;
- put secrets in logs;
- put secrets in the task report;
- put secrets in the ZIP.

Use environment variables.

`.env.example` may contain:

```text
ALEM_API_KEY=
ALEM_BASE_URL=https://llm.alem.ai/v1
ALEM_MODEL=gemma4
```

but never a real key.

---

## 6. Scope discipline

Before editing, identify the smallest file set likely needed.

Do not perform:

- unrelated formatting;
- dependency upgrades unrelated to the task;
- repository-wide renames;
- broad cleanup;
- style rewrites;
- architecture changes outside the task;
- large generated file changes unrelated to acceptance criteria.

Preserve existing user work.

If the repository is already dirty, inspect and record pre-existing changes before editing. Do not include untouched pre-existing changes in the task ZIP.

---

## 7. Testing policy

### Default: targeted tests only

Do **not** run the whole test suite after every task.

Run the smallest test set that gives meaningful confidence for the files/behavior changed.

Examples:

```text
catalog importer changed
→ catalog importer/unit tests + directly affected repository tests

one validator changed
→ validator tests + relevant regression test

recommendation scoring changed
→ scoring tests + recommendation scenario tests
```

### Full suite

A full suite is allowed when:

- the task is explicitly cross-cutting;
- shared infrastructure changed in a way that can affect most modules;
- database/model changes touch many bounded areas;
- the architect/user explicitly requests it;
- the task is a release/milestone integration check.

If you run the full suite, state why.

If you do not run it, say:

```text
Full suite not run: change was scoped to ...
```

### Exact reporting

The task report must contain:

- exact test command(s);
- pass/fail count or command outcome;
- failures/skips that matter;
- whether full suite was run.

Never write "tests pass" without saying what was run.

### Network tests

Normal tests should not require live external websites/APIs.

Live ingestion/verification commands are operational checks, not replacements for deterministic tests. Report them separately.

---

## 8. Do not hide failures

A task is not complete when:

- targeted tests fail;
- acceptance criteria fail;
- required data count is lower than claimed;
- validation reports critical errors;
- data was silently skipped;
- a migration is missing;
- output depends on an uncommitted secret/config value not documented.

If blocked:

1. stop;
2. preserve useful work;
3. explain the blocker precisely;
4. do not fake completion.

The architect will decide the fix-task.

---

## 9. Migrations and database changes

When a task changes Django models:

- create the required migration in that task;
- run the targeted migration/model checks needed for that change;
- do not edit an already-applied migration merely to make tests easier unless the task is still in an explicitly disposable initial migration state;
- do not commit a runtime SQLite database.

Model changes and canonical data format changes must be documented in the report.

---

## 10. Deterministic catalog exports

When writing `data/canonical/*.jsonl`:

- stable ordering;
- stable identifiers;
- no unrelated rewrite;
- no random values;
- no export timestamp that causes every row to change;
- UTF-8;
- valid schema;
- only normalized facts and reviewable evidence/provenance.

Raw HTML belongs in ignored cache, not the canonical dataset.

---

## 11. Dependency rules

Prefer existing dependencies.

Add a dependency only when:

- it materially simplifies/reliably solves the current task;
- it fits `architecture.md`;
- a standard-library/existing dependency solution would be meaningfully worse.

Any added dependency must be listed in the report with a one-line reason.

Do not replace dependencies selected in architecture without approval.

---

## 12. Coding rules

- Keep business logic out of Django views and CLI command functions.
- Keep recommendation logic out of ORM models.
- Use typed boundaries/DTOs where data crosses layers.
- Prefer small pure functions for scoring/validation.
- Keep network access behind dedicated clients/fetchers.
- Keep LLM access behind `admission.llm`.
- Avoid hidden global state.
- Make batch ingestion idempotent/resumable.
- One bad university should not normally abort all 100.
- Log actionable identifiers, never secrets.
- Do not swallow broad exceptions without recording context.
- Comments explain "why", not obvious syntax.
- No dead code or placeholder fake implementation to satisfy an interface.

---

## 13. Recommendation safety/correctness rules

Never output or implement fake admission probabilities.

Do not equate:

```text
meets minimum requirement
```

with:

```text
likely admitted
```

Do not equate:

```text
missing SAT data
```

with:

```text
test optional
```

Do not equate:

```text
average domestic net price
```

with:

```text
international student's expected cost
```

Do not equate:

```text
CIP field found
```

with an invented exact program title.

Do not let overall score erase individual warnings.

---

## 14. Start-of-task procedure

At the beginning of every executor run:

1. Read the three project instruction files.
2. Identify the exact current task/fix-task.
3. Inspect repository status.
4. Record the baseline changed/untracked paths before editing.
5. Do not overwrite unrelated pre-existing user changes.
6. Inspect only the code/data needed for the task.
7. Execute the task.

Do not create a separate plan that changes the architect's task ordering.

---

## 15. End-of-task handoff — mandatory

Every run must end with two artifacts:

1. **Task report**
2. **Delta ZIP**

### 15.1 Task report

Create a Markdown report named:

```text
TASK-<NNN>-REPORT.md
```

For a fix task:

```text
TASK-<NNN>-FIX-<N>-REPORT.md
```

The report must contain:

```markdown
# Task <N> Report

## Result
PASS | BLOCKED | FAIL

## Scope
What this task was supposed to do.

## What changed
Concrete behavior/data changes.

## Files created or modified
- path
- path

## Data changes
Counts and important dataset changes, if any.

## Migrations
Migration names and what they do, or "None".

## Dependencies
New/removed dependencies and reason, or "None".

## Commands run
Exact relevant commands.

## Tests run
Exact test commands and results.

## Operational/live checks
Any live data import/fetch/validation commands and outcomes.

## Acceptance criteria
- [x] ...
- [ ] ...

## Known issues / limitations
Anything unresolved.

## Pre-existing repository changes not touched
List them, or "None observed".
```

Do not claim `PASS` if any mandatory acceptance criterion is unchecked.

### 15.2 Delta ZIP

Create:

```text
TASK-<NNN>-CHANGES.zip
```

or:

```text
TASK-<NNN>-FIX-<N>-CHANGES.zip
```

The ZIP must contain **only**:

- repository files created by this task;
- repository files modified by this task;
- the task report.

Preserve repository-relative paths inside the ZIP.

Example:

```text
TASK-004-REPORT.md
src/admission/catalog/ingestion/extraction.py
src/admission/catalog/schemas.py
tests/catalog/test_extraction.py
data/canonical/english_requirements.jsonl
```

### 15.3 ZIP exclusions

Never include merely because they exist:

```text
.git/
.venv/
venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
.env
*.sqlite3
*.db
coverage artifacts
raw source cache
browser cache
unrelated generated files
unchanged repository files
```

Never include a secret.

### 15.4 Determining the delta

Capture repository state at task start.

At handoff, compare against that baseline so the ZIP does not accidentally include:

- the user's earlier uncommitted changes;
- files changed by a previous task;
- unrelated untracked files.

Git may be used to inspect status/diffs, but **do not commit or push** unless the user explicitly asks.

If a current task intentionally modifies a file that was already dirty at baseline, say so explicitly in the report and include that file because the task modified it.

---

## 16. Stop rule

After producing the report and delta ZIP:

**STOP.**

Do not:

- execute the next plan task;
- prepare code for the next task;
- fix non-blocking future issues;
- mark the next task started.

The user will send the ZIP to the architect.

The architect will respond with either:

```text
PASS → next task
```

or:

```text
FAIL → focused fix-task
```

Only then may execution continue.
