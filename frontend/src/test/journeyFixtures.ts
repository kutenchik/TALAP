import type { AdmissionJourney, ApplicantDiagnostic } from '../types/journey';

export function diagnosticFixture(): ApplicantDiagnostic {
  return {
    profile_key: 'talap-local-journey-test',
    goal: { mode: 'known_major', intended_cip_codes: ['11.0701', '14.0901'], interests: [], goal_supplied: true },
    academics: {
      graduation_year: 2027,
      gpa: { state: 'provided', gpa_value: 4.7, gpa_scale: 5, gpa_weighting: 'unknown' },
      class_rank: { state: 'provided', class_rank: 2, class_size: 30 },
    },
    testing: {
      state: 'scores_provided',
      attempts: [
        { test_type: 'sat', scale: 'sat_total_400_1600', score: 1450, taken_on: '2026-07-12' },
        { test_type: 'act', scale: 'act_composite_1_36', score: 32, taken_on: null },
      ],
    },
    english: {
      state: 'scores_provided',
      attempts: [
        { test_type: 'toefl', scale: 'toefl_ibt_0_120', score: 105, taken_on: '2026-05-01' },
        { test_type: 'toefl', scale: 'toefl_ibt_1_6', score: 5, taken_on: '2026-06-01' },
        { test_type: 'ielts', scale: 'ielts_0_9', score: 6.5, taken_on: null },
      ],
    },
    financial: { budget_state: 'budget_provided', annual_budget_usd: 25000, needs_financial_aid: true },
    preferences: { preferred_states: ['CA', 'NY'], excluded_states: ['TX', 'FL'] },
    explicit_constraints: [
      { constraint_type: 'excluded_state', value: 'TX', hard: true, source: 'applicant_profile' },
      { constraint_type: 'excluded_state', value: 'FL', hard: true, source: 'applicant_profile' },
    ],
    missing_information: [
      { code: 'gpa_missing', importance: 'useful', message: 'GPA was not supplied.' },
      { code: 'english_test_scores_missing', importance: 'useful', message: 'No English test attempt was supplied.' },
      { code: 'class_rank_missing', importance: 'optional', message: 'Class rank was not supplied.' },
    ],
  };
}

export function readyJourneyFixture(): AdmissionJourney {
  const diagnostic = diagnosticFixture();
  return {
    profile_key: diagnostic.profile_key,
    journey_state: 'recommendations_ready',
    diagnostic,
    recommendations: {
      profile_key: diagnostic.profile_key,
      seed_order_start: 1,
      seed_order_end: 100,
      limit: null,
      applicant_financial_context: { annual_budget_usd: 25000, needs_financial_aid: true },
      recommendations: [],
    },
    roadmap: {
      profile_key: diagnostic.profile_key,
      roadmap_state: 'no_blocking_actions',
      seed_order_start: 1,
      seed_order_end: 100,
      recommendation_limit: null,
      items: [],
    },
    summary: {
      candidate_count: 0,
      recommended_for_review_count: 0,
      consider_with_actions_count: 0,
      insufficient_evidence_count: 0,
      excluded_by_applicant_count: 0,
      roadmap_item_count: 0,
    },
  };
}

export function preparationJourneyFixture(): AdmissionJourney {
  const journey = readyJourneyFixture();
  journey.journey_state = 'profile_preparation';
  journey.diagnostic.goal = { mode: 'known_major', intended_cip_codes: [], interests: [], goal_supplied: false };
  journey.diagnostic.missing_information = [
    { code: 'major_missing', importance: 'required_for_next_step', message: 'No intended CIP code was supplied for known-major mode.' },
    { code: 'gpa_missing', importance: 'useful', message: 'GPA was not supplied.' },
    { code: 'english_test_scores_missing', importance: 'useful', message: 'No English test attempt was supplied.' },
    { code: 'class_rank_missing', importance: 'optional', message: 'Class rank was not supplied.' },
  ];
  journey.recommendations = null;
  journey.roadmap.roadmap_state = 'profile_preparation';
  journey.roadmap.items = [{
    action_code: 'define_intended_major', category: 'profile', priority: 'required', scope: 'profile',
    institution_unitids: [], reason_codes: ['major_missing'],
  }];
  journey.summary.roadmap_item_count = 1;
  return journey;
}
