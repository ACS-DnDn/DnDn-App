import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { MOCK_GH } from '@/mocks/data/workspace.mock';
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
  const { session } = useAuth();

  const [step, setStep] = useState(0);
  const [toast, setToast] = useState<{ msg: string; type: string } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Step 1: AWS
  const [acctId, setAcctId] = useState('');
  const [awsTesting, setAwsTesting] = useState(false);
  const [awsTested, setAwsTested] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);

  // Step 2: GitHub
  const [ghConnected, setGhConnected] = useState(false);
  const [ghConnecting, setGhConnecting] = useState(false);
  const [org, setOrg] = useState('');
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('');
  const [path, setPath] = useState('');

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

  const showToast = (msg: string, type = 'warn') => {
    setToast({ msg, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  // AWS test
  const testAws = () => {
    const clean = acctId.replace(/\D/g, '');
    if (clean.length !== 12) { showToast('AWS 계정 ID를 12자리로 입력하세요.'); return; }
    setAwsTesting(true);
    setTimeout(() => { setAwsTesting(false); setAwsTested(true); }, 1200);
  };

  // GitHub connect
  const connectGH = () => {
    setGhConnecting(true);
    setTimeout(() => { setGhConnecting(false); setGhConnected(true); }, 1500);
  };

  const orgRepos = org ? (MOCK_GH.repos[org] || []) : [];
  const repoBranches = repo ? (MOCK_GH.branches[repo] || []) : [];

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
    setTimeout(() => navigate('/workspace'), 1000);
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
                  <div className={`policy-toggle${policyOpen ? ' open' : ''}`} onClick={() => setPolicyOpen(p => !p)}>
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
                  <a className="btn-seq" href="#" onClick={(e) => { e.preventDefault(); window.open('https://ap-northeast-2.console.aws.amazon.com/cloudformation/home', '_blank'); }}>역할 생성</a>
                </div>
              </div>
              <div className="seq-step" data-n="3">
                <div className="seq-label">연동 확인</div>
                <div className="seq-desc">스택 생성이 완료되면 테스트 버튼으로 연결 상태를 확인합니다.</div>
                <div className="seq-action">
                  {awsTesting && <span className="test-result show" style={{ background: 'var(--bg-alt)', color: 'var(--text-muted)' }}>연동 확인 중...</span>}
                  {awsTested && !awsTesting && <span className="test-result show success">{SVG.check} 연동 성공 — 계정 {cleanAcct}</span>}
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
                  {ghConnected && <span className="gh-status show ok">{SVG.check} 연결 완료</span>}
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
                    <select className="field-input" value={org} onChange={(e) => { setOrg(e.target.value); setRepo(''); setBranch(''); }} disabled={!ghConnected}>
                      <option value="">선택하세요</option>
                      {MOCK_GH.orgs.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">저장소 <span className="req">*</span></label>
                      <select className="field-input" value={repo} onChange={(e) => { setRepo(e.target.value); setBranch(''); }} disabled={!org}>
                        <option value="">선택하세요</option>
                        {orgRepos.map(r => <option key={r} value={r}>{r}</option>)}
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
                      {repoBranches.map(b => <option key={b} value={b}>{b}</option>)}
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

      {toast && <div className={`toast ${toast.type} show`}>{toast.msg}</div>}
    </div>
  );
}
