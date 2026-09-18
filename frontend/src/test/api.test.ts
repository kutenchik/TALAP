import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '../lib/api';
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
describe('API foundation', () => {
  it('defaults to same-origin /api/v1', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    const fetcher = vi.fn().mockResolvedValue(new Response('{"ok":true}'));
    vi.stubGlobal('fetch', fetcher);
    expect(await createApiClient().get('health/')).toEqual({ ok: true });
    expect(fetcher).toHaveBeenCalledWith('/api/v1/health/', expect.objectContaining({ credentials: 'same-origin', method: 'GET' }));
  });
  it('uses the Vite environment configuration and normalizes slashes', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '/configured/api/');
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetcher);
    await createApiClient().get('/health/');
    expect(fetcher).toHaveBeenCalledWith('/configured/api/health/', expect.anything());
  });
  it('sends JSON and an explicit CSRF header without changing credential policy', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    expect(await createApiClient().post('example/', { example: true }, 'test-token')).toBeUndefined();
    expect(fetcher).toHaveBeenCalledWith('/api/v1/example/', expect.objectContaining({ method: 'POST', body: '{"example":true}', credentials: 'same-origin', headers: expect.objectContaining({ 'X-CSRFToken': 'test-token', 'Content-Type': 'application/json' }) }));
  });
  it('rejects tokenless POSTs before any request', () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    expect(() => createApiClient().post('example/', {}, '')).toThrow('CSRF');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('exposes HTTP errors without exposing response bodies', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private server detail', { status: 403 })));
    await expect(createApiClient().get('example/')).rejects.toEqual(new ApiError(403));
  });
  it('rejects endpoint paths that escape the configured API', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    await expect(createApiClient().get('https://example.com')).rejects.toThrow('relative API');
    await expect(createApiClient().get('../other')).rejects.toThrow('relative API');
    expect(fetcher).not.toHaveBeenCalled();
  });
});
