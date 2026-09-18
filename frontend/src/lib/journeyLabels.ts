import type { MissingInformationCode, MissingInformationImportance, TestScale, TestType } from '../types/journey';

export const importanceLabels: Record<MissingInformationImportance, string> = {
  required_for_next_step: 'Required next step',
  useful: 'Useful',
  optional: 'Optional',
};

export const missingInformationLabels: Record<MissingInformationCode, string> = {
  major_missing: 'Add your intended major',
  interests_missing: 'Add your academic interests',
  graduation_year_missing: 'Add your graduation year',
  gpa_missing: 'Add your GPA',
  class_rank_missing: 'Add your class rank',
  academic_test_scores_missing: 'Add an SAT or ACT score',
  english_test_scores_missing: 'Add an English test score',
  annual_budget_missing: 'Add your annual budget',
};

export const studyModeLabels = { known_major: 'Known major', explore: 'Exploring majors' } as const;
export const weightingLabels = { weighted: 'Weighted', unweighted: 'Unweighted', unknown: 'Unknown' } as const;
export const testScaleLabels: Record<TestScale, string> = {
  sat_total_400_1600: 'SAT',
  act_composite_1_36: 'ACT',
  ielts_0_9: 'IELTS',
  toefl_ibt_0_120: 'TOEFL iBT (0–120)',
  toefl_ibt_1_6: 'TOEFL iBT (1–6)',
  det_10_160: 'Duolingo English Test',
};
export const testTypeFallbackLabels: Record<TestType, string> = {
  sat: 'SAT', act: 'ACT', ielts: 'IELTS', toefl: 'TOEFL iBT', duolingo: 'Duolingo English Test',
};
