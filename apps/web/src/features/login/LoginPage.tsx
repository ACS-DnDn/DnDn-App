import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/hooks/useTheme';
import { useAuth } from '@/hooks/useAuth';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import './LoginPage.css';

const PW_RULES = [
  { label: '8자 이상', test: (v: string) => v.length >= 8 },
  { label: '영문 대문자 포함', test: (v: string) => /[A-Z]/.test(v) },
  { label: '영문 소문자 포함', test: (v: string) => /[a-z]/.test(v) },
  { label: '숫자 포함', test: (v: string) => /\d/.test(v) },
  { label: '특수문자 포함', test: (v: string) => /[^A-Za-z0-9]/.test(v) },
];

type PageMode = 'login' | 'challenge' | 'forgot' | 'reset';

export function LoginPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();
  const { login, challenge, forgotPassword, confirmResetPassword } = useAuth();

  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);

  // 페이지 모드
  const [mode, setMode] = useState<PageMode>('login');

  // challenge 상태 (NEW_PASSWORD_REQUIRED)
  const [challengeSession, setChallengeSession] = useState('');
  const [challengeEmail, setChallengeEmail] = useState('');

  // forgot password 상태
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotDestination, setForgotDestination] = useState('');

  // reset 상태
  const [resetCode, setResetCode] = useState('');

  // 모달 상태 (challenge + reset 공용)
  const [modalError, setModalError] = useState('');
  const [modalLoading, setModalLoading] = useState(false);
  const newPwRef = useRef<HTMLInputElement>(null);
  const confirmPwRef = useRef<HTMLInputElement>(null);
  const [newPwValue, setNewPwValue] = useState('');
  const [confirmPwValue, setConfirmPwValue] = useState('');
  const [showRules, setShowRules] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);

  function resetModalState() {
    setModalError('');
    setModalLoading(false);
    setNewPwValue('');
    setConfirmPwValue('');
    setShowRules(false);
    setShowNewPw(false);
    setShowConfirmPw(false);
  }

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
        resetModalState();
        setMode('challenge');
      } else {
        navigate('/dashboard');
      }
    } catch (e) {
      if (e instanceof Error && e.message === 'HR_ACCESS_DENIED') {
        setError('HR 관리자는 DnDn HR에서 로그인해 주세요.');
      } else {
        setError('이메일 또는 비밀번호가 올바르지 않습니다.');
      }
    } finally {
      setIsLoading(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    const newPw = newPwRef.current?.value ?? '';
    const confirmPw = confirmPwRef.current?.value ?? '';

    if (!newPw) { setModalError('새 비밀번호를 입력해 주세요.'); newPwRef.current?.focus(); return; }

    const failedRule = PW_RULES.find((r) => !r.test(newPw));
    if (failedRule) { setModalError(`${failedRule.label} 조건을 충족해야 합니다.`); newPwRef.current?.focus(); return; }

    if (newPw !== confirmPw) { setModalError('비밀번호가 일치하지 않습니다.'); confirmPwRef.current?.focus(); return; }

    setModalError('');
    setModalLoading(true);
    try {
      await challenge(challengeEmail, newPw, challengeSession);
      navigate('/dashboard');
    } catch (e) {
      if (e instanceof Error && e.message === 'HR_ACCESS_DENIED') {
        setModalError('HR 계정은 DnDn HR 서비스를 이용해 주세요.');
      } else {
        setModalError('비밀번호 변경에 실패했습니다. 다시 시도해 주세요.');
      }
    } finally {
      setModalLoading(false);
    }
  }

  async function handleForgotPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!forgotEmail) { setError('이메일을 입력해 주세요.'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(forgotEmail)) { setError('올바른 이메일 형식을 입력해 주세요.'); return; }

    setError('');
    setIsLoading(true);
    try {
      const destination = await forgotPassword(forgotEmail);
      setForgotDestination(destination);
      resetModalState();
      setResetCode('');
      setMode('reset');
    } catch {
      setError('인증 코드 발송에 실패했습니다. 이메일을 확인해 주세요.');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleConfirmReset(e: React.FormEvent) {
    e.preventDefault();
    const newPw = newPwRef.current?.value ?? '';
    const confirmPw = confirmPwRef.current?.value ?? '';

    if (!resetCode.trim()) { setModalError('인증 코드를 입력해 주세요.'); return; }
    if (!newPw) { setModalError('새 비밀번호를 입력해 주세요.'); newPwRef.current?.focus(); return; }

    const failedRule = PW_RULES.find((r) => !r.test(newPw));
    if (failedRule) { setModalError(`${failedRule.label} 조건을 충족해야 합니다.`); newPwRef.current?.focus(); return; }

    if (newPw !== confirmPw) { setModalError('비밀번호가 일치하지 않습니다.'); confirmPwRef.current?.focus(); return; }

    setModalError('');
    setModalLoading(true);
    try {
      await confirmResetPassword(forgotEmail, resetCode.trim(), newPw);
      setMode('login');
      setError('');
      // 비밀번호 변경 성공 메시지를 login 화면 에러 영역에 표시 (초록색 아님, 단순 안내)
      setError('비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요.');
    } catch {
      setModalError('비밀번호 재설정에 실패했습니다. 인증 코드를 확인해 주세요.');
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

        {mode === 'login' && (
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
            <button type="button" className="forgot-link" onClick={() => { setMode('forgot'); setError(''); setForgotEmail(''); }}>
              비밀번호를 잊으셨나요?
            </button>
          </form>
        )}

        {mode === 'forgot' && (
          <form className="form" onSubmit={handleForgotPassword} noValidate>
            <p className="forgot-desc">가입한 이메일을 입력하면 비밀번호 재설정 코드를 보내드립니다.</p>
            <div className="field">
              <input
                className="field-input"
                type="email"
                placeholder="이메일"
                autoComplete="email"
                autoFocus
                value={forgotEmail}
                onChange={(e) => setForgotEmail(e.target.value)}
              />
              <div className={`error-msg${error ? ' show' : ''}`}>{error}</div>
            </div>
            <button className="btn-login" type="submit" disabled={isLoading}>
              {isLoading ? '발송 중...' : '인증 코드 발송'}
            </button>
            <button type="button" className="forgot-link" onClick={() => { setMode('login'); setError(''); }}>
              로그인으로 돌아가기
            </button>
          </form>
        )}
      </div>

      <div className="version">DnDn v2.0</div>

      <div className="service-links">
        <a href="https://console.aws.amazon.com" target="_blank" rel="noopener noreferrer" className="service-link" aria-label="AWS Console">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" className="service-logo service-logo-aws">
            <path d="M6.763 10.036c0 .296.032.535.088.71.064.176.144.368.256.576.04.064.056.128.056.184 0 .08-.048.16-.152.24l-.504.336a.383.383 0 0 1-.208.072c-.08 0-.16-.04-.24-.112a2.47 2.47 0 0 1-.288-.376 6.18 6.18 0 0 1-.248-.471c-.622.734-1.405 1.1-2.347 1.1-.67 0-1.205-.191-1.596-.574-.391-.384-.59-.894-.59-1.533 0-.678.239-1.23.726-1.644.487-.415 1.133-.623 1.955-.623.272 0 .551.024.846.064.296.04.6.104.918.176v-.583c0-.607-.127-1.03-.375-1.277-.255-.248-.686-.367-1.3-.367-.28 0-.568.031-.863.103-.295.072-.583.16-.862.272a2.287 2.287 0 0 1-.28.104.488.488 0 0 1-.127.023c-.112 0-.168-.08-.168-.247v-.391c0-.128.016-.224.056-.28a.597.597 0 0 1 .224-.167c.279-.144.614-.264 1.005-.36a4.84 4.84 0 0 1 1.246-.151c.95 0 1.644.216 2.091.647.439.43.662 1.085.662 1.963zm-3.24 1.214c.263 0 .534-.048.822-.144.287-.096.543-.271.758-.51.128-.152.224-.32.272-.512.047-.191.08-.423.08-.694v-.335a6.66 6.66 0 0 0-.735-.136 6.02 6.02 0 0 0-.75-.048c-.535 0-.926.104-1.19.32-.263.215-.39.518-.39.917 0 .375.095.655.295.846.191.2.47.296.838.296zm6.41.862c-.144 0-.24-.024-.304-.08-.064-.048-.12-.16-.168-.311L7.586 5.55a1.398 1.398 0 0 1-.072-.32c0-.128.064-.2.191-.2h.783c.151 0 .255.025.31.08.065.048.113.16.16.312l1.342 5.284 1.245-5.284c.04-.16.088-.264.151-.312a.549.549 0 0 1 .32-.08h.638c.152 0 .256.025.32.08.063.048.12.16.151.312l1.261 5.348 1.381-5.348c.048-.16.104-.264.16-.312a.52.52 0 0 1 .311-.08h.743c.127 0 .2.065.2.2 0 .04-.009.08-.017.128a1.137 1.137 0 0 1-.056.2l-1.923 6.17c-.048.16-.104.263-.168.311a.51.51 0 0 1-.303.08h-.687c-.151 0-.255-.024-.32-.08-.063-.056-.119-.16-.15-.32l-1.238-5.148-1.23 5.14c-.04.16-.087.264-.15.32-.065.056-.177.08-.32.08zm10.256.215c-.415 0-.83-.048-1.229-.143-.399-.096-.71-.2-.918-.32-.128-.071-.215-.151-.247-.223a.563.563 0 0 1-.048-.224v-.407c0-.167.064-.247.183-.247.048 0 .096.008.144.024.048.016.12.048.2.08.271.12.566.215.878.279.319.064.63.096.95.096.502 0 .894-.088 1.165-.264a.86.86 0 0 0 .41-.758.777.777 0 0 0-.215-.559c-.144-.151-.416-.287-.807-.415l-1.157-.36c-.583-.183-1.014-.454-1.277-.813a1.902 1.902 0 0 1-.4-1.158c0-.335.073-.63.216-.886.144-.255.335-.479.575-.654.24-.184.51-.32.83-.415.32-.096.655-.136 1.006-.136.175 0 .359.008.535.032.183.024.35.056.518.088.16.04.312.08.455.127.144.048.256.096.336.144a.69.69 0 0 1 .24.2.43.43 0 0 1 .071.263v.375c0 .168-.064.256-.184.256a.83.83 0 0 1-.303-.096 3.652 3.652 0 0 0-1.532-.311c-.455 0-.815.071-1.062.223-.248.152-.375.383-.375.71 0 .224.08.416.24.567.159.152.454.304.877.44l1.134.358c.574.184.99.44 1.237.767.247.327.367.702.367 1.117 0 .343-.072.655-.207.926-.144.272-.336.511-.583.703-.248.2-.543.343-.886.447-.36.111-.743.167-1.15.167zM21.4 16.459c-2.574 1.894-6.313 2.897-9.527 2.897-4.505 0-8.56-1.663-11.623-4.426-.241-.216-.025-.51.263-.343 3.311 1.926 7.399 3.087 11.63 3.087 2.85 0 5.986-.591 8.874-1.815.438-.175.806.287.383.6zm1.093-1.239c-.328-.422-2.168-.199-2.993-.1-.251.031-.29-.19-.063-.35 1.462-1.027 3.864-.73 4.144-.387.281.35-.074 2.75-1.45 3.899-.21.177-.41.083-.317-.15.31-.77 1.006-2.5.679-2.912z" fill="#FF9900"/>
          </svg>
        </a>

        <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="service-link" aria-label="GitHub">
          <svg viewBox="0 0 98 96" xmlns="http://www.w3.org/2000/svg" className="service-logo service-logo-github">
            <path fillRule="evenodd" clipRule="evenodd" d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z" fill="currentColor"/>
          </svg>
        </a>

        <a href="https://www.dndnhr.cloud" target="_blank" rel="noopener noreferrer" className="service-link" aria-label="DnDn HR">
          <object
            data={isDark ? '/logo-hr-dark.svg' : '/logo-hr-light.svg'}
            type="image/svg+xml"
            className="service-logo service-logo-hr"
            aria-label="DnDn HR"
          />
        </a>
      </div>

      {/* ── 비밀번호 변경 모달 (challenge) ── */}
      {mode === 'challenge' && (
        <div className="pw-modal-overlay">
          <div className="pw-modal">
            <h3 className="pw-modal-title">비밀번호를 변경해주세요</h3>
            <form onSubmit={handleChangePassword} noValidate>
              <div className="pw-modal-field pw-modal-field--has-rules pw-modal-field--toggle">
                <input
                  className="pw-modal-input"
                  ref={newPwRef}
                  type={showNewPw ? 'text' : 'password'}
                  placeholder="새 비밀번호"
                  autoComplete="new-password"
                  autoFocus
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

      {/* ── 비밀번호 재설정 모달 (코드 + 새 비밀번호) ── */}
      {mode === 'reset' && (
        <div className="pw-modal-overlay">
          <div className="pw-modal">
            <h3 className="pw-modal-title">비밀번호 재설정</h3>
            <p className="pw-modal-desc">{forgotDestination}으로 발송된 인증 코드를 입력해 주세요.</p>
            <form onSubmit={handleConfirmReset} noValidate>
              <div className="pw-modal-field">
                <input
                  className="pw-modal-input"
                  type="text"
                  placeholder="인증 코드"
                  autoComplete="one-time-code"
                  autoFocus
                  value={resetCode}
                  onChange={(e) => setResetCode(e.target.value)}
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
              <button type="button" className="pw-modal-back" onClick={() => { setMode('login'); setError(''); }}>
                로그인으로 돌아가기
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
