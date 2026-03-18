import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { getWorkspaces } from '@/services/workspace.service';
import { getReportSettings } from '@/services/report.service';
import { WS_ICONS, ICON_KEYS } from '@/mocks/data/icons.mock';
import type { Workspace, IconKey } from '@/mocks/types/workspace';
import type { OpaCategory, OpaItem, OpaSeverity } from '@/mocks/types/report';
import './WorkspacePage.css';

const OPA_ICONS: Record<string, ReactNode> = {
  '네트워크 보안': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 1.5l5.5 2.5v4c0 3-2.2 5.5-5.5 6.5-3.3-1-5.5-3.5-5.5-6.5V4z"/></svg>,
  'IAM 보안': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="4" y="7" width="8" height="7" rx="1"/><path d="M6 7V5a2 2 0 014 0v2"/></svg>,
  '스토리지 보안': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 4l6-2 6 2v8l-6 2-6-2z"/><path d="M2 4l6 2 6-2M8 6v8"/></svg>,
  '컴퓨팅 제어': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 6h6M5 8h6M5 10h4"/></svg>,
  '로깅 / 모니터링': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 12l4-4 3 3 5-6"/><path d="M10 5h4v4"/></svg>,
  '비용 관리': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 4v8M6 6h3.5a1.5 1.5 0 010 3H6.5h3a1.5 1.5 0 010 3H6"/></svg>,
  '가용성': <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><ellipse cx="8" cy="4" rx="6" ry="2"/><path d="M2 4v4c0 1.1 2.7 2 6 2s6-.9 6-2V4"/><path d="M2 8v4c0 1.1 2.7 2 6 2s6-.9 6-2V8"/></svg>,
};

export function WorkspacePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { session } = useAuth();

  const sectionParam = searchParams.get('section');
  const section = sectionParam === 'opa' ? 'opa' : 'general';
  const [account, setAccount] = useState<Workspace | null>(null);

  // 모달
  const [modalOpen, setModalOpen] = useState(false);
  const [modalAlias, setModalAlias] = useState('');
  const [modalMemo, setModalMemo] = useState('');
  const [selectedIcon, setSelectedIcon] = useState<IconKey>('rocket');
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const iconAreaRef = useRef<HTMLDivElement>(null);

  // OPA
  const [opaData, setOpaData] = useState<OpaCategory[]>([]);
  const [closedItems, setClosedItems] = useState<Set<string>>(() => new Set());

  // 토스트
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'warn' } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const ws = getWorkspaces();
    if (ws.length > 0) setAccount({ ...ws[0]! });
    const settings = getReportSettings();
    setOpaData(JSON.parse(JSON.stringify(settings.opa)));
    // 기본으로 모든 아이템 접힘
    const allKeys = settings.opa.flatMap(g => g.items.map(i => i.key));
    setClosedItems(new Set(allKeys));
  }, []);

  // 아이콘 피커 외부 클릭
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (iconAreaRef.current && !iconAreaRef.current.contains(e.target as Node)) setIconPickerOpen(false);
    }
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  useEffect(() => {
    return () => { clearTimeout(toastTimer.current); };
  }, []);

  const showToast = useCallback((msg: string, type: 'ok' | 'warn' = 'warn') => {
    setToast({ msg, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  // 모달
  const openEditModal = () => {
    if (session.auth !== 'leader') { showToast('접근 권한이 없습니다.'); return; }
    if (!account) return;
    setSelectedIcon(account.icon);
    setModalAlias(account.alias);
    setModalMemo(account.memo);
    setModalOpen(true);
  };
  const closeModal = () => { setModalOpen(false); setIconPickerOpen(false); };
  const saveAccount = () => {
    if (!modalAlias.trim()) { showToast('별칭을 입력하세요.'); return; }
    setAccount(prev => prev ? { ...prev, alias: modalAlias.trim(), memo: modalMemo.trim(), icon: selectedIcon } : prev);
    closeModal();
  };

  // OPA helpers
  const findAndUpdate = (key: string, updater: (item: OpaItem) => void) => {
    setOpaData(prev => prev.map(g => ({
      ...g,
      items: g.items.map(i => {
        if (i.key !== key) return i;
        const next = { ...i, params: i.params ? { ...i.params } : null, exceptions: [...i.exceptions] };
        updater(next as OpaItem);
        return next as OpaItem;
      }),
    })));
  };

  const toggleOpaSwitch = (key: string) => findAndUpdate(key, i => { i.on = !i.on; });
  const setSeverity = (key: string, sev: OpaSeverity) => findAndUpdate(key, i => { i.severity = sev; });

  const delTag = (key: string, field: 'params' | 'exceptions', idx: number) => {
    findAndUpdate(key, i => {
      if (field === 'params' && i.params && 'values' in i.params) {
        i.params = { ...i.params, values: i.params.values.filter((_, j) => j !== idx) };
      } else if (field === 'exceptions') {
        i.exceptions = i.exceptions.filter((_, j) => j !== idx);
      }
    });
  };

  const addTag = (key: string, field: 'params' | 'exceptions', val: string) => {
    findAndUpdate(key, i => {
      if (field === 'params' && i.params && 'values' in i.params) {
        if (!i.params.values.includes(val)) i.params = { ...i.params, values: [...i.params.values, val] };
      } else if (field === 'exceptions') {
        if (!i.exceptions.includes(val)) i.exceptions = [...i.exceptions, val];
      }
    });
  };

  const updateParam = (key: string, val: number) => {
    findAndUpdate(key, i => { if (i.params && i.params.type === 'number') i.params = { ...i.params, value: val }; });
  };

  const toggleSvc = (key: string, svc: string) => {
    findAndUpdate(key, i => {
      if (i.params && i.params.type === 'services') {
        const vals = i.params.values.includes(svc) ? i.params.values.filter(v => v !== svc) : [...i.params.values, svc];
        i.params = { ...i.params, values: vals };
      }
    });
  };

  return (
    <div className="workspace-page">
      <div className="page-content">

        {/* 일반 섹션 */}
        {section === 'general' && (
          <>
            {!account ? (
              <div className="empty-state">
                <div className="empty-icon">
                  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12h18M12 3c-4 4-4 14 0 18M12 3c4 4 4 14 0 18" /><circle cx="12" cy="12" r="9" />
                  </svg>
                </div>
                <div className="empty-title">연동된 워크스페이스가 없습니다</div>
                <button className="btn-primary" onClick={() => navigate('/workspace/create')}>
                  <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="10" y1="3" x2="10" y2="17" /><line x1="3" y1="10" x2="17" y2="10" /></svg>
                  워크스페이스 연동하기
                </button>
              </div>
            ) : (
              <>
                {/* 프로필 카드 */}
                <div className="info-card profile-card">
                  <div className="profile-section">
                    <div className="ws-icon">{WS_ICONS[account.icon] || WS_ICONS.rocket}</div>
                    <div className="banner-info">
                      <div className="banner-name-row">{account.alias}</div>
                    </div>
                    <div className="profile-btn-group">
                      <button className="btn-outline" onClick={openEditModal}>
                        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 2.5l2 2L5 11H3V9l6.5-6.5z" /></svg>
                        편집
                      </button>
                    </div>
                  </div>
                  <div className="info-row">
                    <span className="info-label">메모</span>
                    <span className="info-value">{account.memo || <span className="muted">메모 없음</span>}</span>
                  </div>
                </div>

                {/* AWS 연동 */}
                <div className="info-card aws-section">
                  <div className="info-card-header">AWS 연동</div>
                  <div className="info-row"><span className="info-label">계정 ID</span><span className="info-value">{account.acctId}</span></div>
                  <div className="info-row"><span className="info-label">리전</span><span className="info-value">us-east-1</span></div>
                </div>

                {/* GitHub 연동 */}
                <div className="info-card github-section">
                  <div className="info-card-header">GitHub 연동</div>
                  <div className="info-row"><span className="info-label">조직</span><span className="info-value">{account.githubOrg || '-'}</span></div>
                  <div className="info-row"><span className="info-label">저장소</span><span className="info-value">{account.repo || '-'}</span></div>
                  <div className="info-row"><span className="info-label">브랜치</span><span className="info-value">{account.branch || '-'}</span></div>
                  <div className="info-row"><span className="info-label">경로</span><span className="info-value">{account.path || '-'}</span></div>
                </div>
              </>
            )}
          </>
        )}

        {/* OPA 섹션 */}
        {section === 'opa' && (
          <div className="opa-card">
            <div className="opa-header">
              <div className="opa-header-left">
                <div className="opa-title">인프라 정책</div>
                <div className="opa-desc">생성된 Terraform 코드를 정적 분석하여 자동 검증합니다</div>
              </div>
              <button className="btn-save-opa" onClick={() => showToast('인프라 정책 설정이 저장되었습니다.', 'ok')} disabled={session.auth !== 'leader'}>설정 저장</button>
            </div>
            <div className="eg-list">
              {opaData.map(g => (
                <div key={g.category} className="eg">
                  <div className="eg-head">
                    <div className="eg-name">
                      <span>{OPA_ICONS[g.category]}</span>
                      {g.category}
                    </div>
                  </div>
                  <div className="eg-body">
                    {g.items.map(item => (
                      <PolicyItem
                        key={item.key}
                        item={item}
                        shut={closedItems.has(item.key)}
                        readOnly={session.auth !== 'leader'}
                        onToggleShut={() => setClosedItems(prev => {
                          const next = new Set(prev);
                          next.has(item.key) ? next.delete(item.key) : next.add(item.key);
                          return next;
                        })}
                        onToggleSwitch={() => toggleOpaSwitch(item.key)}
                        onSetSeverity={(sev) => setSeverity(item.key, sev)}
                        onDelTag={(field, idx) => delTag(item.key, field, idx)}
                        onAddTag={(field, val) => addTag(item.key, field, val)}
                        onUpdateParam={(val) => updateParam(item.key, val)}
                        onToggleSvc={(svc) => toggleSvc(item.key, svc)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 편집 모달 */}
      {modalOpen && (
        <div className="modal-overlay open" onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
          <div className="modal">
            <div className="modal-head">
              <span className="modal-title">워크스페이스 편집</span>
              <button className="modal-close" onClick={closeModal}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="3" y1="3" x2="13" y2="13" /><line x1="13" y1="3" x2="3" y2="13" /></svg>
              </button>
            </div>
            <div className="modal-body">
              <div className="modal-profile">
                <div className="modal-icon-area" ref={iconAreaRef}>
                  <div className="modal-icon-preview">{WS_ICONS[selectedIcon]}</div>
                  <button className="modal-icon-btn" onClick={() => setIconPickerOpen(p => !p)} title="아이콘 변경">
                    <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 2.5l2 2L5 11H3V9l6.5-6.5z" /></svg>
                  </button>
                  {iconPickerOpen && (
                    <div className="modal-icon-picker open">
                      {ICON_KEYS.map(k => (
                        <div key={k} className={`icon-opt${k === selectedIcon ? ' selected' : ''}`}
                          onClick={() => { setSelectedIcon(k); setIconPickerOpen(false); }}>
                          {WS_ICONS[k]}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="modal-name-area">
                  <input className="modal-alias-input" type="text" placeholder="워크스페이스 별칭" value={modalAlias} onChange={(e) => setModalAlias(e.target.value)} />
                </div>
              </div>
              <div className="field-group">
                <label className="field-label">메모</label>
                <textarea className="field-input" rows={2} placeholder="이 워크스페이스에 대한 설명" style={{ resize: 'vertical' }} value={modalMemo} onChange={(e) => setModalMemo(e.target.value)} />
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn-modal btn-cancel" onClick={closeModal}>취소</button>
              <button className="btn-modal btn-save" onClick={saveAccount}>저장</button>
            </div>
          </div>
        </div>
      )}

      {/* 토스트 */}
      {toast && <div className={`toast ${toast.type} show`}>{toast.msg}</div>}

    </div>
  );
}

/* ── 정책 아이템 컴포넌트 ── */
interface PolicyItemProps {
  item: OpaItem;
  shut: boolean;
  readOnly?: boolean;
  onToggleShut: () => void;
  onToggleSwitch: () => void;
  onSetSeverity: (sev: OpaSeverity) => void;
  onDelTag: (field: 'params' | 'exceptions', idx: number) => void;
  onAddTag: (field: 'params' | 'exceptions', val: string) => void;
  onUpdateParam: (val: number) => void;
  onToggleSvc: (svc: string) => void;
}

function PolicyItem({ item, shut, readOnly, onToggleShut, onToggleSwitch, onSetSeverity, onDelTag, onAddTag, onUpdateParam, onToggleSvc }: PolicyItemProps) {
  const [addingField, setAddingField] = useState<'params' | 'exceptions' | null>(null);
  const [inputVal, setInputVal] = useState('');

  const confirmAdd = (field: 'params' | 'exceptions') => {
    const v = inputVal.trim();
    if (v) onAddTag(field, v);
    setInputVal('');
    setAddingField(null);
  };

  return (
    <div className={`ei${shut ? ' shut' : ''}`}>
      <div className="ei-head" onClick={onToggleShut}>
        <span className="ei-label">{item.label}</span>
        <div className="ei-right">
          <span className={`sev sev-${item.severity}`}>{item.severity === 'block' ? 'BLOCK' : 'WARN'}</span>
          <label className="sw" onClick={(e) => e.stopPropagation()}>
            <input type="checkbox" checked={item.on} onChange={onToggleSwitch} disabled={readOnly} />
            <div className="tr" /><div className="kn" />
          </label>
          <svg className="ei-arr" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6l4 4 4-4" /></svg>
        </div>
      </div>
      {!shut && (
        <div className="ei-body">
          {/* 심각도 */}
          <div className="ei-field">
            <span className="ei-field-label">심각도</span>
            <div className="sev-group">
              <button className={`sev-btn${item.severity === 'block' ? ' active-block' : ''}`} onClick={() => onSetSeverity('block')} disabled={readOnly}>BLOCK</button>
              <button className={`sev-btn${item.severity === 'warn' ? ' active-warn' : ''}`} onClick={() => onSetSeverity('warn')} disabled={readOnly}>WARN</button>
            </div>
          </div>

          {/* 파라미터 */}
          {item.params && item.params.type === 'list' && (
            <div className="ei-field">
              <span className="ei-field-label">{item.params.label}</span>
              <div className="tag-list">
                {item.params.values.map((v, i) => (
                  <span key={`${v}-${i}`} className="tag">{v}<button className="tag-x" onClick={() => onDelTag('params', i)} disabled={readOnly}>&times;</button></span>
                ))}
                {!readOnly && (addingField === 'params' ? (
                  <input className="tag-input" autoFocus value={inputVal} onChange={(e) => setInputVal(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); confirmAdd('params'); } if (e.key === 'Escape') { setAddingField(null); setInputVal(''); } }}
                    onBlur={() => confirmAdd('params')} placeholder="입력 후 Enter" />
                ) : (
                  <button className="tag-add" onClick={() => setAddingField('params')}>+ 추가</button>
                ))}
              </div>
            </div>
          )}

          {item.params && item.params.type === 'number' && (
            <div className="ei-field">
              <span className="ei-field-label">{item.params.label}</span>
              <div>
                <input type="number" className="num-input" value={item.params.value} min={1} onChange={(e) => onUpdateParam(+e.target.value)} disabled={readOnly} />
                <span className="num-unit">{item.params.unit || ''}</span>
              </div>
            </div>
          )}

          {item.params && item.params.type === 'services' && (
            <div className="ei-field">
              <span className="ei-field-label">{item.params.label}</span>
              <div className="svc-checks">
                {item.params.options.map(svc => (
                  <label key={svc} className="svc-check">
                    <input type="checkbox" checked={item.params!.type === 'services' && (item.params as { values: string[] }).values.includes(svc)} onChange={() => onToggleSvc(svc)} disabled={readOnly} />
                    {svc}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* 예외 리소스 */}
          <div className="ei-field">
            <span className="ei-field-label">예외 리소스</span>
            <div className="tag-list">
              {item.exceptions.map((v, i) => (
                <span key={`${v}-${i}`} className="tag">{v}<button className="tag-x" onClick={() => onDelTag('exceptions', i)} disabled={readOnly}>&times;</button></span>
              ))}
              {!readOnly && (addingField === 'exceptions' ? (
                <input className="tag-input" autoFocus value={inputVal} onChange={(e) => setInputVal(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); confirmAdd('exceptions'); } if (e.key === 'Escape') { setAddingField(null); setInputVal(''); } }}
                  onBlur={() => confirmAdd('exceptions')} placeholder="입력 후 Enter" />
              ) : (
                <button className="tag-add" onClick={() => setAddingField('exceptions')}>+ 추가</button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
