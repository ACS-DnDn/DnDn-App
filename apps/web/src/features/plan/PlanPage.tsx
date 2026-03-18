import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';
import { AnimatedLogo } from '@/components/layout/AnimatedLogo';
import { apiFetch } from '@/services/api';
import { getDocuments } from '@/services/document.service';
import type { Document } from '@/mocks';
import type { OrgDept } from '@/mocks';
import './PlanPage.css';

/* ── Terraform 기본값 (API 실패 시 fallback) ── */
const TF_FILES = [
  { name: 'main.tf', code: '# Terraform 코드 생성 버튼을 눌러 코드를 생성하세요.' },
];


interface Approver { id: string; name: string; rank: string; type: string; }
interface PendingApprover { id: string; name: string; rank: string; type: string; }
interface RefDoc { no: string; name: string; }
interface LogEntry { time: string; msg: string; type: string; tab: number; }

const DOC_PAGE_SIZE = 8;

function now() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => String(n).padStart(2, '0')).join(':');
}

export function PlanPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const session = useSession();
  const { isDark } = useTheme();

  /* ── left panel state ── */
  const [approvers, setApprovers] = useState<Approver[]>([]);
  const [refDocs, setRefDocs] = useState<RefDoc[]>([]);
  const [nlTarget, setNlTarget] = useState('');
  const [nlInput, setNlInput] = useState('');

  /* ── center panel state ── */
  const [docState, setDocState] = useState<'blank' | 'loading' | 'ready'>('blank');
  const docTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [docId] = useState(() => Date.now());
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  const autoSaveRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  /* ── right panel state ── */
  const [tfState, setTfState] = useState<'blank' | 'loading' | 'ready'>('blank');
  const [tfTab, setTfTab] = useState(0);
  const [tfCodes, setTfCodes] = useState(TF_FILES.map(f => f.code));
  const [tfStatus, setTfStatus] = useState<'pending' | 'generating' | 'ok'>('pending');
  const [tfStatusText, setTfStatusText] = useState('대기 중');
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const tfTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const validationTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  /* ── API 연동 state ── */
  const [draftDocumentId, setDraftDocumentId] = useState<string | null>(null);
  const [iframeSrc, setIframeSrc] = useState<string | null>(null);
  const [generatedTfFiles, setGeneratedTfFiles] = useState<{ name: string; code: string }[]>([]);
  const logPanelRef = useRef<HTMLDivElement>(null);

  /* ── approver popup state ── */
  const [apvPopupOpen, setApvPopupOpen] = useState(false);
  const [expandedDepts, setExpandedDepts] = useState<Set<string>>(new Set());
  const [orgSelected, setOrgSelected] = useState<Set<string>>(new Set());
  const [pendingApprovers, setPendingApprovers] = useState<PendingApprover[]>([]);
  const [apvSearch, setApvSearch] = useState('');

  /* ── 실제 API 데이터 state ── */
  const [orgData, setOrgData] = useState<OrgDept[]>([]);
  const [docList, setDocList] = useState<Document[]>([]);
  const [ws, setWs] = useState<{ id: string; alias: string; acctId: string } | null>(null);

  useEffect(() => {
    apiFetch<{ data: OrgDept[] }>('/org/members')
      .then(res => setOrgData(res.data))
      .catch(() => {});
    getDocuments({ pageSize: 100 })
      .then(res => setDocList(res.items))
      .catch(() => {});
    apiFetch<{ success: boolean; data: { items: { id: string; alias: string; acctId: string }[] } }>('/workspaces')
      .then(res => setWs(res.data.items[0] ?? null))
      .catch(() => {});
  }, []);

  /* ── doc popup state ── */
  const [docPopupOpen, setDocPopupOpen] = useState(false);
  const [docSearchField, setDocSearchField] = useState<'name' | 'author'>('name');
  const [docSearchQ, setDocSearchQ] = useState('');
  const [docFilterField, setDocFilterField] = useState<'name' | 'author'>('name');
  const [docFilterQ, setDocFilterQ] = useState('');
  const [docPage, setDocPage] = useState(1);
  const [selectedDocNo, setSelectedDocNo] = useState<string | null>(null);

  /* ── init: auto-add ref doc from query ── */
  useEffect(() => {
    const refDocId = searchParams.get('refDocId');
    if (!refDocId) return;
    const doc = docList.find(d => d.id === refDocId);
    if (!doc) return;
    setRefDocs(prev => {
      if (prev.some(r => r.no === doc.id)) return prev;
      return [...prev, { no: doc.id, name: `${doc.icon} ${doc.name}` }];
    });
  }, [searchParams, docList]);

  /* ── scroll log panel ── */
  useEffect(() => {
    if (logPanelRef.current) logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight;
  }, [logEntries]);

  /* ── helpers ── */
  const addLog = useCallback((msg: string, type: string, tab: number) => {
    setLogEntries(prev => [...prev, { time: now(), msg, type, tab }]);
  }, []);

  /* ══════════════════════════════
     결재선
  ══════════════════════════════ */
  const authorInfo = { name: session.name, rank: session.role };

  function removeApprover(idx: number) {
    setApprovers(prev => prev.filter((_, i) => i !== idx));
  }

  /* ── approver popup ── */
  function openApvPopup() {
    setPendingApprovers([]);
    setOrgSelected(new Set());
    setExpandedDepts(new Set());
    setApvSearch('');
    setApvPopupOpen(true);
  }

  function toggleDept(dept: string) {
    setExpandedDepts(prev => {
      const next = new Set(prev);
      if (next.has(dept)) next.delete(dept); else next.add(dept);
      return next;
    });
  }

  function toggleOrgSel(name: string) {
    setOrgSelected(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  function moveToRight() {
    if (!orgSelected.size) return;
    const newPending = [...pendingApprovers];
    orgSelected.forEach(name => {
      if (newPending.some(p => p.name === name)) return;
      const member = orgData.flatMap(d => d.members).find(m => m.name === name);
      newPending.push({ id: member?.id ?? '', name, rank: member?.rank ?? '', type: '결재' });
    });
    setPendingApprovers(newPending);
    setOrgSelected(new Set());
  }

  function removePending(idx: number) {
    setPendingApprovers(prev => prev.filter((_, i) => i !== idx));
  }

  function changePendingType(idx: number, type: string) {
    setPendingApprovers(prev => prev.map((p, i) => i === idx ? { ...p, type } : p));
  }

  function saveApprovers() {
    setApprovers(prev => [...prev, ...pendingApprovers.map(p => ({ id: p.id, name: p.name, rank: p.rank, type: p.type }))]);
    setApvPopupOpen(false);
  }

  /* ── org tree filter ── */
  const sq = apvSearch.toLowerCase();
  const isSearching = sq.length > 0;

  function isMemberDisabled(name: string) {
    return approvers.some(a => a.name === name) || pendingApprovers.some(p => p.name === name);
  }

  /* ══════════════════════════════
     문서 불러오기 팝업
  ══════════════════════════════ */
  function openDocPopup() {
    setSelectedDocNo(null);
    setDocSearchQ('');
    setDocSearchField('name');
    setDocFilterField('name');
    setDocFilterQ('');
    setDocPage(1);
    setDocPopupOpen(true);
  }

  function filterDocsAction() {
    setDocFilterField(docSearchField);
    setDocFilterQ(docSearchQ.toLowerCase().trim());
    setDocPage(1);
  }

  const filteredDocs = docList.filter(d => {
    if (!docFilterQ) return true;
    const val = docFilterField === 'author' ? d.author : d.name;
    return val.toLowerCase().includes(docFilterQ);
  });

  const totalDocPages = Math.max(1, Math.ceil(filteredDocs.length / DOC_PAGE_SIZE));
  const currentPageDocs = filteredDocs.slice((docPage - 1) * DOC_PAGE_SIZE, docPage * DOC_PAGE_SIZE);

  function saveDocPopup() {
    if (!selectedDocNo) return;
    const d = docList.find(x => x.id === selectedDocNo);
    if (!d) return;
    setRefDocs(prev => {
      if (prev.some(r => r.no === d.id)) return prev;
      return [...prev, { no: d.id, name: `${d.id} — ${d.name}` }];
    });
    setDocPopupOpen(false);
  }

  /* ══════════════════════════════
     계획서 생성
  ══════════════════════════════ */
  async function pollJob(jobId: string): Promise<Record<string, unknown>> {
    for (let i = 0; i < 60; i++) {
      await new Promise<void>(r => setTimeout(r, 1000));
      const res = await fetch(`/todo/documents/generate/${jobId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const { status, result, error } = (json.data ?? json) as {
        status: string;
        result?: Record<string, unknown>;
        error?: { message: string };
      };
      if (status === 'done') return result ?? {};
      if (status === 'failed') throw new Error(error?.message ?? '생성 실패');
    }
    throw new Error('타임아웃: 60초 초과');
  }

  async function generateDoc() {
    setDocState('loading');
    setTfState('blank');
    setTfStatus('pending');
    setTfStatusText('대기 중');
    setGeneratedTfFiles([]);
    setTfCodes(TF_FILES.map(f => f.code));
    setLogEntries([]);
    setDraftDocumentId(null);
    try {
      const res = await fetch('/todo/documents/generate/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspaceId: ws?.id,
          target: nlTarget,
          content: nlInput,
          ...(refDocs.length > 0 && { refDocIds: refDocs.map(rd => rd.no) }),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const { jobId } = json.data ?? json;
      const result = await pollJob(jobId);
      setDraftDocumentId(result.documentId as string);
      setIframeSrc(result.contentUrl as string);
      setDocState('ready');
    } catch (err) {
      console.error('workplan API error:', err);
      setDocState('blank');
      alert('계획서 생성 중 오류가 발생했습니다: ' + String(err));
    }
  }

  function doAutoSave() {
    const html = iframeRef.current?.contentDocument?.documentElement.outerHTML;
    if (!html) return;
    localStorage.setItem(`doc-${docId}`, html);
    const timestamp = new Date();
    setLastSaved(
      `${String(timestamp.getHours()).padStart(2, '0')}:${String(timestamp.getMinutes()).padStart(2, '0')}:${String(timestamp.getSeconds()).padStart(2, '0')}`
    );
  }

  const scheduleAutoSave = useCallback(() => {
    if (autoSaveRef.current) clearTimeout(autoSaveRef.current);
    autoSaveRef.current = setTimeout(doAutoSave, 2000);
  }, []);

  async function saveDoc() {
    if (docState !== 'ready' || !draftDocumentId) { alert('저장할 계획서가 없습니다.'); return; }
    if (approvers.length === 0) { alert('결재자를 1명 이상 지정해 주세요.'); return; }

    try {
      const terraformObj = Object.fromEntries(generatedTfFiles.map(f => [f.name, f.code]));
      const res = await apiFetch<{ id: string; docNum: string; status: string }>('/documents', {
        method: 'POST',
        body: JSON.stringify({
          documentId: draftDocumentId,
          type: 'plan',
          terraform: generatedTfFiles.length > 0 ? terraformObj : undefined,
          refDocIds: refDocs.map(rd => rd.no),
          approvers: approvers.map((a, i) => ({ userId: a.id, seq: i + 1, type: a.type })),
          isDraft: false,
        }),
      });
      navigate(`/viewer/${res.id}`);
    } catch (err) {
      console.error('결재 상신 실패:', err);
      alert('결재 상신에 실패했습니다. 다시 시도해 주세요.');
    }
  }

  /* ══════════════════════════════
     Terraform 코드 생성
  ══════════════════════════════ */
  async function generateTerraform() {
    if (!draftDocumentId) return;
    setTfState('loading');
    setTfStatus('generating');
    setTfStatusText('코드 생성 중');
    setLogEntries([]);
    addLog('작업 계획서 분석 중...', 'muted', 0);
    addLog('Terraform 코드 생성 중...', 'run', 0);
    try {
      const res = await fetch('/todo/documents/generate/terraform', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documentId: draftDocumentId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const { jobId } = json.data ?? json;
      const result = await pollJob(jobId);
      const rawFiles = (result.files as Record<string, string>) ?? {};
      const files = Object.entries(rawFiles).map(([name, code]) => ({ name, code }));
      if (files.length === 0) throw new Error('생성된 Terraform 파일이 없습니다.');
      setGeneratedTfFiles(files);
      setTfCodes(files.map(f => f.code));
      setTfTab(0);
      setTfState('ready');
      files.forEach((f, i) => addLog(`${f.name} 생성 완료`, 'ok', i));
      setTfStatus('ok');
      setTfStatusText('생성 완료');
    } catch (err) {
      console.error('terraform API error:', err);
      setTfState('blank');
      setTfStatus('pending');
      setTfStatusText('대기 중');
      addLog('오류: ' + String(err), 'muted', 0);
    }
  }

  function revalidate() {
    setLogEntries([]);
  }

  /* ── auto-resize textarea ── */
  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
  }

  function handleTabKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.currentTarget;
      const s = el.selectionStart;
      const end = el.selectionEnd;
      const val = tfCodes[tfTab] ?? '';
      const newVal = val.substring(0, s) + '  ' + val.substring(end);
      setTfCodes(prev => prev.map((c, i) => i === tfTab ? newVal : c));
      requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 2; });
    }
  }

  /* ── cleanup ── */
  useEffect(() => {
    return () => {
      if (docTimerRef.current) clearTimeout(docTimerRef.current);
      if (tfTimerRef.current) clearTimeout(tfTimerRef.current);
      if (autoSaveRef.current) clearTimeout(autoSaveRef.current);
      validationTimersRef.current.forEach((t) => { clearTimeout(t); });
      const iframeDoc = iframeRef.current?.contentDocument;
      if (iframeDoc) {
        iframeDoc.removeEventListener('input', scheduleAutoSave);
      }
    };
  }, [scheduleAutoSave]);

  /* ══════════════════════════════
     Pagination helper
  ══════════════════════════════ */
  function renderPagination() {
    if (totalDocPages <= 1) return null;
    const range: (number | '…')[] = [];
    for (let i = 1; i <= totalDocPages; i++) {
      if (i === 1 || i === totalDocPages || Math.abs(i - docPage) <= 1) range.push(i);
      else if (range[range.length - 1] !== '…') range.push('…');
    }
    return (
      <div className="doc-pagination">
        <button className="doc-page-btn" disabled={docPage === 1} onClick={() => setDocPage(docPage - 1)}>&lsaquo;</button>
        {range.map((r, i) =>
          r === '…' ? <span key={`e${i}`} className="doc-page-ellipsis">&hellip;</span>
            : <button key={r} className={`doc-page-btn${r === docPage ? ' active' : ''}`} onClick={() => setDocPage(r)}>{r}</button>
        )}
        <button className="doc-page-btn" disabled={docPage === totalDocPages} onClick={() => setDocPage(docPage + 1)}>&rsaquo;</button>
      </div>
    );
  }

  /* ══════════════════════════════
     Approver table rows
  ══════════════════════════════ */
  function renderApproverRows() {
    const rows: React.ReactNode[] = [];
    // author
    rows.push(
      <tr key="author" className="approver-row approver-fixed">
        <td className="col-seq">0</td>
        <td className="col-name">{authorInfo.name || '—'}</td>
        <td className="col-rank">{authorInfo.rank || '—'}</td>
        <td className="col-type">기안</td>
        <td className="col-del"></td>
      </tr>
    );

    const typeOrder = ['결재', '협조', '참조'];
    let isFirst = true;
    typeOrder.forEach(type => {
      const filtered = approvers.filter(a => a.type === type);
      if (!filtered.length) return;
      filtered.forEach((a, i) => {
        const idx = approvers.indexOf(a);
        rows.push(
          <tr key={`${type}-${idx}`} className={`approver-row${i === 0 && !isFirst ? ' group-start' : ''}`}>
            <td className="col-seq">{type === '결재' ? i + 1 : '—'}</td>
            <td className="col-name">{a.name}</td>
            <td className="col-rank">{a.rank}</td>
            <td className="col-type">{a.type}</td>
            <td className="col-del"><button className="approver-remove" onClick={() => removeApprover(idx)}>&times;</button></td>
          </tr>
        );
      });
      isFirst = false;
    });

    return rows;
  }

  /* ══════════════════════════════
     RENDER
  ══════════════════════════════ */
  return (
    <>
      {/* ── Plan 전용 topnav (사이드바 없음) ── */}
      <header className="topnav">
        <a className="nav-logo-link" href="/dashboard" onClick={(e) => { e.preventDefault(); navigate('/dashboard'); }}>
          <AnimatedLogo variant={isDark ? 'dark' : 'light'} className="nav-logo-obj" />
        </a>
        <div className="nav-title">
          <a className="crumb-link" href="/dashboard" onClick={(e) => { e.preventDefault(); navigate('/dashboard'); }}>
            <svg className="crumb-home-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2 10l8-6 8 6"/><path d="M4.5 9v7a1 1 0 001 1h3.5v-4h2v4h3.5a1 1 0 001-1V9"/></svg>
          </a>
          <span className="sep">›</span><span className="crumb-cur">작업계획서 작성</span>
        </div>
        <div className="topnav-right">
          {ws && <span className="ws-label">{ws.alias} <span className="ws-acct">({ws.acctId})</span></span>}
          <div className="divider-v" />
          <div className="profile-info">
            <span className="profile-name">{session.name}</span>
            <span className="profile-role">{session.role}</span>
          </div>
          <span className="company-name">{session.company.name}</span>
          <div className="divider-v" />
          {session.company.logoUrl && <img className="company-logo" src={session.company.logoUrl} alt="" />}
        </div>
      </header>

      <div className="plan-page">
      {/* ── 왼쪽 패널 ── */}
      <aside className="plan-left">
        {/* 결재선 */}
        <div className="lsec">
          <div className="lsec-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 12c0-2.2 1.8-4 4-4h4c2.2 0 4 1.8 4 4"/><circle cx="8" cy="5" r="3"/></svg>
            결재선 지정
          </div>
          <div className="approver-table-wrap">
            <table className="approver-table">
              <thead><tr><th className="col-seq">순서</th><th className="col-name">결재자</th><th className="col-rank">직급</th><th className="col-type">구분</th><th className="col-del"></th></tr></thead>
              <tbody>{renderApproverRows()}</tbody>
            </table>
          </div>
          <button className="plan-btn-add" onClick={openApvPopup}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2"><line x1="8" y1="2" x2="8" y2="14"/><line x1="2" y1="8" x2="14" y2="8"/></svg>
            결재자 추가
          </button>
        </div>

        {/* 참조 문서 */}
        <div className="lsec">
          <div className="lsec-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 2H4a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V6l-4-4z"/><path d="M9 2v4h4"/></svg>
            참조 문서
          </div>
          <div className="ref-doc-wrap">
            {refDocs.map(rd => (
              <div key={rd.no} className="ref-doc-item">
                <div className="ref-doc-name">{rd.name}</div>
                <button className="ref-doc-remove" onClick={() => {
                  setRefDocs(prev => prev.filter(r => r.no !== rd.no));
                }}>&times;</button>
              </div>
            ))}
          </div>
          <button className="plan-btn-add" onClick={openDocPopup}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2"><line x1="8" y1="2" x2="8" y2="14"/><line x1="2" y1="8" x2="14" y2="8"/></svg>
            문서 불러오기
          </button>
        </div>

        {/* 작업 대상 */}
        <div className="lsec">
          <div className="lsec-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2"/></svg>
            작업 대상
          </div>
          <textarea className="nl-target" rows={2} value={nlTarget} onChange={e => setNlTarget(e.target.value)} aria-label="작업 대상" />
        </div>

        {/* 작업 내용 */}
        <div className="lsec" style={{ borderBottom: 'none' }}>
          <div className="lsec-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 4h12M2 7h8M2 10h10M2 13h6"/></svg>
            작업 내용
          </div>
          <textarea className="nl-textarea" rows={4} value={nlInput} onChange={e => setNlInput(e.target.value)} aria-label="작업 내용" />
          <button className="btn-generate" disabled={docState === 'loading'} onClick={generateDoc}>문서 작성</button>
        </div>
      </aside>

      {/* ── 가운데 패널 ── */}
      <section className="plan-center">
        <div className="center-topbar">
          <button className="plan-btn-cancel" onClick={() => navigate(-1)}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 3L5 8l5 5"/></svg>
            취소
          </button>
          {lastSaved && <span className="auto-save-label">마지막 저장 {lastSaved}</span>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
            <button className="btn-tf" disabled={docState !== 'ready' || tfState === 'loading'} onClick={generateTerraform}>Terraform 코드 생성</button>
            <button className="plan-btn-save" onClick={saveDoc}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 10l4 4 8-9"/></svg>
              결재 상신
            </button>
          </div>
        </div>

        <div className={`doc-editor${docState === 'ready' ? ' has-doc' : ''}`}>
          {docState === 'blank' && <div className="doc-blank" />}

          {docState === 'loading' && (
            <div className="doc-loading">
              <div className="loading-shimmer-wrap">
                <div className="shimmer shimmer-title" />
                <div className="shimmer shimmer-meta" style={{ marginBottom: 12 }} />
                <div className="shimmer shimmer-line w90" />
                <div className="shimmer shimmer-line w80" />
                <div className="shimmer shimmer-line w95" />
                <div className="shimmer shimmer-line w70" style={{ marginBottom: 12 }} />
                <div className="shimmer shimmer-block" style={{ height: 72, borderRadius: 8, marginBottom: 12 }} />
                <div className="shimmer shimmer-line w90" />
                <div className="shimmer shimmer-line w80" />
              </div>
              <div className="loading-label">계획서 생성 중...</div>
            </div>
          )}

          {docState === 'ready' && (
            <iframe
              ref={iframeRef}
              className="plan-iframe"
              {...(iframeSrc ? { src: iframeSrc } : { src: '/mock/plan-sample.html' })}
              onLoad={() => {
                const doc = iframeRef.current?.contentDocument;
                if (doc) {
                  doc.designMode = 'on';
                  doc.addEventListener('input', scheduleAutoSave);
                }
              }}
            />
          )}
        </div>
      </section>

      {/* ── 오른쪽: Terraform ── */}
      <aside className="plan-right">
        {tfState === 'blank' && <div className="tf-blank" />}

        {tfState === 'loading' && (
          <div className="tf-loading">
            <div className="tf-shimmer-wrap">
              <div className="tf-block-mock">
                <div className="tf-shimmer h12 w60" />
                <div className="tf-shimmer h12 w95" />
                <div className="tf-shimmer h12 w80" />
                <div className="tf-shimmer h12 w70" />
                <div className="tf-shimmer h12 w95" />
                <div className="tf-shimmer h12 w50" />
              </div>
              <div className="tf-block-mock" style={{ marginTop: 4 }}>
                <div className="tf-shimmer h12 w70" />
                <div className="tf-shimmer h12 w80" />
                <div className="tf-shimmer h12 w60" />
              </div>
            </div>
            <div className="tf-loading-label">코드 생성 중...</div>
          </div>
        )}

        {tfState === 'ready' && (
          <div className="tf-code-area">
            <div className="tf-tabs-bar">
              {(generatedTfFiles.length > 0 ? generatedTfFiles : TF_FILES).map((f, i) => (
                <button key={f.name} className={`plan-tf-tab${tfTab === i ? ' active' : ''}`} onClick={() => setTfTab(i)}>{f.name}</button>
              ))}
            </div>
            <div className="tf-code-scroll">
              {(generatedTfFiles.length > 0 ? generatedTfFiles : TF_FILES).map((_, i) => (
                <div key={i} className={`tf-tab-panel${tfTab === i ? ' active' : ''}`}>
                  <textarea
                    className="tf-editor"
                    spellCheck={false}
                    value={tfCodes[i]}
                    onChange={e => {
                      const val = e.target.value;
                      setTfCodes(prev => prev.map((c, ci) => ci === i ? val : c));
                      autoResize(e.target);
                    }}
                    onKeyDown={handleTabKey}
                    ref={el => { if (el) autoResize(el); }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="tf-statusbar">
          <div className="tf-log-header">
            <div className={`tf-status ${tfStatus}`}>
              <div className="tf-dot" />
              <span>{tfStatusText}</span>
            </div>
            <button className="tf-revalidate-btn" onClick={revalidate} title="재검증">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M13.5 8A5.5 5.5 0 1 1 8 2.5" />
                <polyline points="13.5 2.5 13.5 8 8 8" />
              </svg>
            </button>
          </div>
          <div className="tf-log-panel active" ref={logPanelRef}>
            {logEntries.filter(e => e.tab === tfTab).map((e, i) => (
              <div key={i} className={`tf-log-entry log-${e.type}`}>
                <span className="tf-log-time">{e.time}</span>
                <div className="tf-log-dot" />
                <span className="tf-log-msg">{e.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ══════════════════════════════
         팝업: 결재자 추가
      ══════════════════════════════ */}
      <div className={`plan-popup-overlay${apvPopupOpen ? ' open' : ''}`} onClick={e => { if (e.target === e.currentTarget) setApvPopupOpen(false); }}>
        <div className="plan-popup" style={{ width: 460 }}>
          <div className="plan-popup-header">
            <span className="plan-popup-title">결재자 추가</span>
            <button className="plan-popup-close" onClick={() => setApvPopupOpen(false)}>&times;</button>
          </div>
          <div className="apv-popup-body">
            {/* 왼쪽: 조직도 */}
            <div className="apv-left">
              <div className="apv-left-search">
                <input type="text" placeholder="이름 또는 부서 검색" value={apvSearch} onChange={e => setApvSearch(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') e.preventDefault(); }} />
                <button className="apv-search-btn" onClick={() => {}}>검색</button>
              </div>
              <div className="apv-tree">
                {orgData.map(dept => {
                  const members = dept.members.filter(m =>
                    !sq || m.name.toLowerCase().includes(sq) || dept.dept.toLowerCase().includes(sq)
                  );
                  if (!members.length) return null;
                  const isOpen = isSearching || expandedDepts.has(dept.dept);
                  return (
                    <div key={dept.dept}>
                      <div className={`org-dept-header${isOpen ? ' open' : ''}`} onClick={() => toggleDept(dept.dept)}>
                        <span className="org-dept-name">{dept.dept}</span>
                        <span className="org-dept-count">{members.length}</span>
                        <span className="org-dept-chevron">&rsaquo;</span>
                      </div>
                      {isOpen && members.map(m => {
                        const disabled = isMemberDisabled(m.name);
                        const selected = orgSelected.has(m.name);
                        return (
                          <div key={m.name} className={`org-member${selected ? ' selected' : ''}${disabled ? ' disabled' : ''}`} onClick={() => !disabled && toggleOrgSel(m.name)}>
                            <div className="org-check">{selected ? '✓' : ''}</div>
                            <span className="org-name">{m.name}</span>
                            <span className="org-rank">{m.rank}</span>
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 가운데: 화살표 */}
            <div className="apv-mid">
              <button className="apv-move-btn" onClick={moveToRight}>&rsaquo;</button>
            </div>

            {/* 오른쪽: 대기 목록 */}
            <div className="apv-right">
              <div className="apv-right-list">
                {pendingApprovers.map((p, i) => (
                  <div key={i} className="apv-pending-row">
                    <span className="apv-pending-name">{p.name}</span>
                    <select className="apv-pending-type" value={p.type} onChange={e => changePendingType(i, e.target.value)}>
                      <option>결재</option>
                      <option>협조</option>
                      <option>참조</option>
                    </select>
                    <button className="apv-pending-del" onClick={() => removePending(i)}>&times;</button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="plan-popup-footer">
            <div className="plan-popup-footer-info">대기: <strong>{pendingApprovers.length}</strong>명</div>
            <button className="btn-popup-save" onClick={saveApprovers}>저장</button>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════
         팝업: 문서 불러오기
      ══════════════════════════════ */}
      <div className={`plan-popup-overlay${docPopupOpen ? ' open' : ''}`} onClick={e => { if (e.target === e.currentTarget) setDocPopupOpen(false); }}>
        <div className="plan-popup popup-doc">
          <div className="plan-popup-header">
            <span className="plan-popup-title">문서 불러오기</span>
            <button className="plan-popup-close" onClick={() => setDocPopupOpen(false)}>&times;</button>
          </div>
          <div className="popup-search">
            <select className="doc-search-field" value={docSearchField} onChange={e => setDocSearchField(e.target.value as 'name' | 'author')}>
              <option value="name">제목</option>
              <option value="author">작성자</option>
            </select>
            <input type="text" placeholder="검색어 입력" value={docSearchQ} onChange={e => setDocSearchQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') filterDocsAction(); }} />
            <button className="popup-search-btn" onClick={filterDocsAction}>검색</button>
          </div>
          <div className="doc-list-header">
            <span className="doc-col-no">문서번호</span>
            <span className="doc-col-name">제목</span>
            <span className="doc-col-author">작성자</span>
            <span className="doc-col-date">등록일</span>
          </div>
          <div className="popup-list">
            {currentPageDocs.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>검색 결과가 없습니다.</div>
            ) : currentPageDocs.map(d => (
              <div key={d.id} className={`doc-popup-item${selectedDocNo === d.id ? ' selected' : ''}`} onClick={() => setSelectedDocNo(prev => prev === d.id ? null : d.id)}>
                <div className="doc-item-no">{d.id}</div>
                <div className="doc-item-name">{d.name}</div>
                <div className="doc-item-author">{d.author}</div>
                <div className="doc-item-date">{d.date}</div>
              </div>
            ))}
          </div>
          {renderPagination()}
          <div className="plan-popup-footer" style={{ justifyContent: 'flex-end' }}>
            <button className="btn-popup-save" onClick={saveDocPopup}>불러오기</button>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
