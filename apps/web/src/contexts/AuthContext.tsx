import { createContext, type ReactNode, useMemo } from 'react';
import { AuthProvider as OidcProvider, useAuth as useOidc } from 'react-oidc-context';
import type { Session } from '@/mocks';
import { session as mockSession } from '@/mocks';

const cognitoAuthority = `https://cognito-idp.ap-northeast-2.amazonaws.com/ap-northeast-2_C9WPeY6sO`;

const oidcConfig = {
  authority: cognitoAuthority,
  client_id: '4q4nv54rihlt94u65ep005t8a1',
  redirect_uri: window.location.origin + '/',
  response_type: 'code',
  scope: 'openid profile email',
  post_logout_redirect_uri: window.location.origin + '/login',
};

interface AuthContextValue {
  session: Session;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  session: mockSession,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: () => {},
});

function AuthInner({ children }: { children: ReactNode }) {
  const oidc = useOidc();

  const session: Session = useMemo(() => {
    if (!oidc.user) return mockSession;

    const profile = oidc.user.profile;
    const groups: string[] = (profile['cognito:groups'] as string[]) ?? [];
    const auth = groups.includes('leader') ? 'leader' : 'user';

    return {
      name: (profile.name as string) ?? (profile.email as string) ?? '사용자',
      role: auth === 'leader' ? '팀장' : '팀원',
      auth: auth as Session['auth'],
      company: mockSession.company, // TODO: API 연동 시 실제 회사 정보로 교체
    };
  }, [oidc.user]);

  const value: AuthContextValue = useMemo(
    () => ({
      session,
      isAuthenticated: oidc.isAuthenticated,
      isLoading: oidc.isLoading,
      login: () => oidc.signinRedirect(),
      logout: () =>
        oidc.signoutRedirect({
          post_logout_redirect_uri: window.location.origin + '/login',
        }),
    }),
    [session, oidc.isAuthenticated, oidc.isLoading, oidc.signinRedirect, oidc.signoutRedirect],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <OidcProvider {...oidcConfig}>
      <AuthInner>{children}</AuthInner>
    </OidcProvider>
  );
}
