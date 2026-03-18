import { useState, useEffect } from 'react';
import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { getDocumentById } from '@/services/document.service';
import './ViewerPage.css';

function escHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderTerraform(terraform: Record<string, string>): string {
  return Object.entries(terraform).map(([filename, code]) =>
    `<div class="tf-code-block"><div class="tf-code-file"><span class="f-dot f-dot-purple"></span>${escHtml(filename)}</div><pre class="tf-pre">${escHtml(code)}</pre></div>`
  ).join('');
}

/* ── 결재선 mock 데이터 ── */
interface ApprovalStep {
  seq: string;
  name: string;
  role: string;
  dot: string;
  status: string;
  statusCls: string;
  date?: string;
  comment?: string;
  commentCls?: string;
}

const APPROVAL_STEPS: ApprovalStep[] = [
  { seq: '기안', name: '이서연', role: '엔지니어', dot: 'dot-author', status: '기안', statusCls: 'author', date: '2026.02.24 14:22', comment: 'EKS CPU 이슈 2주 지속되어 긴급 스케일업 요청드립니다. 비용 증가 사전 승인 부탁드립니다.' },
  { seq: '1차', name: '박지훈', role: '팀장', dot: 'dot-approved', status: '결재', statusCls: 'approved', date: '2026.02.24 16:05', comment: '피크타임 CPU 수치 확인했습니다. 비용 증가 합리적인 수준으로 판단하여 결재합니다.' },
  { seq: '2차', name: '정지은', role: '선임연구원', dot: 'dot-current', status: '대기', statusCls: 'current' },
  { seq: '3차', name: '최현우', role: '매니저', dot: 'dot-wait', status: '대기', statusCls: 'wait' },
];

const COLLAB_STEPS: ApprovalStep[] = [
  { seq: '협조', name: '홍길동', role: '선임', dot: 'dot-approved', status: '확인', statusCls: 'approved', date: '2026.02.25 09:12' },
  { seq: '협조', name: '이수진', role: '과장', dot: 'dot-wait', status: '대기', statusCls: 'wait' },
  { seq: '참조', name: '김민준', role: '매니저', dot: 'dot-approved', status: '확인', statusCls: 'approved', date: '2026.02.25 11:40' },
  { seq: '참조', name: '박소연', role: '과장', dot: 'dot-wait', status: '대기', statusCls: 'wait' },
  { seq: '참조', name: '장우진', role: '담당', dot: 'dot-wait', status: '대기', statusCls: 'wait' },
];

/* ── 첨부 파일 mock ── */
const ATTACHMENTS = [
  { name: 'CPU_usage_peaktime.png', size: '1.2 MB' },
  { name: 'cloudwatch_metrics_0224.csv', size: '85 KB' },
  { name: 'eks_plan_output.txt', size: '4 KB' },
];

/* ── Terraform 코드 mock ── */
const TF_CODE_HTML = `<div class="tf-code-block">
<div class="tf-code-file"><span class="f-dot f-dot-purple"></span>eks_node_group.tf</div>
<pre class="tf-pre"><span class="tf-kw">resource</span> <span class="tf-str">"aws_eks_node_group"</span> <span class="tf-str">"production_ng"</span> {
  <span class="tf-attr">cluster_name</span>    = <span class="tf-val">aws_eks_cluster.main.name</span>
  <span class="tf-attr">node_group_name</span> = <span class="tf-str">"production-ng"</span>
  <span class="tf-attr">node_role_arn</span>   = <span class="tf-val">aws_iam_role.node.arn</span>
  <span class="tf-attr">subnet_ids</span>      = <span class="tf-val">var.private_subnet_ids</span>

  <span class="tf-attr">instance_types</span> = [<span class="tf-str">"t3.large"</span>]
  <span class="tf-cmt"># 변경: t3.medium → t3.large</span>

  <span class="tf-kw">scaling_config</span> {
    <span class="tf-attr">desired_size</span> = <span class="tf-num">3</span>
    <span class="tf-attr">min_size</span>     = <span class="tf-num">2</span>
    <span class="tf-attr">max_size</span>     = <span class="tf-num">6</span>
  }

  <span class="tf-kw">update_config</span> {
    <span class="tf-attr">max_unavailable</span> = <span class="tf-num">1</span>
  }

  <span class="tf-kw">tags</span> = {
    <span class="tf-attr">Environment</span> = <span class="tf-str">"production"</span>
    <span class="tf-attr">ManagedBy</span>   = <span class="tf-str">"terraform"</span>
    <span class="tf-attr">ChangedBy</span>   = <span class="tf-str">"dndn"</span>
    <span class="tf-attr">RFC</span>         = <span class="tf-str">"PLAN-2026-0224-001"</span>
  }
}</pre>
</div>
<div class="tf-code-block">
<div class="tf-code-file"><span class="f-dot f-dot-purple"></span>iam_node_role.tf</div>
<pre class="tf-pre"><span class="tf-kw">resource</span> <span class="tf-str">"aws_iam_role"</span> <span class="tf-str">"node"</span> {
  <span class="tf-attr">name</span> = <span class="tf-str">"eks-node-role"</span>

  <span class="tf-attr">assume_role_policy</span> = <span class="tf-val">jsonencode</span>({
    <span class="tf-attr">Version</span>   = <span class="tf-str">"2012-10-17"</span>
    <span class="tf-attr">Statement</span> = [{
      <span class="tf-attr">Action</span>    = <span class="tf-str">"sts:AssumeRole"</span>
      <span class="tf-attr">Effect</span>    = <span class="tf-str">"Allow"</span>
      <span class="tf-attr">Principal</span> = {
        <span class="tf-attr">Service</span> = <span class="tf-str">"ec2.amazonaws.com"</span>
      }
    }]
  })
}</pre>
</div>
<div class="tf-code-block">
<div class="tf-code-file"><span class="f-dot f-dot-purple"></span>rollback_vars.tf</div>
<pre class="tf-pre"><span class="tf-cmt"># 롤백용 원본 설정 보존</span>
<span class="tf-kw">variable</span> <span class="tf-str">"rollback_instance_type"</span> {
  <span class="tf-attr">description</span> = <span class="tf-str">"이전 인스턴스 타입 (롤백 시 참조)"</span>
  <span class="tf-attr">default</span>     = <span class="tf-str">"t3.medium"</span>
}</pre>
</div>`;

const TF_PLAN_HTML = `<div class="tf-plan-box"><span class="pl-ok">\u2713 terraform plan 성공</span>

Terraform will perform the following actions:

<span class="pl-add">~ aws_eks_node_group.production_ng</span>
    instance_types: [
        - "t3.medium"
        + "t3.large"
    ]
    update_config.max_unavailable: 1

<span class="pl-warn">Plan: 0 to add, 1 to change, 0 to destroy.</span>

<span class="pl-ok">\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500</span>
Note: You didn't use the -out option to save this plan.
Next steps: Review \u2192 Merge PR \u2192 apply will run automatically.</div>`;

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

  // mock: localStorage에 저장된 문서가 있으면 /mock/ URL 사용, 나중에 API 연동 시 S3 URL로 대체
  const savedDocUrl = localStorage.getItem(`doc-${id}`) ? '/mock/plan-sample.html' : null;
  const [doc, setDoc] = useState<import('@/mocks/types/document').Document | undefined>(undefined);
  const [docNotFound, setDocNotFound] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    if (!id) { setDocNotFound(true); return; }
    setDoc(undefined);
    setDocNotFound(false);
    setFetchError(false);
    getDocumentById(id).then(result => {
      if (result) setDoc(result);
      else setDocNotFound(true);
    }).catch(() => setFetchError(true));
  }, [id]);

  /* 참조 문서 목록 */
  const [refDocList, setRefDocList] = useState<{ id: string; name: string; date: string }[]>([]);
  useEffect(() => {
    setRefDocList([]);
    if (!doc?.refDocIds?.length) return;
    Promise.all(doc.refDocIds.map(refId => getDocumentById(refId)))
      .then(results => setRefDocList(
        results.filter((d): d is NonNullable<typeof d> => d !== undefined)
          .map(d => ({ id: d.id, name: d.name, date: d.date }))
      ))
      .catch(() => setRefDocList([]));
  }, [doc?.id]);

  /* 패널 탭 */
  const [panelTab, setPanelTab] = useState<'refs' | 'attach'>('refs');
  const [attachChecked, setAttachChecked] = useState<boolean[]>(ATTACHMENTS.map(() => false));
  const checkedCount = attachChecked.filter(Boolean).length;

  /* 모달 */
  const [tfModalOpen, setTfModalOpen] = useState(false);
  const [tfTab, setTfTab] = useState<'code' | 'plan'>('code');
  const [approveModalOpen, setApproveModalOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [approveOpinion, setApproveOpinion] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  if (docNotFound) return <Navigate to="/documents" replace />;
  if (fetchError) return <div style={{ padding: '2rem', color: 'red' }}>문서를 불러오는 중 오류가 발생했습니다.</div>;
  if (!doc) return null;

  const isReport = doc.type !== '계획서';
  const viewMode = doc.action === 'approve' ? 'approver' : 'completed';
  const hasTerraform = !!doc.terraform && Object.keys(doc.terraform).length > 0;
  const tfHtml = hasTerraform ? renderTerraform(doc.terraform!) : '';

  const [sCls, sLbl] = STATUS_MAP[doc.status] ?? ['s-progress', '진행 중'];

  function handleApproveConfirm() {
    setApproveModalOpen(false);
    alert(`결재 완료!${approveOpinion ? '\n의견: "' + approveOpinion + '"' : ''}\n\n다음 결재자에게 알림이 전송됩니다.`);
  }

  function handleReject() {
    if (!rejectReason.trim()) { alert('반려 사유를 입력해주세요.'); return; }
    setRejectModalOpen(false);
    alert(`반려 처리되었습니다.\n사유: "${rejectReason}"\n\n이전 결재자와 작성자에게 알림이 전송됩니다.`);
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
          {savedDocUrl ? (
            <iframe className="viewer-iframe" src={savedDocUrl} title="문서 미리보기" />
          ) : doc.content ? (
            <div dangerouslySetInnerHTML={{ __html: doc.content }} />
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
                  <div className="sidebar-ref-no">{rd.id}</div>
                  <div className="sidebar-ref-row">
                    <span className="sidebar-ref-name">{rd.name}</span>
                    <span className="sidebar-ref-date">{rd.date}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className={`panel-tab-content${panelTab === 'attach' ? ' active' : ''}`}>
            <div className="attach-list">
              {ATTACHMENTS.map((a, i) => (
                <div className="attach-item" key={i}>
                  <input type="checkbox" className="attach-check" checked={attachChecked[i]} onChange={() => setAttachChecked(prev => prev.map((c, j) => j === i ? !c : c))} />
                  <span className="attach-name">{a.name}</span>
                  <span className="attach-size">{a.size}</span>
                </div>
              ))}
            </div>
            <button className="btn-attach-dl" disabled={checkedCount === 0}>
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
                {APPROVAL_STEPS.map((s, i) => (
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
                      {s.comment && <div className={`step-comment${s.commentCls ? ' ' + s.commentCls : ''}`}>{s.comment}</div>}
                    </div>
                  </div>
                ))}
              </div>
              <div className="collab-area">
                {COLLAB_STEPS.map((s, i) => (
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
            <button className="btn-approve" onClick={() => { setApproveOpinion(''); setApproveModalOpen(true); }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M3 8l4 4 6-6" /></svg>
              결재
            </button>
            <button className="btn-reject" onClick={() => { setRejectReason(''); setRejectModalOpen(true); }}>
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
          <div className="tf-modal-body" style={{ display: tfTab === 'plan' ? 'block' : 'none' }} dangerouslySetInnerHTML={{ __html: TF_PLAN_HTML }} />
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
