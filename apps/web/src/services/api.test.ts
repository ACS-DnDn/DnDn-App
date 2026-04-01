import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';


class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}


function createJsonResponse(body: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  const text = JSON.stringify(body);
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? 'OK',
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(text),
  };
}


describe('api service helpers', () => {
  const fetchMock = vi.fn();
  const storage = new MemoryStorage();

  beforeEach(() => {
    vi.resetModules();
    fetchMock.mockReset();
    storage.clear();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', storage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('adds authorization and json headers for apiFetch', async () => {
    storage.setItem('dndn-access-token', 'token-123');
    fetchMock.mockResolvedValue(createJsonResponse({ ok: true }));

    const { apiFetch } = await import('@/services/api');

    await expect(apiFetch('/documents', { method: 'POST', body: JSON.stringify({ a: 1 }) })).resolves.toEqual({ ok: true });

    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toMatch(/\/api\/documents$/);
    expect((options as RequestInit).method).toBe('POST');
    expect(((options as RequestInit).headers as Headers).get('Authorization')).toBe('Bearer token-123');
    expect(((options as RequestInit).headers as Headers).get('Content-Type')).toBe('application/json');
  });

  it('refreshes token once and retries failed apiFetch requests', async () => {
    storage.setItem('dndn-access-token', 'expired-token');
    storage.setItem('dndn-refresh-token', 'refresh-token');

    fetchMock
      .mockResolvedValueOnce(createJsonResponse({ error: 'expired' }, { ok: false, status: 401, statusText: 'Unauthorized' }))
      .mockResolvedValueOnce(createJsonResponse({ data: { accessToken: 'fresh-token' } }))
      .mockResolvedValueOnce(createJsonResponse({ ok: true }));

    const { apiFetch } = await import('@/services/api');

    await expect(apiFetch('/dashboard')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1]?.[0])).toMatch(/\/api\/auth\/refresh$/);
    expect(String(fetchMock.mock.calls[2]?.[0])).toMatch(/\/api\/dashboard$/);
    expect(storage.getItem('dndn-access-token')).toBe('fresh-token');
    expect((((fetchMock.mock.calls[2]?.[1] as RequestInit).headers) as Headers).get('Authorization')).toBe('Bearer fresh-token');
  });

  it('throws original error when refresh token flow cannot recover', async () => {
    storage.setItem('dndn-access-token', 'expired-token');
    storage.setItem('dndn-refresh-token', 'refresh-token');

    fetchMock
      .mockResolvedValueOnce(createJsonResponse({ error: 'expired' }, { ok: false, status: 401, statusText: 'Unauthorized' }))
      .mockResolvedValueOnce(createJsonResponse({ error: 'refresh failed' }, { ok: false, status: 401, statusText: 'Unauthorized' }));

    const { apiFetch } = await import('@/services/api');

    await expect(apiFetch('/dashboard')).rejects.toThrow('SESSION_EXPIRED');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toMatch(/\/api\/auth\/refresh$/);
    // 토큰이 삭제되었는지 확인
    expect(storage.getItem('dndn-access-token')).toBeNull();
    expect(storage.getItem('dndn-refresh-token')).toBeNull();
  });

  it('does not force content-type for FormData payloads', async () => {
    fetchMock.mockResolvedValue(createJsonResponse({ ok: true }));

    const { apiFetch } = await import('@/services/api');
    const formData = new FormData();
    formData.append('file', 'demo');

    await apiFetch('/upload', { method: 'POST', body: formData });

    const [, options] = fetchMock.mock.calls[0] ?? [];
    expect(((options as RequestInit).headers as Headers).has('Content-Type')).toBe(false);
  });

  it('uses API error message from response body for reportApiFetch', async () => {
    fetchMock.mockResolvedValue(
      createJsonResponse(
        { error: { message: 'report failed' } },
        { ok: false, status: 500, statusText: 'Internal Server Error' },
      ),
    );

    const { reportApiFetch } = await import('@/services/api');

    await expect(reportApiFetch('/documents/generate/plan')).rejects.toThrow('report failed');
  });
});
