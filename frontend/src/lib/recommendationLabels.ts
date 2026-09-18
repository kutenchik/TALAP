import type { EnglishAssessment, EnglishTestAssessment, PositionState, ProgramAssessment, RecommendationActionCode, RecommendationReasonCode, RecommendationState } from '../types/journey';

export const recommendationLabels: Record<RecommendationState, string> = {
  recommended_for_review: 'Recommended for review', consider_with_actions: 'Consider with actions',
  insufficient_evidence: 'More evidence needed', excluded_by_applicant: 'Excluded by you',
};
export const programLabels: Record<ProgramAssessment['state'], string> = {
  one_or_more_observed: 'Program evidence found', none_observed: 'Not observed in current data',
  unavailable: 'Program data unavailable', not_evaluated_explore_mode: 'Not evaluated in explore mode',
};
export const englishLabels: Record<EnglishTestAssessment['state'], string> = {
  meets_verified_minimum: 'Meets verified minimum', below_verified_minimum: 'Below verified minimum',
  no_minimum_published: 'No minimum published', not_required: 'Not required',
  no_matching_applicant_score: 'No matching applicant score', requirement_not_found: 'Requirement not found',
  requirement_conflicting: 'Conflicting requirements', requirement_unavailable: 'Requirement unavailable',
  applicability_ambiguous: 'Applicability unresolved', no_applicable_requirement: 'No applicable requirement',
};
export const policyLabels: Record<EnglishAssessment['policy_state'], string> = {
  not_required: 'Not required', no_minimum_published: 'No minimum published', verified_minimum: 'Verified minimum published',
  conflicting: 'Conflicting policy evidence', reviewed_not_found: 'Policy reviewed, not found', unavailable: 'Policy unavailable',
};
export const academicLabels: Record<PositionState, string> = {
  above_reported_context: 'Above reported context', within_reported_context: 'Within reported context', below_reported_context: 'Below reported context',
  context_unavailable: 'Context unavailable', applicant_score_missing: 'Applicant score missing', context_not_comparable: 'Context not comparable',
};
export const qualityLabels = { usable: 'Usable evidence', partial: 'Partial evidence', sparse: 'Limited evidence', conflicting: 'Conflicting evidence' };
export const actionLabels: Record<RecommendationActionCode, string> = {
  retake_or_improve_english_test: 'Retake or improve your English test', submit_compatible_english_score: 'Submit a compatible English score',
  verify_current_english_policy: 'Verify the current English policy', verify_program_availability: 'Verify program availability',
  research_financial_aid: 'Research financial aid', provide_missing_academic_test_if_desired: 'Provide an academic test score if desired',
};
export const reasonLabels: Record<RecommendationReasonCode, string> = {
  preferred_state: 'In a preferred state', excluded_state: 'Excluded by your location preferences', program_cip_observed: 'Submitted CIP evidence found',
  program_evidence_partial: 'Partial program evidence', program_evidence_unavailable: 'Program evidence unavailable', program_not_evaluated_explore_mode: 'Program not evaluated in explore mode',
  english_minimum_met: 'Verified English minimum met', english_not_required: 'English test not required', english_no_minimum_published: 'No English minimum published',
  english_minimum_not_met: 'Below the verified English minimum', english_score_missing: 'Compatible English score missing', english_policy_unavailable: 'English policy unavailable',
  english_policy_not_found: 'English policy not found', english_policy_conflicting: 'Conflicting English policy evidence', english_applicability_unresolved: 'English policy applicability unresolved',
  english_conditional_policy_review_needed: 'Conditional English policy needs review', academic_above_reported_context: 'Academic score above reported context',
  academic_within_reported_context: 'Academic score within reported context', academic_below_reported_context: 'Academic score below reported context',
  academic_context_unavailable: 'Academic context unavailable', financial_review_needed: 'Financial information needs review', sparse_data: 'Limited data available',
};
