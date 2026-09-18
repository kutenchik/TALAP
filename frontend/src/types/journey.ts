export type JourneyState = 'profile_preparation' | 'recommendations_ready';
export type MissingInformationImportance = 'required_for_next_step' | 'useful' | 'optional';
export type MissingInformationCode =
  | 'major_missing' | 'interests_missing' | 'graduation_year_missing' | 'gpa_missing'
  | 'class_rank_missing' | 'academic_test_scores_missing' | 'english_test_scores_missing'
  | 'annual_budget_missing';
export type TestType = 'sat' | 'act' | 'ielts' | 'toefl' | 'duolingo';
export type TestScale = 'sat_total_400_1600' | 'act_composite_1_36' | 'ielts_0_9'
  | 'toefl_ibt_0_120' | 'toefl_ibt_1_6' | 'det_10_160';

export interface GoalDiagnostic {
  mode: 'known_major' | 'explore';
  intended_cip_codes: string[];
  interests: string[];
  goal_supplied: boolean;
}

export interface GpaDiagnostic {
  state: 'provided' | 'missing';
  gpa_value: number | null;
  gpa_scale: number | null;
  gpa_weighting: 'weighted' | 'unweighted' | 'unknown';
}

export interface ClassRankDiagnostic {
  state: 'provided' | 'missing';
  class_rank: number | null;
  class_size: number | null;
}

export interface AcademicDiagnostic {
  graduation_year: number | null;
  gpa: GpaDiagnostic;
  class_rank: ClassRankDiagnostic;
}

export interface TestAttemptDiagnostic {
  test_type: TestType;
  scale: TestScale;
  score: number;
  taken_on: string | null;
}

export interface TestingDiagnostic {
  state: 'scores_provided' | 'no_scores_provided';
  attempts: TestAttemptDiagnostic[];
}

export type EnglishDiagnostic = TestingDiagnostic;

export interface FinancialDiagnostic {
  budget_state: 'budget_provided' | 'budget_missing';
  annual_budget_usd: number | null;
  needs_financial_aid: boolean | null;
}

export interface PreferenceDiagnostic {
  preferred_states: string[];
  excluded_states: string[];
}

export interface ExplicitConstraint {
  constraint_type: 'excluded_state';
  value: string;
  hard: true;
  source: 'applicant_profile';
}

export interface MissingInformation {
  code: MissingInformationCode;
  importance: MissingInformationImportance;
  message: string;
}

export interface ApplicantDiagnostic {
  profile_key: string;
  goal: GoalDiagnostic;
  academics: AcademicDiagnostic;
  testing: TestingDiagnostic;
  english: EnglishDiagnostic;
  financial: FinancialDiagnostic;
  preferences: PreferenceDiagnostic;
  explicit_constraints: ExplicitConstraint[];
  missing_information: MissingInformation[];
}

export interface InstitutionIdentity { ipeds_unitid: number; name: string; state: string }
export type PositionState = 'above_reported_context' | 'within_reported_context' | 'below_reported_context'
  | 'context_unavailable' | 'applicant_score_missing' | 'context_not_comparable';
export type EvidenceState = 'verified' | 'partial' | 'conflicting' | 'unavailable' | 'not_applicable';
export interface ReportedRange { scale: 'sat_total_400_1600' | 'act_composite_1_36'; lower: number; upper: number }
export interface AttemptPosition { scale: string; score: number; taken_on: string | null; state: PositionState }
export interface TestPosition { state: PositionState; context: ReportedRange | null; attempts: AttemptPosition[] }
export interface RawGpa { state: 'supplied_not_comparable' | 'missing'; gpa_value: number | null; gpa_scale: number | null; gpa_weighting: 'weighted' | 'unweighted' | 'unknown' }
export interface AcademicContext {
  snapshot_available: boolean; sat_context_available: boolean; act_context_available: boolean;
  data_year: string | null; source_data_year: string | null; term: string | null;
  source_url: string | null; source_locator: string | null; gpa: RawGpa; sat: TestPosition; act: TestPosition;
}
export interface EvidenceQuality { program: EvidenceState; english: EvidenceState; academic: EvidenceState }
export interface ApplicantConstraintAssessment { excluded_by_applicant: boolean; reasons: 'excluded_state'[] }
export interface CipEvidence { cip_code: string; state: 'observed' | 'not_observed' | 'unavailable'; academic_years: string[] }
export interface ProgramAssessment { state: 'one_or_more_observed' | 'none_observed' | 'unavailable' | 'not_evaluated_explore_mode'; requested_cips: CipEvidence[] }
export interface RequirementEvidence { scale: string; minimum_score: number; valid_for_tests_before: string | null; valid_for_tests_on_or_after: string | null; policy_cycle: string }
export interface SupportingAttempt { scale: string; score: number; taken_on: string | null }
export interface EnglishTestAssessment {
  test_type: 'ielts' | 'toefl' | 'duolingo';
  state: 'meets_verified_minimum' | 'below_verified_minimum' | 'no_minimum_published' | 'not_required'
    | 'no_matching_applicant_score' | 'requirement_not_found' | 'requirement_conflicting'
    | 'requirement_unavailable' | 'applicability_ambiguous' | 'no_applicable_requirement';
  requirements: RequirementEvidence[]; supporting_attempts: SupportingAttempt[]; conditional_policy_present: boolean;
}
export interface EnglishAssessment { policy_state: 'not_required' | 'no_minimum_published' | 'verified_minimum' | 'conflicting' | 'reviewed_not_found' | 'unavailable'; tests: EnglishTestAssessment[] }
export interface DataAvailability { program_data_available: boolean; english_data_available: boolean; admissions_context_available: boolean }
export interface InstitutionAssessment {
  seed_order: number; institution: InstitutionIdentity; applicant_constraints: ApplicantConstraintAssessment;
  program: ProgramAssessment; english: EnglishAssessment; data_availability: DataAvailability;
  academic: AcademicContext; evidence_quality: EvidenceQuality;
}

export type RecommendationState = 'recommended_for_review' | 'consider_with_actions' | 'insufficient_evidence' | 'excluded_by_applicant';
export type RecommendationActionCode = 'retake_or_improve_english_test' | 'submit_compatible_english_score'
  | 'verify_current_english_policy' | 'verify_program_availability' | 'research_financial_aid'
  | 'provide_missing_academic_test_if_desired';
export type RecommendationReasonCode = 'preferred_state' | 'excluded_state' | 'program_cip_observed'
  | 'program_evidence_partial' | 'program_evidence_unavailable' | 'program_not_evaluated_explore_mode'
  | 'english_minimum_met' | 'english_not_required' | 'english_no_minimum_published'
  | 'english_minimum_not_met' | 'english_score_missing' | 'english_policy_unavailable'
  | 'english_policy_not_found' | 'english_policy_conflicting' | 'english_applicability_unresolved'
  | 'english_conditional_policy_review_needed' | 'academic_above_reported_context'
  | 'academic_within_reported_context' | 'academic_below_reported_context'
  | 'academic_context_unavailable' | 'financial_review_needed' | 'sparse_data';
export interface RecommendationSignals {
  program: 'observed' | 'partial' | 'unavailable' | 'not_applicable';
  english: 'usable' | 'action_needed' | 'uncertain' | 'conflicting';
  academic: 'above_reported_context' | 'within_reported_context' | 'below_reported_context' | 'unavailable';
  preference: 'preferred_state' | 'neutral' | 'excluded_state'; financial: 'unavailable';
  data_quality: 'usable' | 'partial' | 'sparse' | 'conflicting';
}
export interface UniversityRecommendation {
  seed_order: number; institution: InstitutionIdentity; recommendation_state: RecommendationState;
  signals: RecommendationSignals; action_codes: RecommendationActionCode[];
  reason_codes: RecommendationReasonCode[]; assessment: InstitutionAssessment;
}
export interface RecommendationSet {
  profile_key: string; seed_order_start: number; seed_order_end: number; limit: number | null;
  applicant_financial_context: { annual_budget_usd: number | null; needs_financial_aid: boolean | null };
  recommendations: UniversityRecommendation[];
}

export type RoadmapState = 'profile_preparation' | 'university_actions' | 'no_blocking_actions';
export type RoadmapCategory = 'profile' | 'academics' | 'english' | 'program' | 'financial' | 'research';
export type RoadmapPriority = 'required' | 'high' | 'medium' | 'optional';
export type RoadmapScope = 'profile' | 'institutions';
export type RoadmapActionCode = 'define_intended_major' | 'provide_academic_interests' | 'provide_graduation_year'
  | 'provide_gpa' | 'provide_class_rank_if_available' | 'provide_academic_test_if_desired'
  | 'provide_english_test_score' | 'provide_annual_budget' | RecommendationActionCode;
export type RoadmapReasonCode = MissingInformationCode | Exclude<RecommendationReasonCode,
  'preferred_state' | 'excluded_state' | 'program_cip_observed' | 'program_not_evaluated_explore_mode'
  | 'english_minimum_met' | 'english_not_required' | 'english_no_minimum_published'
  | 'academic_above_reported_context' | 'academic_within_reported_context'
  | 'academic_below_reported_context' | 'sparse_data'>;
export interface RoadmapItem {
  action_code: RoadmapActionCode; category: RoadmapCategory; priority: RoadmapPriority;
  scope: RoadmapScope; institution_unitids: number[]; reason_codes: RoadmapReasonCode[];
}
export interface Roadmap {
  profile_key: string; roadmap_state: RoadmapState; seed_order_start: number; seed_order_end: number;
  recommendation_limit: number | null; items: RoadmapItem[];
}

export interface JourneySummary {
  candidate_count: number; recommended_for_review_count: number; consider_with_actions_count: number;
  insufficient_evidence_count: number; excluded_by_applicant_count: number; roadmap_item_count: number;
}

export interface AdmissionJourney {
  profile_key: string;
  journey_state: JourneyState;
  diagnostic: ApplicantDiagnostic;
  recommendations: RecommendationSet | null;
  roadmap: Roadmap;
  summary: JourneySummary;
}
