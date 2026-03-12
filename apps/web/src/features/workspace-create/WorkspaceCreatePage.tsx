import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useSession } from '@/hooks/useSession';
import { WS_ICONS, ICON_KEYS, SVG } from '@/mocks/data/icons.mock';
import type { IconKey } from '@/mocks/types/workspace';
import './WorkspaceCreatePage.css';

const POLICY_ROWS = [
  ['SecurityAudit', 'Security Hub, GuardDuty, Config 읽기'],
  ['cloudtrail:LookupEvents', 'CloudTrail 변경 이력 수집'],
  ['health:Describe*', 'AWS Health 이벤트 수집'],
  ['ce:GetCost*', 'Cost Explorer 비용 데이터 조회'],
  ['inspector2:List*, BatchGet*', 'Inspector 취약점 스캔 결과 조회'],
  ['access-analyzer:List*, Get*', 'IAM Access Analyzer 결과 조회'],
  ['s3:GetObject, PutObject', '보고서 저장 (지정 버킷)'],
];

export function WorkspaceCreatePage() {
  const navigate = useNavigate();
  const session = useSession();

  const [step, setStep] = useState(0);
  const [toast, setToast] = useState<{ msg: string; type: string } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const navTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Step 1: AWS
  const [acctId, setAcctId] = useState('');
  const [awsTesting, setAwsTesting] = useState(false);
  const [awsTested, setAwsTested] = useState(false);
  const [awsError, setAwsError] = useState('');
  const [policyOpen, setPolicyOpen] = useState(false);

  // Step 2: GitHub
  const [ghConnected, setGhConnected] = useState(false);
  const [ghConnecting, setGhConnecting] = useState(false);
  const [ghUsername, setGhUsername] = useState('');
  const [ghToken, setGhToken] = useState('');
  const [org, setOrg] = useState('');
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('');
  const [path, setPath] = useState('');
  const [orgList, setOrgList] = useState<{ login: string; avatarUrl: string | null }[]>([]);
  const [repoList, setRepoList] = useState<{ name: string; private: boolean; defaultBranch: string }[]>([]);
  const [branchList, setBranchList] = useState<{ name: string; isDefault: boolean }[]>([]);

  // Step 3: Profile
  const [alias, setAlias] = useState('');
  const [memo, setMemo] = useState('');
  const [selectedIcon, setSelectedIcon] = useState<IconKey>('cloud');
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const iconAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (session.auth !== 'leader') {
      showToast('접근 권한이 없습니다.', 'warn');
      navigate('/workspace');
    }
  }, [session.auth, navigate]);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (iconAreaRef.current && !iconAreaRef.current.contains(e.target as Node)) setIconPickerOpen(false);
    }
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  useEffect(() => {
    return () => {
      clearTimeout(toastTimer.current);
      clearTimeout(navTimerRef.current);
    };
  }, []);

  const showToast = (msg: string, type = 'warn') => {
    setToast({ msg, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  // AWS — CloudFormation 역할 생성 페이지 열기
  const openCfnLink = async () => {
    const clean = acctId.replace(/\D/g, '');
    if (clean.length !== 12) { showToast('AWS 계정 ID를 12자리로 입력하세요.'); return; }
    try {
      const res = await fetch('/api/workspaces/cfn-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ acctId: clean }),
      });
      const data = await res.json();
      if (data.success) {
        window.open(data.data.url, '_blank');
      } else {
        showToast(data.error?.message || 'URL 생성 실패');
      }
    } catch {
      showToast('서버 연결 실패 — 테스트 서버가 실행 중인지 확인하세요.');
    }
  };

  // AWS — 연동 테스트
  const testAws = async () => {
    const clean = acctId.replace(/\D/g, '');
    if (clean.length !== 12) { showToast('AWS 계정 ID를 12자리로 입력하세요.'); return; }
    setAwsTested(false);
    setAwsError('');
    setAwsTesting(true);
    try {
      const res = await fetch('/api/workspaces/test-aws', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ acctId: clean }),
      });
      const data = await res.json();
      setAwsTesting(false);
      if (data.success) {
        setAwsTested(true);
        setAwsError('');
      } else {
        setAwsError(data.data?.error || '연동 실패 — 스택 생성을 먼저 완료하세요.');
      }
    } catch {
      setAwsTesting(false);
      setAwsError('서버 연결 실패 — 테스트 서버가 실행 중인지 확인하세요.');
    }
  };

  // GitHub connect — OAuth 팝업 방식
  const connectGH = async () => {
    setGhConnecting(true);
    try {
      const res = await fetch('/api/github/auth-url');
      const data = await res.json();
      if (!data.success) { showToast(data.error?.message || 'GitHub 인증 URL 생성 실패'); setGhConnecting(false); return; }

      const { authorizeUrl, state } = data.data;

      // 팝업으로 GitHub 인증 페이지 열기
      const w = 600, h = 700;
      const left = window.screenX + (window.innerWidth - w) / 2;
      const top = window.screenY + (window.innerHeight - h) / 2;
      const popup = window.open(authorizeUrl, 'github-oauth', `width=${w},height=${h},left=${left},top=${top}`);
      if (!popup) {
        showToast('팝업이 차단되었습니다. 팝업 차단을 해제해 주세요.');
        setGhConnecting(false);
        return;
      }

      // 팝업이 사용자에 의해 닫힌 경우 감지
      const popupCheck = setInterval(() => {
        if (popup.closed) {
          clearInterval(popupCheck);
          setGhConnecting(false);
        }
      }, 1000);

      // 콜백 메시지 수신 대기
      const handler = async (e: MessageEvent) => {
        if (e.origin !== window.location.origin || e.data?.type !== 'github-oauth') return;
        window.removeEventListener('message', handler);
        clearInterval(popupCheck);

        const { code, state: returnedState, error } = e.data;
        if (error) { showToast(e.data.errorDescription || 'GitHub 인증이 거부되었습니다.'); setGhConnecting(false); return; }
        if (!code || returnedState !== state) { showToast('GitHub 인증이 취소되었습니다.'); setGhConnecting(false); return; }

        // code → access token 교환
        const exRes = await fetch('/api/github/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, state }),
        });
        const exData = await exRes.json();
        if (!exData.success) { showToast(exData.error?.message || 'GitHub 토큰 교환 실패'); setGhConnecting(false); return; }

        setGhToken(exData.data.accessToken);
        setGhUsername(exData.data.username);
        setGhConnected(true);
        setGhConnecting(false);

        // 조직 목록 자동 로드
        const orgRes = await fetch('/api/github/orgs', { headers: { Authorization: `Bearer ${exData.data.accessToken}` } });
        const orgData = await orgRes.json();
        if (orgData.success) {
          // 본인 계정도 포함
          setOrgList([{ login: exData.data.username, avatarUrl: null }, ...orgData.data]);
        }
      };
      window.addEventListener('message', handler);
    } catch {
      showToast('서버 연결 실패 — 테스트 서버가 실행 중인지 확인하세요.');
      setGhConnecting(false);
    }
  };

  // 조직 선택 시 레포 목록 로드
  const handleOrgChange = async (selectedOrg: string) => {
    setOrg(selectedOrg);
    setRepo('');
    setBranch('');
    setRepoList([]);
    setBranchList([]);
    if (!selectedOrg || !ghToken) return;
    try {
      const res = await fetch(`/api/github/repos?org=${encodeURIComponent(selectedOrg)}`, { headers: { Authorization: `Bearer ${ghToken}` } });
      const data = await res.json();
      if (data.success) setRepoList(data.data);
    } catch { /* ignore */ }
  };

  // 레포 선택 시 브랜치 목록 로드
  const handleRepoChange = async (selectedRepo: string) => {
    setRepo(selectedRepo);
    setBranch('');
    setBranchList([]);
    if (!selectedRepo || !org || !ghToken) return;
    try {
      const res = await fetch(`/api/github/branches?org=${encodeURIComponent(org)}&repo=${encodeURIComponent(selectedRepo)}`, { headers: { Authorization: `Bearer ${ghToken}` } });
      const data = await res.json();
      if (data.success) {
        setBranchList(data.data);
        const defaultBr = (data.data as { name: string; isDefault: boolean }[]).find((b) => b.isDefault);
        if (defaultBr) setBranch(defaultBr.name);
      }
    } catch { /* ignore */ }
  };

  // Validation
  const validateStep = (s: number): boolean => {
    if (s === 0) {
      if (acctId.replace(/\D/g, '').length !== 12) { showToast('AWS 계정 ID를 12자리로 입력하세요.'); return false; }
      if (!awsTested) { showToast('스택 배포 후 연동 테스트를 완료해주세요.'); return false; }
    }
    if (s === 1) {
      if (!ghConnected) { showToast('GitHub 계정을 먼저 연결하세요.'); return false; }
      if (!org) { showToast('GitHub 조직/사용자를 선택하세요.'); return false; }
      if (!repo) { showToast('저장소를 선택하세요.'); return false; }
    }
    return true;
  };

  const nextStep = () => {
    if (!validateStep(step)) return;
    if (step === 2) { createWorkspace(); return; }
    if (step === 1 && !alias) setAlias('Workspace-' + acctId.replace(/\D/g, '').slice(-4));
    setStep(s => s + 1);
  };

  const prevStep = () => {
    if (step === 0) { navigate('/workspace'); return; }
    setStep(s => s - 1);
  };

  const createWorkspace = () => {
    const ws = {
      alias: alias.trim() || 'Workspace-' + acctId.replace(/\D/g, '').slice(-4),
      acctId: acctId.replace(/\D/g, ''),
      githubOrg: org, repo, path: path.trim(), branch: branch || 'main',
      memo: memo.trim(), icon: selectedIcon,
    };
    showToast(`"${ws.alias}" 워크스페이스가 생성되었습니다.`, 'ok');
    navTimerRef.current = setTimeout(() => navigate('/workspace'), 1000);
  };

  const cleanAcct = acctId.replace(/\D/g, '');
  const repoDisplay = [org, repo, path].filter(Boolean).join('/');

  if (session.auth !== 'leader') return null;

  return (
    <div className="wsc-page">
      <div className="wizard">
        <div className="page-header"><div className="page-title">워크스페이스 생성</div></div>

        {/* 스텝 바 */}
        <div className="step-bar">
          {[0, 1, 2].map(i => (
            <div key={i} style={{ display: 'contents' }}>
              {i > 0 && <div className={`step-line${i <= step ? ' done' : ''}`} />}
              <div className={`step-item${i === step ? ' active' : i < step ? ' done' : ''}`}>
                <div className="step-num">{i + 1}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Step 1: AWS */}
        {step === 0 && (
          <div className="step-content active">
            <div className="step-section-title">AWS 계정 연동</div>
            <div className="step-section-desc">AWS 계정에 데이터 수집을 위한 IAM Role을 생성합니다.</div>
            <div className="seq-list">
              <div className="seq-step" data-n="1">
                <div className="seq-label">AWS 계정 ID</div>
                <div className="seq-action">
                  <input className="field-input" type="text" maxLength={12} value={acctId} onChange={(e) => { setAcctId(e.target.value); setAwsTested(false); }} style={{ width: 160, textAlign: 'center', letterSpacing: '1.5px' }} />
                </div>
              </div>
              <div className="seq-step" data-n="2">
                <div className="seq-label">DnDn 연동 역할 배포</div>
                <div className="seq-desc">AWS 콘솔에 로그인한 상태에서 역할 생성 버튼을 클릭하세요.<br />IAM 리소스 생성 승인 체크 후 스택 생성까지 약 1~2분 소요됩니다.</div>
                <div className="policy-wrap">
                  <div className={`policy-toggle${policyOpen ? ' open' : ''}`} onClick={() => setPolicyOpen(p => !p)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setPolicyOpen(p => !p); } }}>
                    <svg className="policy-toggle-arr" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 4l4 4-4 4" /></svg>
                    필요 권한 확인
                  </div>
                  {policyOpen && (
                    <div className="policy-detail" style={{ display: 'block' }}>
                      <table className="policy-table">
                        <thead><tr><th>정책 / 권한</th><th>용도</th></tr></thead>
                        <tbody>{POLICY_ROWS.map(([p, u]) => <tr key={p}><td><code>{p}</code></td><td>{u}</td></tr>)}</tbody>
                      </table>
                      <div className="policy-note">CloudFormation이 IAM Role을 자동으로 생성합니다. 기존 리소스에는 영향을 주지 않습니다.</div>
                    </div>
                  )}
                </div>
                <div className="seq-action">
                  <button className="btn-seq" onClick={openCfnLink}>역할 생성</button>
                </div>
              </div>
              <div className="seq-step" data-n="3">
                <div className="seq-label">연동 확인</div>
                <div className="seq-desc">스택 생성이 완료되면 테스트 버튼으로 연결 상태를 확인합니다.</div>
                <div className="seq-action">
                  {awsTesting && <span className="test-result show" style={{ background: 'var(--bg-alt)', color: 'var(--text-muted)' }}>연동 확인 중...</span>}
                  {awsTested && !awsTesting && <span className="test-result show success">{SVG.check} 연동 성공 — 계정 {cleanAcct}</span>}
                  {awsError && !awsTesting && !awsTested && <span className="test-result show" style={{ background: 'var(--danger-bg, #fef2f2)', color: 'var(--danger, #dc2626)' }}>연동 실패 — 스택생성 여부를 확인하세요</span>}
                  <button className="btn-seq" onClick={testAws}>테스트</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: GitHub */}
        {step === 1 && (
          <div className="step-content active">
            <div className="step-section-title">GitHub 연동</div>
            <div className="step-section-desc">GitHub 계정을 연결하고 저장소를 선택합니다.</div>
            <div className="seq-list">
              <div className="seq-step" data-n="1">
                <div className="seq-label">GitHub 계정 연결</div>
                <div className="seq-desc">GitHub OAuth를 통해 저장소 접근 권한을 부여합니다.</div>
                <div className="seq-action">
                  {ghConnected && <span className="gh-status show ok">{SVG.check} 연결 완료 — {ghUsername}</span>}
                  <button className="btn-seq" onClick={connectGH} disabled={ghConnected || ghConnecting} style={ghConnected ? { opacity: 0.5, pointerEvents: 'none' } : undefined}>
                    {ghConnecting ? '연결 중…' : ghConnected ? '연결됨' : '연결'}
                  </button>
                </div>
              </div>
              <div className="seq-step" data-n="2">
                <div className="seq-label">저장소 선택</div>
                <div className="gh-repo-fields">
                  <div className="field-group">
                    <label className="field-label">조직 / 사용자 <span className="req">*</span></label>
                    <select className="field-input" value={org} onChange={(e) => handleOrgChange(e.target.value)} disabled={!ghConnected}>
                      <option value="">선택하세요</option>
                      {orgList.map(o => <option key={o.login} value={o.login}>{o.login}</option>)}
                    </select>
                  </div>
                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">저장소 <span className="req">*</span></label>
                      <select className="field-input" value={repo} onChange={(e) => handleRepoChange(e.target.value)} disabled={!org}>
                        <option value="">선택하세요</option>
                        {repoList.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
                      </select>
                    </div>
                    <div className="field-group">
                      <label className="field-label">경로</label>
                      <input className="field-input" type="text" placeholder="예: envs/prd" value={path} onChange={(e) => setPath(e.target.value)} disabled={!ghConnected} />
                    </div>
                  </div>
                  <div className="field-group">
                    <label className="field-label">브랜치</label>
                    <select className="field-input" value={branch} onChange={(e) => setBranch(e.target.value)} disabled={!repo}>
                      <option value="">선택하세요</option>
                      {branchList.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Profile */}
        {step === 2 && (
          <div className="step-content active">
            <div className="step-section-title">워크스페이스 기본정보</div>
            <div className="profile-header">
              <div className="profile-icon-area" ref={iconAreaRef}>
                <div className="profile-icon-preview">{WS_ICONS[selectedIcon]}</div>
                <button className="profile-icon-btn" onClick={() => setIconPickerOpen(p => !p)}>변경</button>
                {iconPickerOpen && (
                  <div className="profile-icon-picker open">
                    {ICON_KEYS.map(k => (
                      <div key={k} className={`icon-opt${k === selectedIcon ? ' selected' : ''}`}
                        onClick={() => { setSelectedIcon(k); setIconPickerOpen(false); }}>
                        {WS_ICONS[k]}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="profile-name-area">
                <input className="profile-alias-input" type="text" placeholder="워크스페이스 별칭" value={alias} onChange={(e) => setAlias(e.target.value)} />
                <div className="profile-acct">{cleanAcct} · {repoDisplay}</div>
              </div>
            </div>
            <div className="field-group" style={{ marginTop: 28 }}>
              <label className="field-label">메모</label>
              <textarea className="field-input profile-memo" rows={2} placeholder="이 워크스페이스에 대한 설명" value={memo} onChange={(e) => setMemo(e.target.value)} />
            </div>
            <div className="profile-summary">
              <div className="profile-summary-item">
                <span className="profile-summary-label">AWS</span>
                <span className="profile-summary-val">{cleanAcct}</span>
                <span className="profile-summary-badge ok">연동됨</span>
              </div>
              <div className="profile-summary-item">
                <span className="profile-summary-label">GitHub</span>
                <span className="profile-summary-val">{org}/{repo}{branch && branch !== 'main' ? ` (${branch})` : ''}</span>
                <span className="profile-summary-badge ok">연결됨</span>
              </div>
            </div>
          </div>
        )}

        {/* 하단 버튼 */}
        <div className="wizard-foot">
          <button className="btn-wiz btn-prev" onClick={prevStep}>{step === 0 ? '취소' : '이전'}</button>
          <button className="btn-wiz btn-next" onClick={nextStep}>{step === 2 ? '생성' : '다음'}</button>
        </div>
      </div>
      {toast && createPortal(<div className={`wsc-toast ${toast.type}`} role={toast.type === 'warn' ? 'alert' : 'status'} aria-live="polite">{toast.msg}</div>, document.body)}
    </div>
  );
}
