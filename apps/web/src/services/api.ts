export const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api';
export const REPORT_BASE_URL = (import.meta.env.VITE_REPORT_API_BASE_URL as string | undefined) ?? '/report-api';

// ── 토큰 자동 갱신 ──────────────────────────────────────
let refreshPromise: Promise<string | null> | null = null;

async function tryRefreshToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('dndn-refresh-token');
  if (!refreshToken) return null;

  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken }),
    });
    if (!res.ok) return null;
    const json = await res.json();
    const newToken = json.data?.accessToken;
    if (newToken) {
      localStorage.setItem('dndn-access-token', newToken);
      return newToken;
    }
    return null;
  } catch {
    return null;
  }
}

/** 동시 다발 401 시 refresh 요청을 1회로 통합 */
function refreshOnce(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = tryRefreshToken().finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

// ── 공통 fetch 헬퍼 ─────────────────────────────────────
function buildHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  const isFormData = init?.body instanceof FormData;
  if (!headers.has('Content-Type') && init?.body != null && !isFormData) {
    headers.set('Content-Type', 'application/json');
  }
  const token = localStorage.getItem('dndn-access-token');
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return headers;
}

export async function reportApiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let headers = buildHeaders(init);
  let res = await fetch(`${REPORT_BASE_URL}${path}`, { ...init, headers });

  // 401 → refresh 후 재시도
  if (res.status === 401) {
    const newToken = await refreshOnce();
    if (newToken) {
      headers = buildHeaders(init);
      res = await fetch(`${REPORT_BASE_URL}${path}`, { ...init, headers });
    } else {
      localStorage.removeItem('dndn-access-token');
      localStorage.removeItem('dndn-refresh-token');
      if (typeof window !== 'undefined') window.location.href = '/login';
      throw new Error('SESSION_EXPIRED');
    }
  }

  if (!res.ok) {
    const body = await res.text();
    let msg = `API ${res.status}: ${res.statusText}`;
    try {
      const parsed = JSON.parse(body);
      if (parsed?.error?.message) msg = parsed.error.message;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let headers = buildHeaders(init);
  let res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  // 401 → refresh 후 재시도
  if (res.status === 401) {
    const newToken = await refreshOnce();
    if (newToken) {
      headers = buildHeaders(init);
      res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
    } else {
      // refresh 실패 → 자동 로그아웃
      localStorage.removeItem('dndn-access-token');
      localStorage.removeItem('dndn-refresh-token');
      if (typeof window !== 'undefined') window.location.href = '/login';
      throw new Error('SESSION_EXPIRED');
    }
  }

  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
