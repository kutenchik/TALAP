import { ApiError, createApiClient } from './api';
import type { ApplicantProfileInput, ApplicantProfileResponse } from '../types/profile';
import type { CsrfResponse } from '../types/api';
import { clearJourneyCache, markProfileSaved } from './journey';
import { clearCompareSelection } from './compareSelection';

export const LOCAL_PROFILE_KEY = 'talap.localProfileKey';

export function readLocalProfileKey(): string | null {
  const key = localStorage.getItem(LOCAL_PROFILE_KEY)?.trim();
  return key || null;
}

export function getLocalProfileKey(): { key: string; existing: boolean } {
  const existing = readLocalProfileKey();
  if (existing) return { key: existing, existing: true };
  const key = `talap-local-${crypto.randomUUID()}`;
  // If storage is blocked, report it instead of silently generating a different identity on every visit.
  localStorage.setItem(LOCAL_PROFILE_KEY, key);
  clearJourneyCache();
  clearCompareSelection();
  return { key, existing: false };
}

export async function loadLocalProfile(signal: AbortSignal) {
  const identity = getLocalProfileKey();
  if (!identity.existing) return { key: identity.key, profile: null };
  try {
    const profile = await createApiClient().get<ApplicantProfileResponse>(
      `profiles/${encodeURIComponent(identity.key)}/`, signal,
    );
    if (!signal.aborted) markProfileSaved(identity.key);
    return { key: identity.key, profile };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.envelope?.error.code === 'profile_not_found') {
      if (!signal.aborted) { clearJourneyCache(); clearCompareSelection(); }
      return { key: identity.key, profile: null };
    }
    throw error;
  }
}

export async function saveProfile(profile: ApplicantProfileInput, signal: AbortSignal) {
  const api = createApiClient();
  const csrf = await api.get<CsrfResponse>('csrf/', signal);
  if (typeof csrf.csrfToken !== 'string' || !csrf.csrfToken.trim()) {
    throw new Error('CSRF acquisition failed');
  }
  const validated = await api.post<ApplicantProfileResponse>('profiles/validate/', profile, csrf.csrfToken, signal);
  // Persist the backend-normalized representation; do not duplicate its validation.
  const saved = await api.post<ApplicantProfileResponse>('profiles/', validated, csrf.csrfToken, signal);
  clearJourneyCache();
  clearCompareSelection();
  markProfileSaved(profile.profile_key);
  return saved;
}
