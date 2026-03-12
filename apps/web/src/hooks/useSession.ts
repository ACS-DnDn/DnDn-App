import { useContext } from 'react';
import { AuthContext } from '@/contexts/AuthContext';
import type { Session } from '@/mocks';

/** Protected routes only — asserts session is non-null (enforced by RequireAuth). */
export function useSession(): Session {
  const { session } = useContext(AuthContext);
  if (!session) throw new Error('useSession must be called inside a protected route');
  return session;
}
