import { ApiError, createApiClient } from './api';
import type { AdmissionJourney, ApplicantDiagnostic, JourneySummary, RecommendationSet, Roadmap } from '../types/journey';

export class InvalidJourneyResponseError extends Error {
  constructor() {
    super('The journey response did not match the expected contract.');
    this.name = 'InvalidJourneyResponseError';
  }
}

const requests = new Map<string, Promise<AdmissionJourney>>();
export type JourneyLoadState =
  | { status: 'loading' }
  | { status: 'ready'; journey: AdmissionJourney }
  | { status: 'error'; message: string; profileMissing?: boolean };
export interface JourneySnapshot { savedProfile: boolean; state: JourneyLoadState; started: boolean }
const emptySnapshot: JourneySnapshot = { savedProfile: false, state: { status: 'loading' }, started: false };
const snapshots = new Map<string, JourneySnapshot>();
const listeners = new Set<() => void>();

export function subscribeJourney(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function getJourneySnapshot(profileKey: string | null): JourneySnapshot {
  return profileKey ? snapshots.get(profileKey) ?? emptySnapshot : emptySnapshot;
}
function publish(profileKey: string, snapshot: JourneySnapshot) {
  snapshots.set(profileKey, snapshot);
  listeners.forEach(listener => listener());
}
export function markProfileSaved(profileKey: string) {
  publish(profileKey, { ...getJourneySnapshot(profileKey), savedProfile: true });
}
const missingCodes = new Set([
  'major_missing', 'interests_missing', 'graduation_year_missing', 'gpa_missing',
  'class_rank_missing', 'academic_test_scores_missing', 'english_test_scores_missing',
  'annual_budget_missing',
]);
const importanceValues = new Set(['required_for_next_step', 'useful', 'optional']);
const testTypes = new Set(['sat', 'act', 'ielts', 'toefl', 'duolingo']);
const testScales = new Set([
  'sat_total_400_1600', 'act_composite_1_36', 'ielts_0_9',
  'toefl_ibt_0_120', 'toefl_ibt_1_6', 'det_10_160',
]);
const positionStates = new Set(['above_reported_context', 'within_reported_context', 'below_reported_context', 'context_unavailable', 'applicant_score_missing', 'context_not_comparable']);
const evidenceStates = new Set(['verified', 'partial', 'conflicting', 'unavailable', 'not_applicable']);
const recommendationStates = new Set(['recommended_for_review', 'consider_with_actions', 'insufficient_evidence', 'excluded_by_applicant']);
const recommendationActions = new Set(['retake_or_improve_english_test', 'submit_compatible_english_score', 'verify_current_english_policy', 'verify_program_availability', 'research_financial_aid', 'provide_missing_academic_test_if_desired']);
const recommendationReasons = new Set([
  'preferred_state', 'excluded_state', 'program_cip_observed', 'program_evidence_partial',
  'program_evidence_unavailable', 'program_not_evaluated_explore_mode', 'english_minimum_met',
  'english_not_required', 'english_no_minimum_published', 'english_minimum_not_met',
  'english_score_missing', 'english_policy_unavailable', 'english_policy_not_found',
  'english_policy_conflicting', 'english_applicability_unresolved', 'english_conditional_policy_review_needed',
  'academic_above_reported_context', 'academic_within_reported_context', 'academic_below_reported_context',
  'academic_context_unavailable', 'financial_review_needed', 'sparse_data',
]);
const roadmapActions = new Set([
  'define_intended_major', 'provide_academic_interests', 'provide_graduation_year', 'provide_gpa',
  'provide_class_rank_if_available', 'provide_academic_test_if_desired', 'provide_english_test_score',
  'provide_annual_budget', ...recommendationActions,
]);
const roadmapReasons = new Set([...missingCodes, ...recommendationReasons]);

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}
function nullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value));
}
function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}
function nullableBoolean(value: unknown): value is boolean | null {
  return value === null || typeof value === 'boolean';
}
function numberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(item => typeof item === 'number' && Number.isFinite(item));
}
function valuesIn(value: unknown, allowed: Set<string>): value is string[] {
  return strings(value) && value.every(item => allowed.has(item));
}
function attempt(value: unknown): boolean {
  return record(value)
    && testTypes.has(String(value.test_type))
    && testScales.has(String(value.scale))
    && typeof value.score === 'number' && Number.isFinite(value.score)
    && nullableString(value.taken_on);
}
function diagnostic(value: unknown): value is ApplicantDiagnostic {
  if (!record(value) || typeof value.profile_key !== 'string') return false;
  const goal = value.goal;
  const academics = value.academics;
  const testing = value.testing;
  const english = value.english;
  const financial = value.financial;
  const preferences = value.preferences;
  if (!record(goal) || !['known_major', 'explore'].includes(String(goal.mode))
    || !strings(goal.intended_cip_codes) || !strings(goal.interests) || typeof goal.goal_supplied !== 'boolean') return false;
  if (!record(academics) || !nullableNumber(academics.graduation_year)
    || !record(academics.gpa) || !['provided', 'missing'].includes(String(academics.gpa.state))
    || !nullableNumber(academics.gpa.gpa_value) || !nullableNumber(academics.gpa.gpa_scale)
    || !['weighted', 'unweighted', 'unknown'].includes(String(academics.gpa.gpa_weighting))
    || !record(academics.class_rank) || !['provided', 'missing'].includes(String(academics.class_rank.state))
    || !nullableNumber(academics.class_rank.class_rank) || !nullableNumber(academics.class_rank.class_size)) return false;
  if (!record(testing) || !['scores_provided', 'no_scores_provided'].includes(String(testing.state))
    || !Array.isArray(testing.attempts) || !testing.attempts.every(attempt)) return false;
  if (!record(english) || !['scores_provided', 'no_scores_provided'].includes(String(english.state))
    || !Array.isArray(english.attempts) || !english.attempts.every(attempt)) return false;
  if (!record(financial) || !['budget_provided', 'budget_missing'].includes(String(financial.budget_state))
    || !nullableNumber(financial.annual_budget_usd) || !nullableBoolean(financial.needs_financial_aid)) return false;
  if (!record(preferences) || !strings(preferences.preferred_states) || !strings(preferences.excluded_states)) return false;
  if (!Array.isArray(value.explicit_constraints) || !value.explicit_constraints.every(item => record(item)
    && item.constraint_type === 'excluded_state' && typeof item.value === 'string'
    && item.hard === true && item.source === 'applicant_profile')) return false;
  return Array.isArray(value.missing_information) && value.missing_information.every(item => record(item)
    && missingCodes.has(String(item.code)) && importanceValues.has(String(item.importance))
    && typeof item.message === 'string');
}
function institution(value: unknown): boolean {
  return record(value) && typeof value.ipeds_unitid === 'number' && Number.isInteger(value.ipeds_unitid)
    && typeof value.name === 'string' && typeof value.state === 'string';
}
function reportedRange(value: unknown): boolean {
  return record(value) && ['sat_total_400_1600', 'act_composite_1_36'].includes(String(value.scale))
    && typeof value.lower === 'number' && typeof value.upper === 'number';
}
function positionedAttempt(value: unknown): boolean {
  return record(value) && typeof value.scale === 'string' && typeof value.score === 'number'
    && nullableString(value.taken_on) && positionStates.has(String(value.state));
}
function testPosition(value: unknown): boolean {
  return record(value) && positionStates.has(String(value.state))
    && (value.context === null || reportedRange(value.context))
    && Array.isArray(value.attempts) && value.attempts.every(positionedAttempt);
}
function academicContext(value: unknown): boolean {
  return record(value) && typeof value.snapshot_available === 'boolean'
    && typeof value.sat_context_available === 'boolean' && typeof value.act_context_available === 'boolean'
    && nullableString(value.data_year) && nullableString(value.source_data_year) && nullableString(value.term)
    && nullableString(value.source_url) && nullableString(value.source_locator)
    && record(value.gpa) && ['supplied_not_comparable', 'missing'].includes(String(value.gpa.state))
    && nullableNumber(value.gpa.gpa_value) && nullableNumber(value.gpa.gpa_scale)
    && ['weighted', 'unweighted', 'unknown'].includes(String(value.gpa.gpa_weighting))
    && testPosition(value.sat) && testPosition(value.act);
}
function requirement(value: unknown): boolean {
  return record(value) && typeof value.scale === 'string' && typeof value.minimum_score === 'number'
    && nullableString(value.valid_for_tests_before) && nullableString(value.valid_for_tests_on_or_after)
    && typeof value.policy_cycle === 'string';
}
function supportingAttempt(value: unknown): boolean {
  return record(value) && typeof value.scale === 'string' && typeof value.score === 'number' && nullableString(value.taken_on);
}
function assessment(value: unknown): boolean {
  if (!record(value)) return false;
  const dataAvailability = value.data_availability;
  const evidenceQuality = value.evidence_quality;
  if (typeof value.seed_order !== 'number' || !institution(value.institution)
    || !record(value.applicant_constraints) || typeof value.applicant_constraints.excluded_by_applicant !== 'boolean'
    || !valuesIn(value.applicant_constraints.reasons, new Set(['excluded_state']))
    || !record(value.program) || !['one_or_more_observed', 'none_observed', 'unavailable', 'not_evaluated_explore_mode'].includes(String(value.program.state))
    || !Array.isArray(value.program.requested_cips) || !value.program.requested_cips.every(item => record(item)
      && typeof item.cip_code === 'string' && ['observed', 'not_observed', 'unavailable'].includes(String(item.state)) && strings(item.academic_years))
    || !record(value.english) || !['not_required', 'no_minimum_published', 'verified_minimum', 'conflicting', 'reviewed_not_found', 'unavailable'].includes(String(value.english.policy_state))
    || !Array.isArray(value.english.tests) || !value.english.tests.every(test => record(test)
      && ['ielts', 'toefl', 'duolingo'].includes(String(test.test_type))
      && ['meets_verified_minimum', 'below_verified_minimum', 'no_minimum_published', 'not_required', 'no_matching_applicant_score', 'requirement_not_found', 'requirement_conflicting', 'requirement_unavailable', 'applicability_ambiguous', 'no_applicable_requirement'].includes(String(test.state))
      && Array.isArray(test.requirements) && test.requirements.every(requirement)
      && Array.isArray(test.supporting_attempts) && test.supporting_attempts.every(supportingAttempt)
      && typeof test.conditional_policy_present === 'boolean')
    || !record(dataAvailability) || !['program_data_available', 'english_data_available', 'admissions_context_available'].every(key => typeof dataAvailability[key] === 'boolean')
    || !academicContext(value.academic) || !record(evidenceQuality)) return false;
  return ['program', 'english', 'academic'].every(key => evidenceStates.has(String(evidenceQuality[key])));
}
function recommendation(value: unknown): boolean {
  if (!record(value) || typeof value.seed_order !== 'number' || !institution(value.institution)
    || !recommendationStates.has(String(value.recommendation_state)) || !record(value.signals)
    || !valuesIn(value.action_codes, recommendationActions) || !valuesIn(value.reason_codes, recommendationReasons)
    || !assessment(value.assessment)) return false;
  return ['observed', 'partial', 'unavailable', 'not_applicable'].includes(String(value.signals.program))
    && ['usable', 'action_needed', 'uncertain', 'conflicting'].includes(String(value.signals.english))
    && ['above_reported_context', 'within_reported_context', 'below_reported_context', 'unavailable'].includes(String(value.signals.academic))
    && ['preferred_state', 'neutral', 'excluded_state'].includes(String(value.signals.preference))
    && value.signals.financial === 'unavailable'
    && ['usable', 'partial', 'sparse', 'conflicting'].includes(String(value.signals.data_quality));
}
function roadmap(value: unknown): value is Roadmap {
  return record(value) && typeof value.profile_key === 'string'
    && ['profile_preparation', 'university_actions', 'no_blocking_actions'].includes(String(value.roadmap_state))
    && typeof value.seed_order_start === 'number' && typeof value.seed_order_end === 'number'
    && nullableNumber(value.recommendation_limit) && Array.isArray(value.items)
    && value.items.every(item => record(item) && roadmapActions.has(String(item.action_code))
      && ['profile', 'academics', 'english', 'program', 'financial', 'research'].includes(String(item.category))
      && ['required', 'high', 'medium', 'optional'].includes(String(item.priority))
      && ['profile', 'institutions'].includes(String(item.scope))
      && numberArray(item.institution_unitids) && valuesIn(item.reason_codes, roadmapReasons));
}
function summary(value: unknown): value is JourneySummary {
  if (!record(value)) return false;
  return ['candidate_count', 'recommended_for_review_count', 'consider_with_actions_count',
    'insufficient_evidence_count', 'excluded_by_applicant_count', 'roadmap_item_count']
    .every(key => typeof value[key] === 'number' && Number.isInteger(value[key]) && value[key] >= 0);
}
function recommendations(value: unknown): value is RecommendationSet {
  return record(value) && typeof value.profile_key === 'string'
    && typeof value.seed_order_start === 'number' && typeof value.seed_order_end === 'number'
    && nullableNumber(value.limit) && record(value.applicant_financial_context)
    && nullableNumber(value.applicant_financial_context.annual_budget_usd)
    && nullableBoolean(value.applicant_financial_context.needs_financial_aid)
    && Array.isArray(value.recommendations) && value.recommendations.every(recommendation);
}

export function readAdmissionJourney(value: unknown): AdmissionJourney {
  if (!record(value) || typeof value.profile_key !== 'string'
    || !['profile_preparation', 'recommendations_ready'].includes(String(value.journey_state))
    || !diagnostic(value.diagnostic) || !roadmap(value.roadmap) || !summary(value.summary)
    || (value.recommendations !== null && !recommendations(value.recommendations))) {
    throw new InvalidJourneyResponseError();
  }
  const stateTotal = value.summary.recommended_for_review_count + value.summary.consider_with_actions_count
    + value.summary.insufficient_evidence_count + value.summary.excluded_by_applicant_count;
  if (value.diagnostic.profile_key !== value.profile_key || value.roadmap.profile_key !== value.profile_key
    || stateTotal !== value.summary.candidate_count || value.summary.roadmap_item_count !== value.roadmap.items.length
    || (value.journey_state === 'profile_preparation' && value.recommendations !== null)
    || (value.journey_state === 'profile_preparation' && (value.summary.candidate_count !== 0 || value.roadmap.roadmap_state !== 'profile_preparation'))
    || (value.journey_state === 'recommendations_ready' && value.recommendations === null)
    || (value.recommendations !== null && (value.recommendations.profile_key !== value.profile_key
      || value.summary.candidate_count !== value.recommendations.recommendations.length
      || value.roadmap.seed_order_start !== value.recommendations.seed_order_start
      || value.roadmap.seed_order_end !== value.recommendations.seed_order_end
      || value.roadmap.recommendation_limit !== value.recommendations.limit))) {
    throw new InvalidJourneyResponseError();
  }
  return value as unknown as AdmissionJourney;
}

export function clearJourneyCache() {
  requests.clear();
  snapshots.clear();
  listeners.forEach(listener => listener());
}

export function loadJourney(profileKey: string, options: { refresh?: boolean } = {}): Promise<AdmissionJourney> {
  if (options.refresh) requests.delete(profileKey);
  const existing = requests.get(profileKey);
  if (existing) return existing;
  const request = createApiClient().get<unknown>(
    `profiles/${encodeURIComponent(profileKey)}/journey/?seed_order_start=1&seed_order_end=100`,
  ).then(value => {
    const journey = readAdmissionJourney(value);
    if (journey.profile_key !== profileKey) throw new InvalidJourneyResponseError();
    // A save can invalidate an in-flight request. It must never republish old data.
    if (requests.get(profileKey) === request) {
      publish(profileKey, { savedProfile: true, started: true, state: { status: 'ready', journey } });
    }
    return journey;
  });
  requests.set(profileKey, request);
  publish(profileKey, { ...getJourneySnapshot(profileKey), started: true, state: { status: 'loading' } });
  void request.catch(error => {
    if (requests.get(profileKey) !== request) return;
    requests.delete(profileKey);
    const profileMissing = error instanceof ApiError && error.status === 404 && error.envelope?.error.code === 'profile_not_found';
    publish(profileKey, {
      savedProfile: !profileMissing && getJourneySnapshot(profileKey).savedProfile, started: true,
      state: { status: 'error', profileMissing, message: error instanceof InvalidJourneyResponseError
        ? 'Talap received an unexpected journey response. Please try again.'
        : 'Talap could not load your journey. Please check your connection and try again.' },
    });
  });
  return request;
}
