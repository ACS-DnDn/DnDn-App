import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/hooks/useTheme';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import './LoginPage.css';

export function LoginPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const [error, setError] = useState('');
  const [pwResetOpen, setPwResetOpen] = useState(false);
  const [pwStep, setPwStep] = useState<1 | 2>(1);
  const [pwEmail, setPwEmail] = useState('');
  const idRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    const id = idRef.current?.value.trim() ?? '';
    const pw = pwRef.current?.value ?? '';
    if (!id) { setError('아이디를 입력해 주세요.'); idRef.current?.focus(); return; }
    if (!pw) { setError('비밀번호를 입력해 주세요.'); pwRef.current?.focus(); return; }
    // TODO: Cognito authenticateUser 연동
    setError('');
    navigate('/dashboard');
  }

  function openPwReset() {
    setPwStep(1);
    setPwEmail('');
    setPwResetOpen(true);
    setTimeout(() => emailRef.current?.focus(), 50);
  }

  function sendPwReset() {
    if (!pwEmail.trim()) { emailRef.current?.focus(); return; }
    setPwStep(2);
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
            <input className="field-input" ref={idRef} type="text" placeholder="아이디" autoComplete="username" />
          </div>
          <div className="field">
            <input className="field-input" ref={pwRef} type="password" placeholder="비밀번호" autoComplete="current-password" />
            <div className={`error-msg${error ? ' show' : ''}`}>{error}</div>
          </div>
          <button className="btn-login" type="submit">LOGIN</button>
        </form>

        <div className="footer">
          <button type="button" className="link" onClick={openPwReset}>비밀번호를 잊으셨나요?</button>
        </div>
      </div>

      {/* 비밀번호 재설정 팝업 */}
      {pwResetOpen && (
        <div className="pw-overlay open" onClick={(e) => { if (e.target === e.currentTarget) setPwResetOpen(false); }}>
          <div className="pw-modal">
            {pwStep === 1 ? (
              <div className="pw-step active">
                <div className="pw-modal-title">비밀번호 재설정</div>
                <div className="pw-modal-desc">
                  가입 시 사용한 이메일을 입력하면<br />재설정 링크를 보내드립니다.
                </div>
                <div className="pw-input-wrap">
                  <input
                    className="pw-input"
                    ref={emailRef}
                    type="email"
                    placeholder="이메일"
                    autoComplete="email"
                    value={pwEmail}
                    onChange={(e) => setPwEmail(e.target.value)}
                  />
                </div>
                <div className="pw-modal-footer">
                  <button className="pw-btn-cancel" onClick={() => setPwResetOpen(false)}>취소</button>
                  <button className="pw-btn-send" onClick={sendPwReset}>확인</button>
                </div>
              </div>
            ) : (
              <div className="pw-step active">
                <div className="pw-sent-icon">✉</div>
                <div className="pw-modal-title">이메일을 확인해 주세요</div>
                <div className="pw-modal-desc">
                  <span className="pw-sent-email">{pwEmail}</span><br />
                  으로 재설정 링크를 보냈습니다.
                  <div className="pw-sent-note">링크는 30분간 유효합니다.</div>
                </div>
                <div className="pw-modal-footer">
                  <button className="pw-btn-send" onClick={() => setPwResetOpen(false)}>확인</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="version">DnDn v2.0</div>
    </>
  );
}
