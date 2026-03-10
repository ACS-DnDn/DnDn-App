import { createContext, type ReactNode } from 'react';
import type { Session } from '@/mocks';
import { session as mockSession } from '@/mocks';

interface AuthContextValue {
  session: Session;
}

export const AuthContext = createContext<AuthContextValue>({
  session: mockSession,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  // TODO: API 연동 시 fetch('/api/me')로 교체
  const session = mockSession;

  return (
    <AuthContext.Provider value={{ session }}>
      {children}
    </AuthContext.Provider>
  );
}
