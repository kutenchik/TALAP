# Graph Report - talap3  (2026-09-19)

## Corpus Check
- 116 files · ~56,051 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1084 nodes · 2599 edges · 100 communities (52 shown, 30 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 184 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- import profile()
- app.py Module
- catalog/services.py Module
- OfficialSourcePipelineTests Module
- lib/journey.ts Module
- HttpApiTests Module
- types/journey.ts Module
- profile.test.tsx Module
- ApplicantProfileInput Module
- ComparePage.tsx Module
- enrich english requirements()
- ApplicantContractModel Module
- roadmap/services.py Module
- DiagnosticsPage.tsx Module
- views.py Module
- RecommendationsPage.tsx Module
- compilerOptions Module
- AdmissionsImportTests Module
- academic.py Module
- assessment/services.py Module
- profiles.ts Module
- fetch official sources()
- import ipeds()
- profileForm.ts Module
- is nonbinding score benchmark()
- AlemGemmaClient Module
- SeedInstitution Module
- Path Module
- source batches.py
- devDependencies Module
- App.tsx Module
- ValueError Module
- useProfile() Module
- ProgramImportTests Module
- Milestone E: Comparison and
- catalog/schemas.py Module
- Catalog Domain Model
- Desktop Profile Editor
- dependencies Module
- Recommendation Engine
- diagnose profile()
- export institutions()
- Validated Ingestion Pipeline
- useCompareSelection.ts Module
- Milestone D: Recommendation Engine
- Architect Executor Reviewer Workflow
- Canonical JSONL Dataset
- scripts Module
- alem.py Module
- parse llm response()
- package.json Module
- Milestone F: Django Web
- Personal Admission Journey Backend
- Task Report
- .success handler()
- ApplicantsConfig Module
- CatalogConfig Module
- @eslint/js Module
- eslint-plugin-react-hooks Module
- globals Module
- jsdom Module
- tailwindcss Module
- @tailwindcss/vite Module
- @testing-library/user-event Module
- @types/react Module
- typescript Module
- typescript-eslint Module
- @vitejs/plugin-react Module
- admission/applicants/ init .py
- applicants/migrations/0001 initial.py
- admission/assessment/ init .py
- catalog/migrations/0001 initial.py
- 0002 alter dataissue issue
- 0003 alter dataissue issue
- 0004 englishrequirement sourcedocument canonical
- 0005 task 004 fix
- 0006 englishrequirement source content
- llm/ init .py
- admission/recommendation/ init .py
- admission/roadmap/ init .py
- settings.py Module
- personal-admission-journey Module

## God Nodes (most connected - your core abstractions)
1. `OfficialSourcePipelineTests` - 84 edges
2. `ApplicantContractModel` - 51 edges
3. `enrich_english_requirements()` - 45 edges
4. `EnglishRequirementCandidate` - 40 edges
5. `import_profile()` - 39 edges
6. `validate_english_evidence()` - 38 edges
7. `FakeEnglishClient` - 29 edges
8. `ApplicantProfileInput` - 26 edges
9. `build_profile_diagnostic()` - 25 edges
10. `recommend_for_profile()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `Sequential Architect-Controlled Execution` --semantically_similar_to--> `Architect Executor Reviewer Workflow`  [INFERRED] [semantically similar]
  plan.md → AGENTS.md
- `Dataset Integrity Rules` --semantically_similar_to--> `Unknown as a First-Class State`  [INFERRED] [semantically similar]
  AGENTS.md → architecture.md
- `Deterministic Catalog Exports` --semantically_similar_to--> `Canonical JSONL Dataset`  [INFERRED] [semantically similar]
  AGENTS.md → architecture.md
- `Recommendation Safety Rules` --conceptually_related_to--> `Recommendation Engine`  [INFERRED]
  AGENTS.md → architecture.md
- `Diagnostics Experience` --semantically_similar_to--> `Recommendation Safety Rules`  [INFERRED] [semantically similar]
  frontend/README.md → AGENTS.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Architect-Controlled Task Handoff** — agents_architect_executor_reviewer_workflow, agents_one_task_per_run, agents_task_report, agents_delta_zip, agents_stop_rule, plan_sequential_architect_control [EXTRACTED 1.00]
- **Facts-to-Recommendations Pipeline** — architecture_facts_first_inference_second, architecture_provenance_domain_model, architecture_source_policy, architecture_ingestion_pipeline, architecture_recommendation_ready_contract, architecture_recommendation_engine [EXTRACTED 1.00]
- **Shared Frontend and Backend Journey Contract** — architecture_applicant_profile_architecture, architecture_django_http_layer, frontend_readme_profile_contract, frontend_readme_journey_contract, frontend_readme_diagnostics_experience [INFERRED 0.85]

## Communities (100 total, 30 thin omitted)

### Community 0 - "import profile()"
Cohesion: 0.06
Nodes (24): AdmissionJourney, import_profile(), atomic, assess_candidates(), build_admission_journey(), Run accepted services once and assemble one deterministic product result., MissingApplicantGoal, RecommendationSet (+16 more)

### Community 1 - "app.py Module"
Cohesion: 0.06
Nodes (56): command, ApplicantProfile, GpaWeighting, StudyMode, load_profile(), ApplicantProfileInput, Path, admissions_status_command() (+48 more)

### Community 2 - "catalog/services.py Module"
Cohesion: 0.09
Nodes (37): AdmissionSnapshot, DataIssue, EnglishRequirement, Institution, InstitutionAlias, IssueType, Meta, ProgramOffering (+29 more)

### Community 3 - "OfficialSourcePipelineTests Module"
Cohesion: 0.12
Nodes (10): EnglishRequirementCandidate, Gemma candidate only; evidence validation controls verified persistence., _mentions_candidate_english_test(), Accept only an explicit, unconditional English-test non-requirement., Evidence must be literal source content and substantiate the requested…, _supports_explicit_no_minimum(), _supports_explicit_not_required(), validate_english_evidence() (+2 more)

### Community 4 - "lib/journey.ts Module"
Cohesion: 0.12
Nodes (36): academicContext(), assessment(), attempt(), diagnostic(), evidenceStates, importanceValues, institution(), InvalidJourneyResponseError (+28 more)

### Community 5 - "HttpApiTests Module"
Cohesion: 0.10
Nodes (13): Client, extract_page(), ExtractedPage, FetchResult, Path, Bounded, cache-backed retrieval and deterministic HTML text extraction., Extract readable text while retaining table content whenever possible., Select deterministic local context rather than sending whole pages to a model. (+5 more)

### Community 6 - "types/journey.ts Module"
Cohesion: 0.06
Nodes (35): AcademicContext, AcademicDiagnostic, ApplicantConstraintAssessment, AttemptPosition, CipEvidence, ClassRankDiagnostic, DataAvailability, EnglishDiagnostic (+27 more)

### Community 7 - "profile.test.tsx Module"
Cohesion: 0.14
Nodes (20): App(), clearJourneyCache(), LOCAL_PROFILE_KEY, COMPARE_STORAGE_KEY, setup(), mockJourney(), diagnosticFixture(), preparationJourneyFixture() (+12 more)

### Community 8 - "ApplicantProfileInput Module"
Cohesion: 0.14
Nodes (15): AcademicsInput, ApplicantProfileInput, FinancialInput, _normalise_ordered(), PreferencesInput, field_validator, StudyIntentInput, export_profile() (+7 more)

### Community 9 - "ComparePage.tsx Module"
Cohesion: 0.10
Nodes (24): scaleLabel(), UniversityRecommendationCard(), testTypeFallbackLabels, academicLabels, actionLabels, englishLabels, policyLabels, programLabels (+16 more)

### Community 10 - "enrich english requirements()"
Cohesion: 0.18
Nodes (5): build_english_prompt(), enrich_english_requirements(), export_english_requirements(), Turn bounded source text into verified facts only after deterministic…, FakeEnglishClient

### Community 11 - "ApplicantContractModel Module"
Cohesion: 0.15
Nodes (23): SimpleTestCase, AcademicDiagnostic, _attempt(), build_profile_diagnostic(), ClassRankDiagnostic, EnglishDiagnostic, ExplicitConstraint, FinancialDiagnostic (+15 more)

### Community 12 - "roadmap/services.py Module"
Cohesion: 0.16
Nodes (18): ApplicantDiagnostic, Roadmap, RoadmapItem, ApplicantDiagnostic, End-to-end, non-persistent admission journey orchestration., AdmissionJourney, JourneySummary, Application-service orchestration for the complete backend journey. (+10 more)

### Community 13 - "DiagnosticsPage.tsx Module"
Cohesion: 0.12
Nodes (17): importanceLabels, missingInformationLabels, studyModeLabels, testScaleLabels, weightingLabels, Attempts(), budgetFormatter, dateText() (+9 more)

### Community 14 - "views.py Module"
Cohesion: 0.27
Nodes (20): Any, HttpRequest, JsonResponse, Versioned plain-Django JSON transport for accepted application services., csrf(), _error(), get_diagnostic(), get_journey() (+12 more)

### Community 15 - "RecommendationsPage.tsx Module"
Cohesion: 0.20
Nodes (16): JourneyStepper(), Badge(), Button(), Card(), EmptyState(), ErrorState(), Field(), FieldControl (+8 more)

### Community 16 - "compilerOptions Module"
Cohesion: 0.09
Nodes (22): compilerOptions, esModuleInterop, jsx, lib, module, moduleResolution, noUnusedLocals, noUnusedParameters (+14 more)

### Community 18 - "academic.py Module"
Cohesion: 0.15
Nodes (19): parametrize, ApplicantTestScoreInput, academic_evidence(), AcademicContext, AttemptPosition, build_academic_context(), position_attempts(), ApplicantProfileInput (+11 more)

### Community 19 - "assessment/services.py Module"
Cohesion: 0.23
Nodes (19): EnglishTestAssessment, EvidenceQuality, ApplicantConstraintAssessment, CandidateAssessmentSet, CipEvidence, DataAvailability, EnglishAssessment, EnglishTestAssessment (+11 more)

### Community 20 - "profiles.ts Module"
Cohesion: 0.22
Nodes (14): ApiError, createApiClient(), request(), url(), getLocalProfileKey(), loadLocalProfile(), readLocalProfileKey(), saveProfile() (+6 more)

### Community 21 - "fetch official sources()"
Cohesion: 0.16
Nodes (3): _allowed_final_host(), fetch_official_sources(), Fetch a reviewed pilot subset while persisting only metadata/provenance in the…

### Community 22 - "import ipeds()"
Cohesion: 0.25
Nodes (15): exact_state_matches(), fuzzy_candidates(), is_bachelors_granting(), normalize_name(), ownership_from_control(), Pure deterministic matching helpers for seed-to-IPEDS resolution., Return suggestions only; callers must never resolve based on this result., IpedInstitutionRecord (+7 more)

### Community 23 - "profileForm.ts Module"
Cohesion: 0.23
Nodes (13): optionalNumber(), optionalText(), ProfileDraft, states(), testOptions, TestRow, text(), toDraft() (+5 more)

### Community 24 - "is nonbinding score benchmark()"
Cohesion: 0.15
Nodes (14): Match, _date_markers(), _evidence_span(), _has_nonbinding_score_group_language(), _is_nonbinding_score_benchmark(), _normalised_text(), Locate complete numeric tokens that exactly equal the candidate score. Decimal…, Find literal evidence while allowing only whitespace representation differences. (+6 more)

### Community 25 - "AlemGemmaClient Module"
Cohesion: 0.15
Nodes (7): OpenAI, RuntimeError, AlemGemmaClient, LLMUnavailable, Explicit runtime placeholder that lets a batch record review issues per source., Thin dependency-injectable boundary around the OpenAI-compatible SDK., UnavailableEnglishClient

### Community 26 - "SeedInstitution Module"
Cohesion: 0.19
Nodes (14): The reviewable 100-entry cohort and its explicit resolution state., SeedInstitution, _completion_record(), import_bachelors_programs(), _is_ipeds_summary_cip_code(), load_cip_titles(), _normalize_cip_code(), Upsert a review item without making different reviewed URLs collide. (+6 more)

### Community 27 - "Path Module"
Cohesion: 0.21
Nodes (13): OfficialSourceSeed, Reviewable official-page seed; search is only recorded as URL discovery., discover_official_sources(), export_admissions(), export_programs(), export_sources(), load_official_source_seeds(), load_seed_manifest() (+5 more)

### Community 28 - "source batches.py"
Cohesion: 0.22
Nodes (10): export_source_gaps(), Path, Offline seed-order selection and audit of the curated English source list., Require every inclusive seed order to resolve to a distinct institution., Audit reviewed seeds locally; list membership is TASK-004's active contract.…, resolve_source_selection(), select_seed_batch(), source_gap_rows() (+2 more)

### Community 29 - "devDependencies Module"
Cohesion: 0.15
Nodes (13): eslint, devDependencies, eslint, @testing-library/jest-dom, @testing-library/react, @types/react-dom, vite, vitest (+5 more)

### Community 30 - "App.tsx Module"
Cohesion: 0.22
Nodes (9): DiagnosticsRoute(), JourneyStep, journeySteps, ComparePage(), DiagnosticsContextPanel(), DiagnosticsPage(), PlaceholderPage(), RecommendationsPage() (+1 more)

### Community 31 - "ValueError Module"
Cohesion: 0.21
Nodes (6): model_validator, model_validator, model_validator, Mirror the accepted service boundary for the no-recommendation branch., _validate_scope(), ValueError

### Community 32 - "useProfile() Module"
Cohesion: 0.29
Nodes (11): emptyDraft(), textRow, ProfilePage(), edit(), input(), repeatable(), replace(), update() (+3 more)

### Community 34 - "Milestone E: Comparison and"
Cohesion: 0.18
Nodes (11): Recommendation Safety Rules, Diagnostics Experience, Admission Journey Frontend Contract, Journey Route Scope, Milestone B: Applicant Profile and Diagnostic, Milestone E: Comparison and Journey, Task 016: Applicant Profile Schema and Persistence, Task 018: Diagnostic Service (+3 more)

### Community 35 - "catalog/schemas.py Module"
Cohesion: 0.31
Nodes (7): EnglishExtractionResponse, IpedAdmissionsRecord, IpedBachelorCompletionRecord, BaseModel, field_validator, SeedManifest, SeedManifestEntry

### Community 36 - "Catalog Domain Model"
Cohesion: 0.25
Nodes (9): Dataset Integrity Rules, Catalog Domain Model, Program Discovery, Provenance as Domain Data, Recommendation-Ready Contract, Official Source Policy, Unknown as a First-Class State, Milestone A: Recommendation-Ready Catalog (+1 more)

### Community 37 - "Desktop Profile Editor"
Cohesion: 0.22
Nodes (9): Applicant Profile Architecture, Talap HTML Entrypoint, CSRF-Safe API Transport, Desktop Profile Editor, Frontend Quality Gates, Local Development Profile Identity, Applicant Profile Frontend Contract, Profile Validation and Save Workflow (+1 more)

### Community 38 - "dependencies Module"
Cohesion: 0.22
Nodes (9): dependencies, lucide-react, react, react-dom, react-router-dom, lucide-react, react, react-dom (+1 more)

### Community 39 - "Recommendation Engine"
Cohesion: 0.25
Nodes (8): Deterministic Core with Optional LLM, Deterministic Next Action, Inspectable Fit Dimensions, Hard Eligibility and Exclusion, Recommendation Diversification, Recommendation Engine, Rule-Based Roadmap, Structured Recommendation Explanations

### Community 40 - "diagnose profile()"
Cohesion: 0.29
Nodes (6): diagnose_profile(), ApplicantTestScore, Meta, TestType, TestCase, StoredApplicantDiagnosticTests

### Community 41 - "export institutions()"
Cohesion: 0.36
Nodes (4): export_institutions(), ImportExportTests, Path, TestCase

### Community 42 - "Validated Ingestion Pipeline"
Cohesion: 0.33
Nodes (7): LLM Candidate Extraction, Alem Gemma4 Adapter, Validated Ingestion Pipeline, Security and Privacy, Milestone C: Program Discovery, Task 019: Program-Family Matching, Task 020: Gemma Interest Interpretation

### Community 43 - "useCompareSelection.ts Module"
Cohesion: 0.38
Nodes (6): CompareResults(), RecommendationResults(), eligibleUnitids(), useCompareSelection(), toggle(), UniversityRecommendation

### Community 44 - "Milestone D: Recommendation Engine"
Cohesion: 0.29
Nodes (7): Milestone D: Recommendation Engine, Task 021: Candidate Generation and Eligibility, Task 022: Academic and English Fit, Task 023: Financial Fit, Task 024: Program Preference Fit and Ordering, Task 025: Recommendation Diversification, Task 026: Explainable Recommendation Output

### Community 45 - "Architect Executor Reviewer Workflow"
Cohesion: 0.33
Nodes (6): Architect Executor Reviewer Workflow, Executor Rules, One Task per Run, Stop Rule, Personal Admission Journey Execution Plan, Sequential Architect-Controlled Execution

### Community 46 - "Canonical JSONL Dataset"
Cohesion: 0.40
Nodes (6): Deterministic Catalog Exports, Canonical JSONL Dataset, CLI Transport, Django HTTP Layer, Django ORM Runtime Persistence, One Data Model, Multiple Transports

### Community 47 - "scripts Module"
Cohesion: 0.33
Nodes (6): scripts, build, dev, lint, preview, test

### Community 48 - "alem.py Module"
Cohesion: 0.33
Nodes (3): Protocol, EnglishExtractionClient, Alem's OpenAI-compatible Gemma adapter.

### Community 49 - "parse llm response()"
Cohesion: 0.40
Nodes (3): _normalise_llm_json_response(), _parse_llm_response(), Accept raw JSON or one complete JSON/generic Markdown fence, and nothing around…

### Community 50 - "package.json Module"
Cohesion: 0.40
Nodes (4): name, private, type, version

### Community 51 - "Milestone F: Django Web"
Cohesion: 0.40
Nodes (5): Milestone F: Django Web Backend, Task 032: Profile and Diagnostic API, Task 033: Recommendation and Comparison API, Task 034: Roadmap and Progress API, Task 035: Web Error-State Hardening

### Community 52 - "Personal Admission Journey Backend"
Cohesion: 0.67
Nodes (3): Architectural Constraints, Facts First, Inference Second, Personal Admission Journey Backend Architecture

### Community 53 - "Task Report"
Cohesion: 0.67
Nodes (3): Delta ZIP, Targeted Testing Policy, Task Report

## Knowledge Gaps
- **139 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+134 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 343 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `enrich_english_requirements()` connect `enrich english requirements()` to `app.py Module`, `catalog/services.py Module`, `OfficialSourcePipelineTests Module`, `HttpApiTests Module`, `alem.py Module`, `parse llm response()`, `fetch official sources()`, `AlemGemmaClient Module`, `SeedInstitution Module`, `Path Module`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `ApplicantProfile` connect `app.py Module` to `import profile()`, `HttpApiTests Module`, `ApplicantProfileInput Module`, `diagnose profile()`, `views.py Module`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `OfficialSourcePipelineTests` connect `OfficialSourcePipelineTests Module` to `HttpApiTests Module`, `enrich english requirements()`, `alem.py Module`, `parse llm response()`, `fetch official sources()`, `.success handler()`, `AlemGemmaClient Module`, `Path Module`, `source batches.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `OfficialSourcePipelineTests` (e.g. with `WebFetcher` and `AlemGemmaClient`) actually correct?**
  _`OfficialSourcePipelineTests` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `enrich_english_requirements()` (e.g. with `DataIssue` and `EnglishRequirement`) actually correct?**
  _`enrich_english_requirements()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `EnglishRequirementCandidate` (e.g. with `_is_nonbinding_score_benchmark()` and `_mentions_candidate_english_test()`) actually correct?**
  _`EnglishRequirementCandidate` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `import_profile()` (e.g. with `ApplicantProfile` and `ApplicantTestScore`) actually correct?**
  _`import_profile()` has 3 INFERRED edges - model-reasoned connections that need verification._