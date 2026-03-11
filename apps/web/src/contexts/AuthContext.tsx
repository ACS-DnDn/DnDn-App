import { createContext, useState, useEffect, type ReactNode } from 'react';
import type { Session } from '@/mocks';
import { session as mockSession } from '@/mocks';
import { apiFetch } from '@/services/api';

interface AuthContextValue {
  session: Session;
  isAuthenticated: boolean;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  session: mockSession,
  isAuthenticated: false,
  logout: () => {},
});

interface MeResponse {
  success: boolean;
  data: {
    username: string;
    email: string;
    name: string | null;
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>(mockSession);
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => !!localStorage.getItem('dndn-access-token'),
  );

  useEffect(() => {
    const token = localStorage.getItem('dndn-access-token');
    if (!token) return;

    apiFetch<MeResponse>('/auth/me')
      .then((res) => {
        setSession({
          name: res.data.name ?? res.data.username,
          role: '',
          auth: 'user',
          company: mockSession.company,
        });
        setIsAuthenticated(true);
      })
      .catch(() => {
        // 토큰 만료 등 — 로그아웃 처리
        localStorage.removeItem('dndn-access-token');
        localStorage.removeItem('dndn-refresh-token');
        localStorage.removeItem('dndn-id-token');
        setIsAuthenticated(false);
      });
  }, []);

  function logout() {
    apiFetch('/auth/logout', { method: 'POST' }).catch(() => {});
    localStorage.removeItem('dndn-access-token');
    localStorage.removeItem('dndn-refresh-token');
    localStorage.removeItem('dndn-id-token');
    setIsAuthenticated(false);
  }

  return (
    <AuthContext.Provider value={{ session, isAuthenticated, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
