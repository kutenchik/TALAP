# TASK-FE-004 Report

## Result
PASS. Desktop university recommendations implemented using the accepted journey service and cache.

## Scope and behavior
- RecommendationsPage replaces the placeholder and reuses useJourney, loadJourney, and all FE-003 contracts.
- UniversityRecommendationCard renders institution name/state, recommendation state, program summary and individual CIP evidence/year, English policy/test assessment states, exact requirement/attempt scales and scores, applicability dates/cycle, conditional-policy presence, SAT/ACT context states/year, evidence quality, backend reasons and actions.
- Display-only exhaustive mappings preserve backend semantics. Backend order is retained, including within filters.
- Profile preparation offers Complete profile without recommendation cards. Empty, all-excluded, and all-insufficient states are explicit.
- Profile and Diagnostics completion are supplied only after a successful journey response.
- Compare selection uses sessionStorage key talap.compareUnitids, containing only identifier numbers. It restores valid eligible IDs, removes duplicates/stale/excluded IDs, limits selection to three, and enables Compare selected with two or three. Storage failure on selection displays a message and disables continuation. Compare itself remains the accepted placeholder.
- No backend policy calculations, probabilities, invented costs, rankings, deadlines, or new domain behavior.

## Files created or modified
- frontend/src/app/App.tsx
- frontend/src/components/UniversityRecommendationCard.tsx
- frontend/src/lib/recommendationLabels.ts
- frontend/src/pages/RecommendationsPage.tsx
- frontend/src/pages/useCompareSelection.ts
- frontend/src/styles/index.css
- frontend/src/test/app.test.tsx
- frontend/src/test/recommendationFixtures.ts
- frontend/src/test/recommendations.test.tsx
- frontend/src/test/profile.test.tsx
- TASK-FE-004-REPORT.md

## Tests and commands
The host has no npm executable. Equivalent installed commands/package scripts were used:
- frontend: .\node_modules\.bin\vitest.cmd --run: 52 tests passed, 5 files passed. Full frontend suite was explicitly requested.
- frontend: .\node_modules\.bin\eslint.cmd . --max-warnings 0: PASS after fixing a synchronous effect state update.
- frontend: bundled pnpm.cmd run build (tsc --noEmit && vite build): PASS.
- git diff --check: PASS (line-ending notices only).
Tests cover backend order, all states, conservative program/English/academic content, TOEFL scales, returned action/reason labels, financial action, forbidden claims, 2-3 selection limits, excluded/stale selections, session remount/route transition, filtering, preparation, empty and insufficient/excluded results, and StrictMode request deduplication.
Backend suite not run: backend unchanged.
An intermediate rerun exposed a pre-existing Profile test race between rendering the Diagnostics heading and starting its effect. The assertion now waits for the journey request; profile.test.tsx is therefore also intentionally modified and included in this task delta.

## Browser review
In-app browser inspection completed at 1440x900 and 1720x900 using a temporary local fixture harness, removed before handoff. Error state also inspected against the application route; Django was not running. Fixture cards, step states, scrolling, disabled fourth selection and enabled comparison CTA inspected. Document scroll widths were 1425 and 1705 respectively, with no horizontal overflow. No reference screenshot was supplied; pixel parity is not claimed. This is not a live Django integration check.

## Data, migrations, dependencies
None changed. Backend, data/, .var/, canonical files and examples untouched. No new package dependency or secrets.

## Acceptance criteria
- [x] Actual journey contract reused with conservative labels and backend order.
- [x] Four states, empty/preparation states, evidence/reasons/actions rendered.
- [x] Compare selection and filters accessible and session-persisted.
- [x] Tests, lint, build and desktop visual review completed.
- [x] Task-only delta ZIP produced.

## Pre-existing changes
Accepted FE-003 was uncommitted at task start: frontend/README.md; app/App.tsx; layouts/DesktopShell.tsx; lib/profiles.ts, journey.ts, journeyLabels.ts; pages/DiagnosticsPage.tsx, useJourney.ts; styles/index.css; test/app.test.tsx, profile.test.tsx, profileFixtures.ts, diagnostics.test.tsx, journeyFixtures.ts; types/journey.ts; TASK-FE-003 report and ZIP. FE-004 intentionally edits the already-dirty App.tsx, index.css and app.test.tsx; their full current files are included in this delta. Other FE-003 files are excluded from the FE-004 ZIP. User explicitly requested committing/pushing results including this prerequisite.

## FE-005 limitations
Compare and Roadmap remain placeholders. FE-005 can recover eligible selected IDs from the current journey and sessionStorage. No backend persistence/authentication/mobile implementation. Live Django integration remains to be checked with a running backend.
