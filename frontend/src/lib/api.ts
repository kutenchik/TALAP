import { readErrorEnvelope, type ApiErrorEnvelope } from '../types/api';

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly envelope?: ApiErrorEnvelope) {
    super(`Request failed (${status})`);
    this.name = 'ApiError';
  }
}

export function createApiClient(baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1') {
  const base = baseUrl.replace(/\/+$/, '');
  function url(path: string) {
    // Keep endpoint paths relative to the configured API, including for CSRF-bearing requests.
    if (/^(?:[a-z]+:|\/\/)/i.test(path) || path.split('/').includes('..')) throw new Error('Expected a relative API endpoint');
    return `${base}/${path.replace(/^\/+/, '')}`;
  }
  async function request<T>(path: string, options: RequestInit): Promise<T> {
    const response = await fetch(url(path), { ...options, credentials: 'same-origin' });
    if (!response.ok) {
      // Django middleware may return HTML (for example for CSRF rejection).
      // Retain only the structured envelope; never render raw response bodies.
      let envelope: ApiErrorEnvelope | undefined;
      try { envelope = readErrorEnvelope(await response.json()); } catch { /* Non-JSON errors use a safe fallback. */ }
      throw new ApiError(response.status, envelope);
    }
    return response.status === 204 ? undefined as T : response.json() as Promise<T>;
  }
  return {
    get<T>(path: string, signal?: AbortSignal) {
      return request<T>(path, { method: 'GET', headers: { Accept: 'application/json' }, signal });
    },
    post<T>(path: string, body: unknown, csrfToken: string, signal?: AbortSignal) {
      if (!csrfToken.trim()) throw new Error('A CSRF token is required for browser POSTs');
      return request<T>(path, { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: JSON.stringify(body), signal });
    },
  };
}
