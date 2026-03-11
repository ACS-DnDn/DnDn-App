import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/hooks/useTheme';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import { apiFetch } from '@/services/api';
import './LoginPage.css';

interface LoginSuccess {
  success: boolean;
  data: {
    accessToken: string;
    refreshToken: string;
    idToken: string;
    expiresIn: number;
  };
}

interface ChallengeNeeded {
  success: boolean;
  data: {
    challenge: string;
    session: string;
  };
}

type LoginApiResponse = LoginSuccess | ChallengeNeeded;

function isChallenge(res: LoginApiResponse): res is ChallengeNeeded {
  return 'challenge' in res.data;
}

const PW_RULES = [
  { label: '8자 이상', test: (v: string) => v.length >= 8 },
  { label: '영문 대문자 포함', test: (v: string) => /[A-Z]/.test(v) },
  { label: '영문 소문자 포함', test: (v: string) => /[a-z]/.test(v) },
  { label: '숫자 포함', test: (v: string) => /\d/.test(v) },
  { label: '특수문자 포함', test: (v: string) => /[^A-Za-z0-9]/.test(v) },
];

export function LoginPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);

  // 비밀번호 변경 모달 상태
  const [challenge, setChallenge] = useState<{ session: string; email: string } | null>(null);
  const [modalError, setModalError] = useState('');
  const [modalLoading, setModalLoading] = useState(false);
  const curPwRef = useRef<HTMLInputElement>(null);
  const newPwRef = useRef<HTMLInputElement>(null);
  const confirmPwRef = useRef<HTMLInputElement>(null);
  const [newPwValue, setNewPwValue] = useState('');
  const [confirmPwValue, setConfirmPwValue] = useState('');
  const [showRules, setShowRules] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    const email = emailRef.current?.value.trim() ?? '';
    const pw = pwRef.current?.value ?? '';

    if (!email) { setError('이메일을 입력해 주세요.'); emailRef.current?.focus(); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('올바른 이메일 형식을 입력해 주세요.'); emailRef.current?.focus(); return; }
    if (!pw) { setError('비밀번호를 입력해 주세요.'); pwRef.current?.focus(); return; }

    setError('');
    setLoading(true);

    try {
      const res = await apiFetch<LoginApiResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password: pw }),
      });

      if (isChallenge(res)) {
        setChallenge({ session: res.data.session, email });
        setLoading(false);
        return;
      }

      localStorage.setItem('dndn-access-token', res.data.accessToken);
      localStorage.setItem('dndn-refresh-token', res.data.refreshToken);
      localStorage.setItem('dndn-id-token', res.data.idToken);
      navigate('/dashboard');
    } catch {
      setError('이메일 또는 비밀번호가 올바르지 않습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (!challenge) return;

    const curPw = curPwRef.current?.value ?? '';
    const newPw = newPwRef.current?.value ?? '';
    const confirmPw = confirmPwRef.current?.value ?? '';

    if (!curPw) { setModalError('현재 비밀번호를 입력해 주세요.'); curPwRef.current?.focus(); return; }
    if (!newPw) { setModalError('새 비밀번호를 입력해 주세요.'); newPwRef.current?.focus(); return; }

    const failedRule = PW_RULES.find((r) => !r.test(newPw));
    if (failedRule) { setModalError(`${failedRule.label} 조건을 충족해야 합니다.`); newPwRef.current?.focus(); return; }

    if (newPw !== confirmPw) { setModalError('비밀번호가 일치하지 않습니다.'); confirmPwRef.current?.focus(); return; }

    setModalError('');
    setModalLoading(true);

    try {
      const res = await apiFetch<LoginSuccess>('/auth/challenge', {
        method: 'POST',
        body: JSON.stringify({
          email: challenge.email,
          newPassword: newPw,
          session: challenge.session,
        }),
      });

      localStorage.setItem('dndn-access-token', res.data.accessToken);
      localStorage.setItem('dndn-refresh-token', res.data.refreshToken);
      localStorage.setItem('dndn-id-token', res.data.idToken);
      navigate('/dashboard');
    } catch {
      setModalError('비밀번호 변경에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setModalLoading(false);
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

        <form className="form" onSubmit={handleLogin} noValidate>
          <div className="field">
            <input className="field-input" ref={emailRef} type="email" placeholder="이메일" autoComplete="email" />
          </div>
          <div className="field">
            <input className="field-input" ref={pwRef} type="password" placeholder="비밀번호" autoComplete="current-password" />
            <div className={`error-msg${error ? ' show' : ''}`}>{error}</div>
          </div>
          <button className="btn-login" type="submit" disabled={loading}>
            {loading ? '로그인 중...' : 'LOGIN'}
          </button>
        </form>
      </div>

      <div className="version">DnDn v2.0</div>

      {/* ── 비밀번호 변경 모달 ── */}
      {challenge && (
        <div className="pw-modal-overlay">
          <div className="pw-modal">
            <h3 className="pw-modal-title">비밀번호를 변경해주세요</h3>
            <form onSubmit={handleChangePassword} noValidate>
              <div className="pw-modal-field">
                <input
                  className="pw-modal-input"
                  ref={curPwRef}
                  type="password"
                  placeholder="현재 비밀번호"
                  autoComplete="current-password"
                  autoFocus
                />
              </div>
              <div className="pw-modal-field pw-modal-field--has-rules pw-modal-field--toggle">
                <input
                  className="pw-modal-input"
                  ref={newPwRef}
                  type={showNewPw ? 'text' : 'password'}
                  placeholder="새 비밀번호"
                  autoComplete="new-password"
                  value={newPwValue}
                  onChange={(e) => setNewPwValue(e.target.value)}
                  onFocus={() => setShowRules(true)}
                  onBlur={() => setShowRules(false)}
                />
                <button type="button" className={`pw-eye-btn${showNewPw ? ' pw-eye-btn--active' : ''}`} onClick={() => setShowNewPw(!showNewPw)} tabIndex={-1} aria-label={showNewPw ? '비밀번호 숨기기' : '비밀번호 보기'}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                </button>
                {showRules && (
                  <div className="pw-rules-tooltip">
                    {PW_RULES.map((rule) => {
                      const passed = rule.test(newPwValue);
                      return (
                        <div key={rule.label} className={`pw-rule ${passed ? 'pw-rule--pass' : ''}`}>
                          <span className="pw-rule-icon">{passed ? '✓' : '✗'}</span>
                          {rule.label}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              <div className="pw-modal-field pw-modal-field--toggle">
                <input
                  className="pw-modal-input"
                  ref={confirmPwRef}
                  type={showConfirmPw ? 'text' : 'password'}
                  placeholder="새 비밀번호 확인"
                  autoComplete="new-password"
                  value={confirmPwValue}
                  onChange={(e) => setConfirmPwValue(e.target.value)}
                />
                {confirmPwValue && newPwValue && confirmPwValue === newPwValue && (
                  <span className="pw-match-icon">✓</span>
                )}
                <button type="button" className={`pw-eye-btn${showConfirmPw ? ' pw-eye-btn--active' : ''}`} onClick={() => setShowConfirmPw(!showConfirmPw)} tabIndex={-1} aria-label={showConfirmPw ? '비밀번호 숨기기' : '비밀번호 보기'}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                </button>
              </div>
              <p className={`pw-modal-error${modalError ? ' pw-modal-error--show' : ''}`}>{modalError || '\u00A0'}</p>
              <button className="pw-modal-btn" type="submit" disabled={modalLoading}>
                {modalLoading ? '변경 중...' : '비밀번호 변경'}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
