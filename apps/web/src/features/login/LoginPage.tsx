import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/hooks/useTheme';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import './LoginPage.css';

export function LoginPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const [error, setError] = useState('');
  const emailRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    const email = emailRef.current?.value.trim() ?? '';
    const pw = pwRef.current?.value ?? '';
    if (!email) { setError('이메일을 입력해 주세요.'); emailRef.current?.focus(); return; }
    if (!pw) { setError('비밀번호를 입력해 주세요.'); pwRef.current?.focus(); return; }
    // TODO: Cognito Custom UI 연동
    setError('');
    navigate('/dashboard');
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

        <form className="form" onSubmit={handleLogin}>
          <div className="field">
            <input className="field-input" ref={emailRef} type="email" placeholder="이메일" autoComplete="email" />
          </div>
          <div className="field">
            <input className="field-input" ref={pwRef} type="password" placeholder="비밀번호" autoComplete="current-password" />
            <div className={`error-msg${error ? ' show' : ''}`}>{error}</div>
          </div>
          <button className="btn-login" type="submit">LOGIN</button>
        </form>
      </div>

      <div className="version">DnDn v2.0</div>
    </>
  );
}
