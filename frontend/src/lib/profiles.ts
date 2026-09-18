import { ApiError, createApiClient } from './api';
import type { ApplicantProfileInput, ApplicantProfileResponse } from '../types/profile';
import type { CsrfResponse } from '../types/api';

export const LOCAL_PROFILE_KEY = 'talap.localProfileKey';

export function getLocalProfileKey(): { key: string; existing: boolean } {
  const existing = localStorage.getItem(LOCAL_PROFILE_KEY);
  if (existing) return { key: existing, existing: true };
  const key = `talap-local-${crypto.randomUUID()}`;
  // If storage is blocked, report it instead of silently generating a different identity on every visit.
  localStorage.setItem(LOCAL_PROFILE_KEY, key);
  return { key, existing: false };
}

export async function loadLocalProfile(signal: AbortSignal) {
  const identity = getLocalProfileKey();
  if (!identity.existing) return { key: identity.key, profile: null };
  try {
    const profile = await createApiClient().get<ApplicantProfileResponse>(
      `profiles/${encodeURIComponent(identity.key)}/`, signal,
    );
    return { key: identity.key, profile };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.envelope?.error.code === 'profile_not_found') {
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
  return api.post<ApplicantProfileResponse>('profiles/', validated, csrf.csrfToken, signal);
}
