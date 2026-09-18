# TASK-FE-003 Report

## Result

PASS - the desktop `/diagnostics` placeholder is replaced by a factual ApplicantDiagnostic experience backed by the existing journey endpoint. Recommendations, Compare, Roadmap, mobile, backend domain logic, and university-data behavior were not implemented.

Baseline commit: `9ded6d18e120c7a32843569c160760686d0b95d5`.

`TASK-FE-002-REPORT.md` was not present in the cloned repository, its Git history, or the supplied attachment directory. `architecture.md`, `AGENTS.md`, `plan.md`, the supplied TASK-FE-003 text, and the frontend/backend contracts were inspected before editing.

## Journey Data Foundation

- Added explicit TypeScript types for the complete `AdmissionJourney` contract in `frontend/src/types/journey.ts`: journey/diagnostic sections, recommendations, institution assessments, roadmap, and summary.
- Added `loadJourney(profileKey, options?)` in `frontend/src/lib/journey.ts`.
- The loader requests exactly one primary endpoint: `GET /api/v1/profiles/<key>/journey/?seed_order_start=1&seed_order_end=100`.
- Requests are cached by profile key, including the in-flight promise, so React StrictMode does not duplicate the initial fetch. Failed requests are evicted, retry forces a fresh request, and a successful profile save clears the journey cache.
- Added recursive runtime validation for the complete response and backend consistency invariants. Invalid data produces a safe UI error rather than an unsafe cast or raw response output.
- Added `useJourney()` for loading, retry, and navigation behavior shared by the Diagnostics route and suitable for later journey pages.
- Diagnostics reads `talap.localProfileKey` through a new non-creating helper. An absent key or structured `profile_not_found` response redirects to `/profile`.

## Diagnostics Experience

- Added a real desktop Diagnostics route, page hero, loading/error states, factual summary cards, contextual right panel, missing-information groups, explicit constraints, and CTA footer.
- Academic content shows raw GPA/scale, weighting, graduation year, class rank, and ordered SAT/ACT attempts without evaluation language.
- English attempts preserve backend order and keep TOEFL iBT 0-120 and 1-6 labels distinct.
- Study direction displays submitted CIP codes or explore interests.
- Financial context displays formatted USD budget and nullable aid need without affordability conclusions.
- Location content distinguishes preferred states, excluded states, and backend-provided hard constraints with `Source: Your profile`.
- Missing information is grouped by backend importance in required/useful/optional order while preserving backend order within each group.
- Display-only mappings cover study mode, GPA weighting, test scales, importance, and missing-information codes. No policy or diagnostic classification is recreated in TypeScript.

## Journey States And Navigation

- `profile_preparation`: Diagnostics remains visible, required information is prominent, recommendation availability is not claimed, and the primary CTA is `Complete your profile` -> `/profile`.
- `recommendations_ready`: the factual diagnostic renders and the primary CTA is `Continue to recommendations` -> `/recommendations`; no university cards are shown.
- `Edit profile` remains available in both states.
- On Diagnostics, Profile is explicitly completed, Diagnostics is current, and Recommendations/Compare/Roadmap remain future. Completion is supplied explicitly after a saved profile identity reaches the journey route, not inferred from route order.

## Tests And Quality Gates

The host did not provide an `npm` executable. The same package scripts were run with the bundled pnpm runtime after dependency installation; no manifest or lockfile was changed.

- Frontend tests: `.\\node_modules\\.bin\\vitest.cmd --run` - PASS, 4 files and 43 tests.
- Diagnostics coverage: saved-key load, exact journey scope, one initial request, absent-key redirect, `profile_not_found` redirect, safe generic error, retry, invalid response, both journey states, CTA routing, factual values, distinct TOEFL scales, SAT/ACT wording, CIP and explore modes, budget/aid, preferences/constraints, missing-information grouping/order/labels, explicit step states, and forbidden text.
- Lint: `pnpm run lint` (`eslint . --max-warnings 0`) - PASS, zero warnings.
- Build: `pnpm run build` (`tsc --noEmit && vite build`) - PASS; 1,900 modules transformed.
- `git diff --check` - PASS; only repository line-ending notices were emitted.
- Backend tests were not rerun because backend files and backend behavior were unchanged.

## Visual Review

- Reference screenshot available: No. No image file was present in the repository or supplied attachment directory.
- Browser visual inspection completed: No.
- Attempted viewport: 1440 x 900. The Vite server returned HTTP 200 from the host shell, but the only available in-app browser was isolated from the host loopback port and returned `ERR_CONNECTION_REFUSED` before the application rendered.
- 1720 x 900 was not attempted after the same browser connectivity blocker was confirmed.
- No screenshot-parity or overflow claim is made. Automated rendering, semantic content, and production build checks passed, but a human/browser visual pass remains outstanding.

## Data Protection And Claims

- Backend unchanged.
- `data/`, `.var/`, canonical files, source seeds, and applicant examples unchanged.
- No additional identity system, recommendation limit, LLM call, live collection, or secret was added.
- No readiness percentage, admission chance, competitiveness label, applicant strength, or unsupported diagnostic conclusion was invented.

## Files In The Task Delta

- `frontend/README.md`
- `frontend/src/app/App.tsx`
- `frontend/src/layouts/DesktopShell.tsx`
- `frontend/src/lib/journey.ts`
- `frontend/src/lib/journeyLabels.ts`
- `frontend/src/lib/profiles.ts`
- `frontend/src/pages/DiagnosticsPage.tsx`
- `frontend/src/pages/useJourney.ts`
- `frontend/src/styles/index.css`
- `frontend/src/test/app.test.tsx`
- `frontend/src/test/diagnostics.test.tsx`
- `frontend/src/test/journeyFixtures.ts`
- `frontend/src/test/profile.test.tsx`
- `frontend/src/test/profileFixtures.ts`
- `frontend/src/types/journey.ts`
- `TASK-FE-003-REPORT.md`

## Known FE-004 Limitations

- `/recommendations` is intentionally still a placeholder; the CTA only routes there.
- Recommendation and assessment contracts are typed and runtime-validated but intentionally not rendered in FE-003.
- Journey caching is in-memory and scoped to the frontend runtime; persistent progress/cache storage was not added.
- The requested desktop browser visual pass must be repeated in an environment where the browser can reach the local Vite port.
