import { useState, useEffect } from 'react';
import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { getDocumentById, getAttachmentDownloadUrl, markDocumentsAsRead } from '@/services/document.service';
import { apiFetch } from '@/services/api';
import './ViewerPage.css';

function escHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderTerraform(terraform: Record<string, string>): string {
  return Object.entries(terraform).map(([filename, code]) =>
    `<div class="tf-code-block"><div class="tf-code-file"><span class="f-dot f-dot-purple"></span>${escHtml(filename)}</div><pre class="tf-pre">${escHtml(code)}</pre></div>`
  ).join('');
}

/* ── 결재선 헬퍼 ── */
interface ApprovalStep {
  seq: string;
  name: string;
  role: string;
  dot: string;
  status: string;
  statusCls: string;
  date?: string;
  comment?: string;
}

function fmtDate(iso?: string | null): string | undefined {
  if (!iso) return undefined;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const DOT_MAP: Record<string, string> = {
  author: 'dot-author', approved: 'dot-approved', current: 'dot-current',
  wait: 'dot-wait', rejected: 'dot-wait',
};
const STATUS_LABEL: Record<string, string> = {
  author: '기안', approved: '결재', current: '대기', wait: '대기', rejected: '반려',
};

function mapApprovalLine(items: import('@/mocks/types/document').ApprovalLineItem[]) {
  const mainSteps: ApprovalStep[] = [];
  const collabSteps: ApprovalStep[] = [];
  let approvalIdx = 0;
  for (const item of items) {
    const dot = DOT_MAP[item.status] ?? 'dot-wait';
    const statusLbl = STATUS_LABEL[item.status] ?? item.status;
    const step: ApprovalStep = {
      seq: '',
      name: item.name,
      role: item.role,
      dot,
      status: statusLbl,
      statusCls: item.status,
      date: fmtDate(item.date),
      comment: item.comment ?? undefined,
    };
    if (item.type === '작성자') {
      step.seq = '기안';
      mainSteps.push(step);
    } else if (item.type === '결재') {
      approvalIdx++;
      step.seq = `${approvalIdx}차`;
      mainSteps.push(step);
    } else {
      step.seq = item.type; // '협조' | '참조'
      collabSteps.push(step);
    }
  }
  return { mainSteps, collabSteps };
}

const TF_PLAN_EMPTY = '<div style="padding:2rem;text-align:center;color:#888;font-size:13px;">최종 결재 후 GitHub PR이 생성되면 CI/CD에서 terraform plan이 실행됩니다.</div>';

/* ── 상태 맵 ── */
const STATUS_MAP: Record<string, [string, string]> = {
  progress: ['s-progress', '진행 중'],
  done: ['s-done', '완료'],
  rejected: ['s-rejected', '반려'],
  failed: ['s-failed', '실패'],
};

export function ViewerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [doc, setDoc] = useState<import('@/mocks/types/document').Document | undefined>(undefined);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [docNotFound, setDocNotFound] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    if (!id) { setDocNotFound(true); return; }
    setDoc(undefined);
    setDocNotFound(false);
    setFetchError(false);
    getDocumentById(id).then(result => {
      if (result) {
        setDoc(result);
        if (!result.isRead) markDocumentsAsRead([id]).catch(console.error);
      } else setDocNotFound(true);
    }).catch(() => setFetchError(true));
  }, [id]);

  /* Blob URL for iframe isolation (prevents AI HTML from polluting parent font) */
  useEffect(() => {
    if (!doc?.content) { setBlobUrl(null); return; }
    const blob = new Blob([doc.content], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    setBlobUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [doc?.content]);

  /* 참조 문서 목록 — API가 직접 반환하는 refDocs 사용 */
  const refDocList = (doc?.refDocs ?? []).map(r => ({ id: r.id, docNum: r.docNum || r.id, name: r.title, type: r.type }));

  /* 첨부파일 — API 응답 사용 */
  const attachments = doc?.attachments ?? [];

  /* 패널 탭 */
  const [panelTab, setPanelTab] = useState<'refs' | 'attach'>('refs');
  const [attachChecked, setAttachChecked] = useState<boolean[]>([]);
  useEffect(() => { setAttachChecked(attachments.map(() => false)); }, [doc?.id]);
  const checkedCount = attachChecked.filter(Boolean).length;

  /* 모달 */
  const [tfModalOpen, setTfModalOpen] = useState(false);
  const [tfTab, setTfTab] = useState<'code' | 'plan'>('code');
  const [approveModalOpen, setApproveModalOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [approveOpinion, setApproveOpinion] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  if (docNotFound) return <Navigate to="/documents" replace />;
  if (fetchError) return <div style={{ padding: '2rem', color: 'red' }}>문서를 불러오는 중 오류가 발생했습니다.</div>;
  if (!doc) return null;

  const isReport = doc.type !== '계획서' && doc.type !== '작업계획서';
  const viewMode = doc.action === 'approve' ? 'approver' : 'completed';
  const { mainSteps, collabSteps } = mapApprovalLine(doc.approvalLine ?? []);
  const hasTerraform = !!doc.terraform && Object.keys(doc.terraform).length > 0;
  const tfHtml = hasTerraform ? renderTerraform(doc.terraform!) : '';

  const [sCls, sLbl] = STATUS_MAP[doc.status] ?? ['s-progress', '진행 중'];

  async function handleApproveConfirm() {
    if (!id) return;
    setApproveModalOpen(false);
    setActionLoading(true);
    try {
      await apiFetch<{ success: boolean; data: { newStatus: string } }>(
        `/documents/${id}/approve`,
        { method: 'POST', body: JSON.stringify({ comment: approveOpinion.trim() || null }) }
      );
      navigate('/documents', { replace: true });
    } catch {
      alert('결재 처리 중 오류가 발생했습니다.');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) { alert('반려 사유를 입력해주세요.'); return; }
    if (!id) return;
    setRejectModalOpen(false);
    setActionLoading(true);
    try {
      await apiFetch(`/documents/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ comment: rejectReason.trim() }),
      });
      navigate('/documents', { replace: true });
    } catch {
      alert('반려 처리 중 오류가 발생했습니다.');
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <div className="viewer-page">
      {/* ── 문서 본문 ── */}
      <main className="doc-main">
        <div className="doc-toolbar">
          <span className={`doc-status-badge ${sCls}`}>{sLbl}</span>
          <div className="toolbar-spacer" />
          {hasTerraform && (
            <button className="btn-tf-popup" onClick={() => setTfModalOpen(true)}>
              Terraform 코드 보기
            </button>
          )}
        </div>
        <div className="doc-scroll">
          {blobUrl ? (
            <iframe className="viewer-iframe" src={blobUrl} title="문서 미리보기" />
          ) : (
            <div style={{ padding: '2rem', color: 'var(--text-muted)', fontSize: 13 }}>문서 내용을 불러올 수 없습니다.</div>
          )}
        </div>
      </main>

      {/* ── 우측 패널 ── */}
      <aside className={`doc-panel${isReport ? ' no-approval' : ''}`}>
        {/* 탭: 참조 문서 / 첨부 파일 */}
        <div className="sidebar-section">
          <div className="panel-tabs">
            <button type="button" className={`panel-tab${panelTab === 'refs' ? ' active' : ''}`} onClick={() => setPanelTab('refs')}>참조 문서</button>
            <button type="button" className={`panel-tab${panelTab === 'attach' ? ' active' : ''}`} onClick={() => setPanelTab('attach')}>첨부 파일</button>
          </div>
          <div className={`panel-tab-content${panelTab === 'refs' ? ' active' : ''}`}>
            <div className="sidebar-refs">
              {refDocList.length === 0 ? (
                <div style={{ padding: '12px 0', fontSize: 12, color: 'var(--text-muted)' }}>참조 문서 없음</div>
              ) : refDocList.map(rd => (
                <div key={rd.id} className="sidebar-ref-item" onClick={() => navigate(`/viewer/${rd.id}`)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/viewer/${rd.id}`); } }}>
                  <div className="sidebar-ref-no">{rd.docNum}</div>
                  <div className="sidebar-ref-row">
                    <span className="sidebar-ref-name">{rd.name}</span>
                    <span className="sidebar-ref-date">{rd.type}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className={`panel-tab-content${panelTab === 'attach' ? ' active' : ''}`}>
            <div className="attach-list">
              {attachments.length === 0 ? (
                <div style={{ padding: '12px 0', fontSize: 12, color: 'var(--text-muted)' }}>첨부 파일 없음</div>
              ) : attachments.map((a, i) => (
                <div className="attach-item" key={a.id}>
                  <input type="checkbox" className="attach-check" checked={attachChecked[i] ?? false} onChange={() => setAttachChecked(prev => prev.map((c, j) => j === i ? !c : c))} />
                  <span className="attach-name">{a.name}</span>
                  <span className="attach-size">{a.sizeKb ? `${a.sizeKb} KB` : ''}</span>
                </div>
              ))}
            </div>
            <button className="btn-attach-dl" disabled={checkedCount === 0} onClick={async () => {
              if (!doc) return;
              const selected = attachments.filter((_, i) => attachChecked[i]);
              for (const a of selected) {
                try {
                  const url = await getAttachmentDownloadUrl(doc.id, a.id);
                  window.open(url, '_blank');
                } catch { /* skip */ }
              }
            }}>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 2v8M5 7l3 3 3-3" /><path d="M3 13h10" /></svg>
              <span>{checkedCount > 0 ? `${checkedCount}개 다운로드` : '다운로드'}</span>
            </button>
          </div>
        </div>

        {/* 결재선 (계획서만) */}
        {!isReport && (
          <>
            <div className="approval-hd">
              <svg viewBox="0 0 16 16" fill="none" stroke="#228BE6" strokeWidth="1.8"><path d="M2 12c0-2.2 1.8-4 4-4h4c2.2 0 4 1.8 4 4" /><circle cx="8" cy="5" r="3" /></svg>
              결재선
            </div>
            <div className="approval-scroll">
              <div className="approval-line">
                {mainSteps.map((s, i) => (
                  <div className="approval-step" key={i}>
                    <div className={`step-dot ${viewMode === 'completed' && (s.dot === 'dot-current' || s.dot === 'dot-wait') ? 'dot-approved' : s.dot}`} />
                    <div className="step-content">
                      <div className="step-header">
                        <span className="step-seq">{s.seq}</span>
                        <span className="step-name">{s.name}</span>
                        <span className="step-role">{s.role}</span>
                        {s.date && <span className="step-date">{s.date}</span>}
                        <div className={`step-status ${viewMode === 'completed' && (s.statusCls === 'current' || s.statusCls === 'wait') ? 'approved' : s.statusCls}`}>
                          {viewMode === 'completed' && (s.statusCls === 'current' || s.statusCls === 'wait') ? '결재' : s.status}
                        </div>
                      </div>
                      {s.comment && <div className="step-comment">{s.comment}</div>}
                    </div>
                  </div>
                ))}
              </div>
              {collabSteps.length > 0 && (
                <div className="collab-area">
                  {collabSteps.map((s, i) => (
                    <div className="approval-step" key={i}>
                      <div className={`step-dot ${s.dot}`} />
                      <div className="step-content">
                        <div className="step-header">
                          <span className="step-seq">{s.seq}</span>
                          <span className="step-name">{s.name}</span>
                          <span className="step-role">{s.role}</span>
                          {s.date && <span className="step-date">{s.date}</span>}
                          <div className={`step-status ${s.statusCls}`}>{s.status}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* 보고서 모드: 계획서 작성 버튼 */}
        {isReport && (
          <div className="report-actions">
            <button className="btn-create-plan" onClick={() => navigate(`/plan?refDocId=${doc.id}`)}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M8 2v12M2 8h12" /></svg>
              계획서 작성
            </button>
          </div>
        )}

        {/* 결재 액션 (계획서 + 결재자) */}
        {!isReport && viewMode === 'approver' && (
          <div className="sidebar-actions">
            <button className="btn-approve" disabled={actionLoading} onClick={() => { setApproveOpinion(''); setApproveModalOpen(true); }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M3 8l4 4 6-6" /></svg>
              {actionLoading ? '처리 중...' : '결재'}
            </button>
            <button className="btn-reject" disabled={actionLoading} onClick={() => { setRejectReason(''); setRejectModalOpen(true); }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4l8 8M12 4l-8 8" /></svg>
              반려
            </button>
          </div>
        )}
      </aside>

      {/* ── Terraform 모달 ── */}
      <div className={`viewer-modal-overlay${tfModalOpen ? ' open' : ''}`} onClick={e => { if (e.target === e.currentTarget) setTfModalOpen(false); }}>
        <div className="viewer-modal tf-modal">
          <div className="tf-modal-header">
            <div className="tf-modal-title">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /><path d="M11.5 9v6M9 11.5h5" /></svg>
              Terraform Code <span>· EKS 노드그룹 변경</span>
            </div>
            <button className="tf-modal-close" onClick={() => setTfModalOpen(false)}>&times;</button>
          </div>
          <div className="tf-modal-tabs">
            <button type="button" className={`tf-tab${tfTab === 'code' ? ' active' : ''}`} onClick={() => setTfTab('code')}>코드</button>
            <button type="button" className={`tf-tab${tfTab === 'plan' ? ' active' : ''}`} onClick={() => setTfTab('plan')}>Plan 결과</button>
          </div>
          <div className="tf-modal-body" style={{ display: tfTab === 'code' ? 'block' : 'none' }} dangerouslySetInnerHTML={{ __html: tfHtml }} />
          <div className="tf-modal-body" style={{ display: tfTab === 'plan' ? 'block' : 'none' }} dangerouslySetInnerHTML={{ __html: TF_PLAN_EMPTY }} />
        </div>
      </div>


      {/* ── 결재 의견 모달 ── */}
      <div className={`viewer-modal-overlay${approveModalOpen ? ' open' : ''}`} onClick={e => { if (e.target === e.currentTarget) setApproveModalOpen(false); }}>
        <div className="viewer-modal approve-reject-modal">
          <div className="approve-reject-body">
            <textarea className="approve-reject-textarea" value={approveOpinion} onChange={e => setApproveOpinion(e.target.value)} placeholder="결재 의견을 입력하세요 (선택)" />
          </div>
          <div className="approve-reject-actions">
            <button className="btn-modal-cancel" onClick={() => setApproveModalOpen(false)}>취소</button>
            <button className="btn-modal-approve" onClick={handleApproveConfirm}>결재</button>
          </div>
        </div>
      </div>

      {/* ── 반려 사유 모달 ── */}
      <div className={`viewer-modal-overlay${rejectModalOpen ? ' open' : ''}`} onClick={e => { if (e.target === e.currentTarget) setRejectModalOpen(false); }}>
        <div className="viewer-modal approve-reject-modal">
          <div className="approve-reject-body">
            <textarea className="approve-reject-textarea" value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder="반려 사유를 입력하세요" style={{ borderColor: rejectReason ? 'var(--orange)' : undefined }} />
          </div>
          <div className="approve-reject-actions">
            <button className="btn-modal-cancel" onClick={() => setRejectModalOpen(false)}>취소</button>
            <button className="btn-modal-reject" onClick={handleReject}>반려</button>
          </div>
        </div>
      </div>
    </div>
  );
}
