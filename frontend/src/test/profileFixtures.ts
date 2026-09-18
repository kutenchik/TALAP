import { beforeEach, afterEach, vi } from 'vitest';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import type { ApplicantProfileInput } from '../types/profile';

// Fictional test data only; production forms have no applicant defaults.
export function profileFixture(): ApplicantProfileInput {
  return {
    profile_key: 'talap-local-test', display_name: 'Test Applicant', citizenship_country_code: 'KZ',
    residence_country_code: 'KZ', school_country_code: null, graduation_year: 2027,
    academics: { gpa_value: 4.7, gpa_scale: 5, gpa_weighting: 'unknown', class_rank: 2, class_size: 30 },
    tests: [{ test_type: 'toefl', scale: 'toefl_ibt_1_6', score: 5, taken_on: '2026-02-01', note: 'Practice fixture' }],
    study_intent: { mode: 'known_major', intended_cip_codes: ['11.0701'], interests: [] },
    financial: { annual_budget_usd: 0, needs_financial_aid: false },
    preferences: { preferred_states: ['CA'], excluded_states: ['TX'] },
  };
}
export const jsonResponse = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
export const missingProfile = () => jsonResponse({ error: { code: 'profile_not_found', message: 'Profile not found.' } }, 404);

export function mockProfileServer(initial: ApplicantProfileInput | null = null) {
  let saved = initial;
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/v1/csrf/') return jsonResponse({ csrfToken: 'test-csrf-token' });
    if (url === '/api/v1/profiles/validate/') return jsonResponse(JSON.parse(String(options?.body)));
    if (url === '/api/v1/profiles/' && options?.method === 'POST') {
      saved = JSON.parse(String(options.body)) as ApplicantProfileInput;
      return jsonResponse(saved);
    }
    if (url.startsWith('/api/v1/profiles/') && options?.method === 'GET') return saved ? jsonResponse(saved) : missingProfile();
    throw new Error(`Unexpected test request: ${url}`);
  });
  vi.stubGlobal('fetch', fetcher);
  return { fetcher, saved: () => saved };
}

export function useProfileTestEnvironment() {
  beforeEach(() => {
    localStorage.clear();
    vi.stubEnv('VITE_API_BASE_URL', '');
    mockProfileServer();
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); localStorage.clear(); });
}
export function useSavedProfile() {
  const profile = profileFixture();
  localStorage.setItem(LOCAL_PROFILE_KEY, profile.profile_key);
  return { profile, ...mockProfileServer(profile) };
}
