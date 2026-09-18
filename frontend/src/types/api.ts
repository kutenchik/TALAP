export interface ValidationDetail {
  location: (string | number)[];
  message: string;
  type: string;
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string; details?: ValidationDetail[] };
}

export interface CsrfResponse { csrfToken: string }

export function readErrorEnvelope(value: unknown): ApiErrorEnvelope | undefined {
  if (!value || typeof value !== 'object' || !('error' in value)) return;
  const error = value.error;
  if (!error || typeof error !== 'object' || !('code' in error) ||
      !('message' in error) || typeof error.code !== 'string' || typeof error.message !== 'string') return;
  let details: ValidationDetail[] | undefined;
  if ('details' in error && Array.isArray(error.details)) {
    details = error.details.filter((detail: unknown): detail is ValidationDetail => {
      if (!detail || typeof detail !== 'object') return false;
      return 'location' in detail && Array.isArray(detail.location) &&
        detail.location.every((part: unknown) => typeof part === 'string' || typeof part === 'number') &&
        'message' in detail && typeof detail.message === 'string' &&
        'type' in detail && typeof detail.type === 'string';
    });
  }
  return { error: { code: error.code, message: error.message, details } };
}
