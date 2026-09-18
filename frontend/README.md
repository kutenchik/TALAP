# Talap frontend

Desktop profile editor for international applicants to U.S. bachelor’s programs. Node.js 24.16+ and npm 11 are the verified frontend runtime. Use the existing Python virtual environment for Django.

## Local development

From `frontend/`:

```powershell
npm ci
npm run dev
```

The API defaults to `/api/v1`. The Vite dev proxy forwards `/api/` to Django at `http://127.0.0.1:8000`, preserving Host and Origin so Django’s same-origin CSRF checks remain effective.

The existing backend settings have DEBUG=False and no ALLOWED_HOSTS configured. For a loopback-only development session, run this from the repository root (the override affects only this process; backend settings files are not edited):

```powershell
.\.venv\Scripts\python.exe -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); from django.conf import settings; settings.ALLOWED_HOSTS=['127.0.0.1','localhost']; from django.core.management import execute_from_command_line; execute_from_command_line(['manage.py','runserver','127.0.0.1:8000','--noreload'])"
```

If Windows reserves port 8000, use another free loopback port, such as 18000, in the Django command. In the frontend terminal set the server-only proxy override before starting Vite:

```powershell
$env:TALAP_DEV_API_TARGET = 'http://127.0.0.1:18000'
npm run dev -- --host 127.0.0.1
```

For an isolated smoke test, set `ADMISSION_DB_PATH` to a temporary SQLite path in the backend terminal and run `python manage.py migrate --noinput` before starting Django. Do not point smoke tests at an existing applicant example or imported catalog database.

```powershell
npm test -- --run
npm run lint
npm run build
npm run preview
```

Production hosting must serve `dist/`, fall back to `index.html` for SPA routes, and provide a same-origin API reverse proxy. Vite's development proxy is not production hosting. No deployment configuration or authentication is provided by this task.

## Profile contract and behavior

`src/types/profile.ts` mirrors `admission.applicants.schemas.ApplicantProfileInput`, using numeric JSON scores/GPA/budget and explicit nullable values. The normalized validate/save/get response has the same shape. `src/lib/profileForm.ts` only translates input strings, empty values, and ordered rows to/from that contract. It does not validate score ranges, convert scales, infer CIP codes, choose best scores, or evaluate financial fit.

Supported sections: display name/country codes/graduation year; known-major CIP codes or ordered explore interests; GPA value and arbitrary scale/weighting/optional rank; zero or more ordered test attempts with dates and notes; annual USD budget and nullable aid need; preferred/excluded U.S. states. TOEFL 0–120 and 1–6 are explicit separate choices. Country/state text is presented in uppercase. Optional numeric blanks become null; zero and false remain distinct from unknown. Added repeated rows must be filled or removed. No applicant values are prepopulated.

`localStorage` identifies the local development profile only. The key is `talap.localProfileKey`, with value `talap-local-` plus `crypto.randomUUID()`. It is not authentication or authorization. No profile contents or CSRF tokens are saved to browser storage. Existing keys are loaded through GET `/profiles/<key>/`; only a 404 `profile_not_found` response opens a fresh form with the same key. Storage/load failures display a retry state. Clearing storage creates a new local identity on the next visit; browser origins have separate storage.

Saving calls GET `/csrf/`, POST `/profiles/validate/`, and then POST `/profiles/` with the backend-normalized validation response. Only successful save navigates to `/diagnostics`. A synchronous in-flight guard blocks duplicate submissions and the form is disabled while saving. Errors preserve edits and focus a role=alert summary. Backend validation locations map to field descriptions or associated group messages; unrecognized locations remain in the summary. Other errors use safe generic text, including non-JSON middleware errors.

Journey links to other steps are disabled while edits are unsaved or saving. A beforeunload handler also requests the browser’s normal leave-page warning. This is a small development guard, not a full SPA history blocker. No progress is inferred from route visits; Diagnostics explicitly marks Profile complete only after a saved profile identity reaches the journey endpoint.

## Journey and Diagnostics

`src/types/journey.ts` mirrors the complete `AdmissionJourney` response, including diagnostics, recommendations, roadmap, and summary contracts for later frontend tasks. `loadJourney()` requests GET `/profiles/<key>/journey/?seed_order_start=1&seed_order_end=100`, validates the response shape, and shares one in-flight/cached promise per profile key. Failed requests are evicted so the page retry can request fresh data. Diagnostics reads, but never creates, `talap.localProfileKey`; an absent key or `profile_not_found` redirects to Profile.

`/diagnostics` renders backend-supplied facts only: academics, ordered test attempts and distinct TOEFL scales, study direction, financial context, preferences, explicit excluded-state constraints, and missing information grouped by the backend importance value. `profile_preparation` keeps the user on a Profile completion path; `recommendations_ready` offers the route to Recommendations. No university evaluation, score, percentage, or inferred applicant strength is produced in the browser.

## CSRF and API

`createApiClient()` reads `VITE_API_BASE_URL`, defaulting to `/api/v1`. `.env.example` documents this public, build-time setting; never put secrets in Vite variables. GET/POST helpers are typed transports, not runtime profile-schema validators. Request cancellation uses AbortSignal; structured HTTP errors are retained without displaying raw server bodies.

The new transport-only Django GET `/api/v1/csrf/` calls `django.middleware.csrf.get_token(request)`, returns `{csrfToken}`, allows middleware to issue its normal cookie, and sends `Cache-Control: no-store`. It performs no database writes. With CSRF requirements satisfied, unsupported methods return the existing 405 JSON `method_not_allowed` envelope. Unsafe requests lacking CSRF can still be rejected with 403 by middleware before method dispatch; no exemption was added.

The browser uses `credentials: same-origin` and sends `X-CSRFToken` for both POSTs. A new token is requested on each save attempt, including retries. Backend CORS/CSRF policy, domain validation, persistence services, and security settings are unchanged. Cross-origin API deployment is outside this development flow.

## Design and scope

The accepted Talap shell, temporary replaceable compass wordmark, tokens, system fonts, and primitives remain in use. The profile uses labeled two-column desktop sections, keyboard-accessible native radio choices, repeatable field rows, an accessible error summary, and a right-aligned gradient CTA. The right panel explains profile inputs and local development identity. Styling is centralized in `src/styles/index.css`; no new dependencies were added.

`/` redirects to `/profile`. `/diagnostics` is the real desktop diagnostic experience; `/recommendations`, `/compare`, and `/roadmap` remain placeholders for later tasks. The layout targets 1280px and wider and scrolls vertically for long content. No mobile, accounts, favorites, university search, major inference, admission chances, or recommendation cards were added.

## Verification

Vitest + Testing Library + jsdom tests use mocked fetch, including an in-memory profile server to verify save and reload. Backend API tests exercise real Django CSRF middleware and persistence in the test database. Normal tests need no external services. Strict TypeScript and ESLint remain the existing quality gates.
