import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/hooks/useTheme';
import { useAuth } from '@/hooks/useAuth';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import './LoginPage.css';

export function LoginPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const { isAuthenticated, isLoading, login } = useAuth();

  useEffect(() => {
    if (isAuthenticated) navigate('/dashboard', { replace: true });
  }, [isAuthenticated, navigate]);

  return (
    <>
      <button type="button" className="mode-toggle" onClick={toggle} aria-label={isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}>
        <div className="toggle-track"><div className="toggle-thumb" /></div>
      </button>

      <div className="glow" />

      <div className="login-container">
        <div className="logo-wrap">
          <AnimatedLogo variant={isDark ? 'dark' : 'light'} className="login-logo-obj" />
        </div>

        <button
          className="btn-login"
          type="button"
          onClick={login}
        >
          Sign in
        </button>
      </div>

      <div className="version">DnDn v2.0</div>
    </>
  );
}
