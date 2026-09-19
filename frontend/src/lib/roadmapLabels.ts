import type {
  RoadmapActionCode,
  RoadmapCategory,
  RoadmapPriority,
  RoadmapReasonCode,
} from '../types/journey';

export const roadmapPriorityOrder: readonly RoadmapPriority[] = ['required', 'high', 'medium', 'optional'];

export const roadmapPriorityLabels: Record<RoadmapPriority, string> = {
  required: 'Required',
  high: 'High priority',
  medium: 'Medium priority',
  optional: 'Optional',
};

export const roadmapCategoryLabels: Record<RoadmapCategory, string> = {
  profile: 'Profile',
  academics: 'Academics',
  english: 'English',
  program: 'Program',
  financial: 'Financial',
  research: 'Research',
};

export const roadmapActionLabels: Record<RoadmapActionCode, string> = {
  define_intended_major: 'Define your intended major',
  provide_academic_interests: 'Add your academic interests',
  provide_graduation_year: 'Add your graduation year',
  provide_gpa: 'Add your GPA',
  provide_class_rank_if_available: 'Add your class rank if available',
  provide_academic_test_if_desired: 'Add an academic test score if desired',
  provide_english_test_score: 'Add an English test score',
  provide_annual_budget: 'Add your annual budget',
  retake_or_improve_english_test: 'Retake or improve your English test',
  submit_compatible_english_score: 'Submit a compatible English score',
  verify_current_english_policy: 'Verify the current English policy',
  verify_program_availability: 'Verify program availability',
  research_financial_aid: 'Research financial aid',
  provide_missing_academic_test_if_desired: 'Provide an academic test score if desired',
};

export const roadmapReasonLabels: Record<RoadmapReasonCode, string> = {
  major_missing: 'Your intended major is missing from your profile.',
  interests_missing: 'Your academic interests are missing from your profile.',
  graduation_year_missing: 'Your graduation year is missing from your profile.',
  gpa_missing: 'Your GPA is missing from your profile.',
  class_rank_missing: 'Your class rank is not currently available.',
  academic_test_scores_missing: 'No SAT or ACT score is currently available.',
  english_test_scores_missing: 'No English test score is currently available.',
  annual_budget_missing: 'Your annual budget is missing from your profile.',
  english_minimum_not_met: 'A submitted score is below a verified English minimum.',
  english_score_missing: 'A compatible English score is not currently available.',
  english_policy_unavailable: 'The current English policy is unavailable.',
  english_policy_not_found: 'The English policy was reviewed but not found.',
  english_policy_conflicting: 'The available English policy evidence conflicts.',
  english_applicability_unresolved: 'The English policy applicability is unresolved.',
  english_conditional_policy_review_needed: 'A conditional English policy needs review.',
  program_evidence_partial: 'The available program evidence is partial.',
  program_evidence_unavailable: 'Program evidence is unavailable.',
  financial_review_needed: 'Financial information needs further review.',
  academic_context_unavailable: 'Academic comparison context is unavailable.',
};
