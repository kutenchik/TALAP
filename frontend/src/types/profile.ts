/** Mirrors admission.applicants.schemas; business validation stays in Django. */
export interface AcademicsInput {
  gpa_value: number | null;
  gpa_scale: number | null;
  gpa_weighting: 'unknown' | 'weighted' | 'unweighted';
  class_rank: number | null;
  class_size: number | null;
}

export interface ApplicantTestScoreInput {
  test_type: 'sat' | 'act' | 'ielts' | 'toefl' | 'duolingo';
  scale: 'sat_total_400_1600' | 'act_composite_1_36' | 'ielts_0_9' |
    'toefl_ibt_0_120' | 'toefl_ibt_1_6' | 'det_10_160';
  score: number;
  taken_on: string | null;
  note: string | null;
}

export interface ApplicantProfileInput {
  profile_key: string;
  display_name: string | null;
  citizenship_country_code: string;
  residence_country_code: string | null;
  school_country_code: string | null;
  graduation_year: number | null;
  academics: AcademicsInput;
  tests: ApplicantTestScoreInput[];
  study_intent: {
    mode: 'known_major' | 'explore';
    intended_cip_codes: string[];
    interests: string[];
  };
  financial: {
    annual_budget_usd: number | null;
    needs_financial_aid: boolean | null;
  };
  preferences: { preferred_states: string[]; excluded_states: string[] };
}

// Validate, save, and get all return the normalized input representation.
export type ApplicantProfileResponse = ApplicantProfileInput;
