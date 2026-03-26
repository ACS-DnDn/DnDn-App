import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { apiFetch } from '@/services/api';
import type { Session, AuthRole } from '@/mocks';

interface ApiMeResponse {
  success: boolean;
  data: {
    id: string;
    name: string;
    email: string;
    role: string;
    position: string | null;
    company: { name: string; logoUrl: string };
    createdAt: string | null;
  };
}

interface ApiLoginData {
  accessToken: string;
  refreshToken: string;
  idToken: string;
  expiresIn: number;
}

interface ApiChallengeData {
  challenge: string;
  session: string;
}

export type LoginResult =
  | { type: 'success' }
  | { type: 'challenge'; session: string };

interface AuthContextValue {
  session: Session | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  challenge: (email: string, newPassword: string, session: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<string>;
  confirmResetPassword: (email: string, code: string, newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue>({
  session: null,
  isLoading: true,
  login: async () => ({ type: 'success' }),
  challenge: async () => {},
  forgotPassword: async () => '',
  confirmResetPassword: async () => {},
  logout: async () => {},
});

function roleToAuth(role: string): AuthRole {
  if (role === 'leader' || role === 'admin') return 'leader';
  if (role === 'auditor') return 'auditor';
  return 'user';
}

function saveTokens(data: ApiLoginData) {
  localStorage.setItem('dndn-access-token', data.accessToken);
  localStorage.setItem('dndn-refresh-token', data.refreshToken);
  localStorage.setItem('dndn-id-token', data.idToken);
}

function clearTokens() {
  localStorage.removeItem('dndn-access-token');
  localStorage.removeItem('dndn-refresh-token');
  localStorage.removeItem('dndn-id-token');
}

async function fetchMe(): Promise<Session> {
  const res = await apiFetch<ApiMeResponse>('/auth/me');
  const { id, name, email, role, position, company, createdAt } = res.data;
  return {
    id,
    name,
    email,
    role,
    position: position ?? null,
    auth: roleToAuth(role),
    company: { name: company.name, logoUrl: company.logoUrl, logoDarkUrl: company.logoUrl },
    createdAt: createdAt ?? null,
  };
}

async function fetchAllowedMe(): Promise<Session> {
  const me = await fetchMe();
  if (me.role === 'hr') {
    clearTokens();
    throw new Error('HR_ACCESS_DENIED');
  }
  return me;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 앱 초기화 — 저장된 토큰으로 세션 복원
  useEffect(() => {
    const token = localStorage.getItem('dndn-access-token');
    if (!token) { setIsLoading(false); return; }
    fetchAllowedMe()
      .then(setSession)
      .catch(clearTokens)
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const res = await apiFetch<{ success: boolean; data: ApiLoginData | ApiChallengeData }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
    );
    const data = res.data;
    if ('challenge' in data) {
      return { type: 'challenge', session: data.session };
    }
    saveTokens(data as ApiLoginData);
    const me = await fetchAllowedMe();
    setSession(me);
    return { type: 'success' };
  }, []);

  const challenge = useCallback(async (email: string, newPassword: string, sess: string) => {
    const res = await apiFetch<{ success: boolean; data: ApiLoginData }>(
      '/auth/challenge',
      { method: 'POST', body: JSON.stringify({ email, newPassword, session: sess }) },
    );
    saveTokens(res.data);
    const me = await fetchAllowedMe();
    setSession(me);
  }, []);

  const forgotPassword = useCallback(async (email: string): Promise<string> => {
    const res = await apiFetch<{ success: boolean; data: { destination: string } }>(
      '/auth/forgot-password',
      { method: 'POST', body: JSON.stringify({ email }) },
    );
    return res.data.destination;
  }, []);

  const confirmResetPassword = useCallback(async (email: string, code: string, newPassword: string) => {
    await apiFetch(
      '/auth/confirm-reset',
      { method: 'POST', body: JSON.stringify({ email, code, newPassword }) },
    );
  }, []);

  const logout = useCallback(async () => {
    try { await apiFetch('/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
    clearTokens();
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider value={{ session, isLoading, login, challenge, forgotPassword, confirmResetPassword, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
