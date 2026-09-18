import type { AcademicsInput, ApplicantProfileInput, ApplicantTestScoreInput } from '../types/profile';

export const testOptions: { label: string; type: ApplicantTestScoreInput['test_type']; scale: ApplicantTestScoreInput['scale'] }[] = [
  { label: 'SAT', type: 'sat', scale: 'sat_total_400_1600' },
  { label: 'ACT', type: 'act', scale: 'act_composite_1_36' },
  { label: 'IELTS', type: 'ielts', scale: 'ielts_0_9' },
  { label: 'TOEFL iBT 0–120', type: 'toefl', scale: 'toefl_ibt_0_120' },
  { label: 'TOEFL iBT 1–6', type: 'toefl', scale: 'toefl_ibt_1_6' },
  { label: 'Duolingo English Test', type: 'duolingo', scale: 'det_10_160' },
];

export interface TextRow { id: string; value: string }
export interface TestRow { id: string; scale: ApplicantTestScoreInput['scale']; score: string; takenOn: string; note: string }

/** Input strings preserve empty/partial edits; this is form state, not a validation schema. */
export interface ProfileDraft {
  displayName: string;
  citizenship: string;
  residence: string;
  school: string;
  graduationYear: string;
  gpaValue: string;
  gpaScale: string;
  gpaWeighting: AcademicsInput['gpa_weighting'];
  classRank: string;
  classSize: string;
  mode: ApplicantProfileInput['study_intent']['mode'];
  cips: TextRow[];
  interests: TextRow[];
  tests: TestRow[];
  budget: string;
  aid: '' | 'yes' | 'no';
  preferredStates: string;
  excludedStates: string;
}

export function textRow(value = ''): TextRow { return { id: crypto.randomUUID(), value }; }
export function emptyDraft(): ProfileDraft {
  return {
    displayName: '', citizenship: '', residence: '', school: '', graduationYear: '',
    gpaValue: '', gpaScale: '', gpaWeighting: 'unknown', classRank: '', classSize: '',
    mode: 'known_major', cips: [], interests: [], tests: [], budget: '', aid: '',
    preferredStates: '', excludedStates: '',
  };
}
const text = (value: string | number | null) => value === null ? '' : String(value);
const optionalText = (value: string) => value.trim() || null;
const optionalNumber = (value: string) => value.trim() === '' ? null : Number(value);
const states = (value: string) => value.split(',').map(part => part.trim().toUpperCase()).filter(Boolean);

export function toDraft(profile: ApplicantProfileInput): ProfileDraft {
  return {
    displayName: text(profile.display_name), citizenship: profile.citizenship_country_code,
    residence: text(profile.residence_country_code), school: text(profile.school_country_code),
    graduationYear: text(profile.graduation_year), gpaValue: text(profile.academics.gpa_value),
    gpaScale: text(profile.academics.gpa_scale), gpaWeighting: profile.academics.gpa_weighting,
    classRank: text(profile.academics.class_rank), classSize: text(profile.academics.class_size),
    mode: profile.study_intent.mode, cips: profile.study_intent.intended_cip_codes.map(textRow),
    interests: profile.study_intent.interests.map(textRow),
    tests: profile.tests.map(attempt => ({ id: crypto.randomUUID(), scale: attempt.scale,
      score: String(attempt.score), takenOn: text(attempt.taken_on), note: text(attempt.note) })),
    budget: text(profile.financial.annual_budget_usd),
    aid: profile.financial.needs_financial_aid === null ? '' : profile.financial.needs_financial_aid ? 'yes' : 'no',
    preferredStates: profile.preferences.preferred_states.join(', '),
    excludedStates: profile.preferences.excluded_states.join(', '),
  };
}

export function toPayload(draft: ProfileDraft, key: string): ApplicantProfileInput {
  return {
    profile_key: key, display_name: optionalText(draft.displayName), citizenship_country_code: draft.citizenship.trim().toUpperCase(),
    residence_country_code: optionalText(draft.residence.toUpperCase()), school_country_code: optionalText(draft.school.toUpperCase()),
    graduation_year: optionalNumber(draft.graduationYear),
    academics: { gpa_value: optionalNumber(draft.gpaValue), gpa_scale: optionalNumber(draft.gpaScale),
      gpa_weighting: draft.gpaWeighting, class_rank: optionalNumber(draft.classRank), class_size: optionalNumber(draft.classSize) },
    tests: draft.tests.map(attempt => ({ test_type: testOptions.find(option => option.scale === attempt.scale)!.type,
      scale: attempt.scale, score: Number(attempt.score), taken_on: optionalText(attempt.takenOn), note: optionalText(attempt.note) })),
    study_intent: { mode: draft.mode,
      intended_cip_codes: draft.mode === 'known_major' ? draft.cips.map(row => row.value.trim()).filter(Boolean) : [],
      interests: draft.mode === 'explore' ? draft.interests.map(row => row.value.trim()).filter(Boolean) : [] },
    financial: { annual_budget_usd: optionalNumber(draft.budget), needs_financial_aid: draft.aid === '' ? null : draft.aid === 'yes' },
    preferences: { preferred_states: states(draft.preferredStates), excluded_states: states(draft.excludedStates) },
  };
}
