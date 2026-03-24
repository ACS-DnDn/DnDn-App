export const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api';
export const REPORT_BASE_URL = (import.meta.env.VITE_REPORT_API_BASE_URL as string | undefined) ?? '/report-api';

export async function reportApiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const isFormData = init?.body instanceof FormData;

  if (!headers.has('Content-Type') && init?.body != null && !isFormData) {
    headers.set('Content-Type', 'application/json');
  }

  const token = localStorage.getItem('dndn-access-token');
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${REPORT_BASE_URL}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const isFormData = init?.body instanceof FormData;

  if (!headers.has('Content-Type') && init?.body != null && !isFormData) {
    headers.set('Content-Type', 'application/json');
  }

  const token = localStorage.getItem('dndn-access-token');
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
