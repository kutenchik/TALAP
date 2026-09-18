import type { RecommendationState, UniversityRecommendation } from '../types/journey';
import { readyJourneyFixture } from './journeyFixtures';

export function universityFixture(id: number, state: RecommendationState): UniversityRecommendation {
  const institution = { ipeds_unitid: id, name: `Test University ${id}`, state: 'CA' };
  const test = { state: 'context_not_comparable' as const, context: null, attempts: [] };
  return {
    seed_order: id, institution, recommendation_state: state,
    signals: { program: 'partial', english: 'uncertain', academic: 'unavailable', preference: 'neutral', financial: 'unavailable', data_quality: 'partial' },
    action_codes: ['verify_current_english_policy', 'research_financial_aid'], reason_codes: ['program_evidence_partial', 'english_policy_unavailable'],
    assessment: {
      seed_order: id, institution, applicant_constraints: { excluded_by_applicant: state === 'excluded_by_applicant', reasons: state === 'excluded_by_applicant' ? ['excluded_state'] : [] },
      program: { state: 'none_observed', requested_cips: [{ cip_code: '11.0701', state: 'not_observed', academic_years: [] }] },
      english: { policy_state: 'unavailable', tests: [{ test_type: 'toefl', state: 'requirement_unavailable', requirements: [], conditional_policy_present: false, supporting_attempts: [
        { scale: 'toefl_ibt_0_120', score: 105, taken_on: null }, { scale: 'toefl_ibt_1_6', score: 5, taken_on: null },
      ] }] },
      data_availability: { program_data_available: false, english_data_available: false, admissions_context_available: false },
      academic: { snapshot_available: false, sat_context_available: false, act_context_available: false, data_year: null, source_data_year: null, term: null, source_url: null, source_locator: null, gpa: { state: 'missing', gpa_value: null, gpa_scale: null, gpa_weighting: 'unknown' }, sat: test, act: { ...test, state: 'applicant_score_missing' } },
      evidence_quality: { program: 'unavailable', english: 'unavailable', academic: 'unavailable' },
    },
  };
}
export function recommendationJourneyFixture() {
  const journey = readyJourneyFixture();
  journey.recommendations!.recommendations = [
    universityFixture(40, 'recommended_for_review'), universityFixture(20, 'consider_with_actions'),
    universityFixture(60, 'insufficient_evidence'), universityFixture(10, 'excluded_by_applicant'), universityFixture(30, 'recommended_for_review'),
  ];
  Object.assign(journey.summary, { candidate_count: 5, recommended_for_review_count: 2, consider_with_actions_count: 1, insufficient_evidence_count: 1, excluded_by_applicant_count: 1 });
  return journey;
}
