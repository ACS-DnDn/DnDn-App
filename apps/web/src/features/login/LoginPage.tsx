import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/hooks/useTheme';
import { useAuth } from '@/hooks/useAuth';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import './LoginPage.css';

export function LoginPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const { login, challenge } = useAuth();

  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);
  const newPwRef = useRef<HTMLInputElement>(null);

  // challenge 상태 (NEW_PASSWORD_REQUIRED)
  const [challengeMode, setChallengeMode] = useState(false);
  const [challengeSession, setChallengeSession] = useState('');
  const [challengeEmail, setChallengeEmail] = useState('');

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    const email = emailRef.current?.value.trim() ?? '';
    const pw = pwRef.current?.value ?? '';
    if (!email) { setError('이메일을 입력해 주세요.'); emailRef.current?.focus(); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('올바른 이메일 형식을 입력해 주세요.'); emailRef.current?.focus(); return; }
    if (!pw) { setError('비밀번호를 입력해 주세요.'); pwRef.current?.focus(); return; }

    setError('');
    setIsLoading(true);
    try {
      const result = await login(email, pw);
      if (result.type === 'challenge') {
        setChallengeEmail(email);
        setChallengeSession(result.session);
        setChallengeMode(true);
      } else {
        navigate('/dashboard');
      }
    } catch {
      setError('이메일 또는 비밀번호가 올바르지 않습니다.');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleChallenge(e: React.FormEvent) {
    e.preventDefault();
    const newPw = newPwRef.current?.value ?? '';
    if (!newPw) { setError('새 비밀번호를 입력해 주세요.'); newPwRef.current?.focus(); return; }

    setError('');
    setIsLoading(true);
    try {
      await challenge(challengeEmail, newPw, challengeSession);
      navigate('/dashboard');
    } catch {
      setError('비밀번호 변경에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setIsLoading(false);
    }
  }

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

        {!challengeMode ? (
          <form className="form" onSubmit={handleLogin} noValidate>
            <div className="field">
              <input className="field-input" ref={emailRef} type="email" placeholder="이메일" autoComplete="email" />
            </div>
            <div className="field">
              <input className="field-input" ref={pwRef} type="password" placeholder="비밀번호" autoComplete="current-password" />
              <div className={`error-msg${error ? ' show' : ''}`}>{error}</div>
            </div>
            <button className="btn-login" type="submit" disabled={isLoading}>
              {isLoading ? '로그인 중...' : 'LOGIN'}
            </button>
          </form>
        ) : (
          <form className="form" onSubmit={handleChallenge} noValidate>
            <p className="field-input" style={{ fontSize: '0.85rem', marginBottom: '8px', opacity: 0.7 }}>
              첫 로그인입니다. 새 비밀번호를 설정해 주세요.
            </p>
            <div className="field">
              <input className="field-input" ref={newPwRef} type="password" placeholder="새 비밀번호" autoComplete="new-password" />
              <div className={`error-msg${error ? ' show' : ''}`}>{error}</div>
            </div>
            <button className="btn-login" type="submit" disabled={isLoading}>
              {isLoading ? '처리 중...' : '비밀번호 설정'}
            </button>
          </form>
        )}
      </div>

      <div className="version">DnDn v2.0</div>
    </>
  );
}
