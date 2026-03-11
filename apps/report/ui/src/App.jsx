import { useState, useRef } from 'react';
import EventReport from './components/report/EventReport';
import WeeklyReport from './components/report/WeeklyReport';
import WorkPlan from './components/report/WorkPlan';
import WorkPlanForm from './components/report/WorkPlanForm';
import HealthEventReport from './components/report/HealthEventReport';
import eventSample from './data/event.securityhub.sample.json';
import canonicalSample from './data/canonical.sample.json';
import healthEksSample from './data/health-eks-version-eol.json';
import healthLambdaSample from './data/health-lambda-runtime-deprecation.json';
import healthRdsSample from './data/health-rds-cert-rotation.json';
import './index.css';

const API_BASE = import.meta.env.VITE_REPORT_API_BASE ?? 'http://localhost:8000';

const TABS = [
  { key: 'event', label: '이벤트 보고서 (SecurityHub)' },
  { key: 'health', label: '이벤트 보고서 (Health)' },
  { key: 'weekly', label: '주간 보고서' },
  { key: 'workplan', label: '작업계획서' },
];

const HEALTH_SAMPLES = [
  { key: 'eks', label: 'EKS 버전 EOL', icon: '⎈', data: healthEksSample },
  { key: 'lambda', label: 'Lambda 런타임 Deprecated', icon: 'λ', data: healthLambdaSample },
  { key: 'rds', label: 'RDS 인증서 교체', icon: '🗄', data: healthRdsSample },
];

async function fetchReport(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API 오류: ${res.status}`);
  const json = await res.json();
  return json.data;
}

function downloadHTML(ref, filename) {
  const style = Array.from(document.styleSheets)
    .map(s => { try { return Array.from(s.cssRules).map(r => r.cssText).join('\n'); } catch { return ''; } })
    .join('\n');
  const html = `<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/><title>${filename}</title><style>${style}</style></head><body>${ref.current.outerHTML}</body></html>`;
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `${filename}.html`; a.click();
  URL.revokeObjectURL(url);
}

function downloadTF(content, filename) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function EmptyState({ onGenerate, loading, label }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">📄</div>
      <div className="empty-state-text">아직 생성된 보고서가 없습니다</div>
      <div className="empty-state-sub">JSON 데이터를 기반으로 AI가 보고서를 생성합니다</div>
      <button className="btn-ai btn-ai-large" onClick={onGenerate} disabled={loading}>
        {loading ? '⏳ AI 보고서 생성 중...' : `✨ ${label} 생성`}
      </button>
    </div>
  );
}

function HealthEmptyState({ loading, onGenerate }) {
  const [selected, setSelected] = useState('eks');
  const selectedSample = HEALTH_SAMPLES.find(s => s.key === selected);

  return (
    <div className="empty-state">
      <div className="empty-state-icon">🏥</div>
      <div className="empty-state-text">AWS Health 이벤트 보고서</div>
      <div className="empty-state-sub">샘플 이벤트를 선택하여 보고서를 생성하세요</div>
      <div className="health-sample-list">
        {HEALTH_SAMPLES.map(s => (
          <button
            key={s.key}
            className={`health-sample-item ${selected === s.key ? 'selected' : ''}`}
            onClick={() => setSelected(s.key)}
          >
            <span className="health-sample-icon">{s.icon}</span>
            {s.label}
          </button>
        ))}
      </div>
      <button
        className="btn-ai btn-ai-large"
        onClick={() => onGenerate(selectedSample.data)}
        disabled={loading}
      >
        {loading ? '⏳ AI 보고서 생성 중...' : '✨ Health 이벤트 보고서 생성'}
      </button>
    </div>
  );
}

function CheckovBadge({ checkov }) {
  if (!checkov || checkov.error) return null;
  const summary = checkov.summary || {};
  const passed = summary.passed ?? '?';
  const failed = summary.failed ?? '?';
  const hasIssues = typeof failed === 'number' && failed > 0;
  return (
    <div className={`checkov-badge ${hasIssues ? 'has-issues' : 'all-pass'}`}>
      🛡 Checkov: <strong>{passed} passed</strong> / <span className={hasIssues ? 'checkov-fail' : ''}>{failed} failed</span>
    </div>
  );
}

function TerraformEditor({ files, checkov, onClose }) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [editedFiles, setEditedFiles] = useState(files);

  function updateContent(idx, value) {
    setEditedFiles(prev => prev.map((f, i) => i === idx ? { ...f, content: value } : f));
  }

  return (
    <div className="tf-editor">
      <div className="tf-editor-header">
        <span className="tf-editor-title">🔧 테라폼 코드</span>
        <div className="tf-editor-actions">
          <CheckovBadge checkov={checkov} />
          {editedFiles.map((f, i) => (
            <button key={i} className="btn-download" onClick={() => downloadTF(f.content, f.filename)}>
              ⬇ {f.filename}
            </button>
          ))}
          <button className="btn-close" onClick={onClose}>✕ 닫기</button>
        </div>
      </div>
      {editedFiles.length > 1 && (
        <div className="tf-tabs">
          {editedFiles.map((f, i) => (
            <button key={i} className={`tf-tab ${selectedIdx === i ? 'active' : ''}`} onClick={() => setSelectedIdx(i)}>
              {f.filename}
            </button>
          ))}
        </div>
      )}
      <textarea
        className="tf-code"
        value={editedFiles[selectedIdx]?.content || ''}
        onChange={e => updateContent(selectedIdx, e.target.value)}
        spellCheck={false}
      />
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState('event');
  const [workplanMode, setWorkplanMode] = useState('view');

  const [generatedDocs, setGeneratedDocs] = useState({ event: null, weekly: null, health: null });
  const [selectedSourceDoc, setSelectedSourceDoc] = useState(null);
  const [workplanData, setWorkplanData] = useState(null);
  const [terraformFiles, setTerraformFiles] = useState(null);
  const [terraformCheckov, setTerraformCheckov] = useState(null);
  const [loading, setLoading] = useState({});
  const [error, setError] = useState({});

  const eventRef = useRef(null);
  const weeklyRef = useRef(null);
  const workplanRef = useRef(null);
  const healthRef = useRef(null);

  async function generateEventReport() {
    setLoading(p => ({ ...p, event: true }));
    setError(p => ({ ...p, event: null }));
    try {
      const data = await fetchReport('/api/report/event', { canonical: eventSample });
      setGeneratedDocs(p => ({ ...p, event: { canonical: data, label: `이벤트 보고서 (EVT-${data?.meta?.run_id?.slice(-8) || 'latest'})` } }));
    } catch (e) {
      setError(p => ({ ...p, event: e.message }));
    } finally {
      setLoading(p => ({ ...p, event: false }));
    }
  }

  async function generateHealthEventReport(rawJson) {
    setLoading(p => ({ ...p, health: true }));
    setError(p => ({ ...p, health: null }));
    try {
      const data = await fetchReport('/api/report/health-event', { raw: rawJson });
      setGeneratedDocs(p => ({ ...p, health: { report: data, label: `Health 이벤트 보고서 (${data?.문서번호 || 'latest'})` } }));
    } catch (e) {
      setError(p => ({ ...p, health: e.message }));
    } finally {
      setLoading(p => ({ ...p, health: false }));
    }
  }

  async function generateWeeklyReport() {
    setLoading(p => ({ ...p, weekly: true }));
    setError(p => ({ ...p, weekly: null }));
    try {
      const data = await fetchReport('/api/report/weekly', { canonical: canonicalSample });
      setGeneratedDocs(p => ({ ...p, weekly: { canonical: data, label: `주간 보고서 (${new Date().toLocaleDateString('ko-KR')})` } }));
    } catch (e) {
      setError(p => ({ ...p, weekly: e.message }));
    } finally {
      setLoading(p => ({ ...p, weekly: false }));
    }
  }

  async function generateWorkPlan() {
    if (!selectedSourceDoc) return;
    setLoading(p => ({ ...p, workplan: true }));
    setError(p => ({ ...p, workplan: null }));
    setTerraformFiles(null);
    try {
      const data = await fetchReport('/api/report/workplan', {
        source_doc: selectedSourceDoc.canonical,
        doc_type: selectedSourceDoc.type,
      });
      setWorkplanData({ ...data, doc_id: `DOC-${Date.now().toString().slice(-8)}`, created_at: new Date().toISOString().slice(0, 10) });
      setWorkplanMode('view');
    } catch (e) {
      setError(p => ({ ...p, workplan: e.message }));
    } finally {
      setLoading(p => ({ ...p, workplan: false }));
    }
  }

  async function generateTerraform() {
    if (!workplanData) return;
    setLoading(p => ({ ...p, terraform: true }));
    setError(p => ({ ...p, terraform: null }));
    try {
      const data = await fetchReport('/api/terraform/generate', {
        workplan: workplanData,
        repo_name: 'ChanHyeok-Jeon/terraform-class',
      });
      setTerraformFiles(data.files);
      setTerraformCheckov(data.checkov || null);
    } catch (e) {
      setError(p => ({ ...p, terraform: e.message }));
    } finally {
      setLoading(p => ({ ...p, terraform: false }));
    }
  }

  function handleSave(formData) {
    setWorkplanData({ ...formData });
    setWorkplanMode('view');
  }

  const availableDocs = [
    ...(generatedDocs.event ? [{ ...generatedDocs.event, type: 'event' }] : []),
    ...(generatedDocs.weekly ? [{ ...generatedDocs.weekly, type: 'weekly' }] : []),
    ...(generatedDocs.health ? [{ ...generatedDocs.health, type: 'health', canonical: generatedDocs.health.report }] : []),
  ];

  const eventCanonical = generatedDocs.event?.canonical || null;
  const weeklyCanonical = generatedDocs.weekly?.canonical || null;
  const healthReport = generatedDocs.health?.report || null;

  return (
    <>
      <div className="dev-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`dev-tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
        <div className="dev-tab-actions">
          {tab === 'event' && eventCanonical && (
            <>
              <button className="btn-ai" onClick={generateEventReport} disabled={loading.event}>🔄 재생성</button>
              <button className="btn-download" onClick={() => downloadHTML(eventRef, 'event-report')}>⬇ 다운로드</button>
            </>
          )}
          {tab === 'health' && healthReport && (
            <>
              <button className="btn-download" onClick={() => downloadHTML(healthRef, 'health-event-report')}>⬇ 다운로드</button>
            </>
          )}
          {tab === 'weekly' && weeklyCanonical && (
            <>
              <button className="btn-ai" onClick={generateWeeklyReport} disabled={loading.weekly}>🔄 재생성</button>
              <button className="btn-download" onClick={() => downloadHTML(weeklyRef, 'weekly-report')}>⬇ 다운로드</button>
            </>
          )}
          {tab === 'workplan' && workplanData && workplanMode === 'view' && (
            <button className="btn-download" onClick={() => downloadHTML(workplanRef, 'work-plan')}>⬇ 다운로드</button>
          )}
        </div>
      </div>

      {tab === 'event' && (
        <>
          {error.event && <div className="ai-error">⚠️ {error.event}</div>}
          {!eventCanonical
            ? <EmptyState onGenerate={generateEventReport} loading={loading.event} label="이벤트 보고서" />
            : <div ref={eventRef}><EventReport canonical={eventCanonical} /></div>
          }
        </>
      )}

      {tab === 'health' && (
        <>
          {error.health && <div className="ai-error">⚠️ {error.health}</div>}
          {!healthReport
            ? <HealthEmptyState loading={loading.health} onGenerate={generateHealthEventReport} />
            : <div ref={healthRef}><HealthEventReport data={healthReport} /></div>
          }
        </>
      )}

      {tab === 'weekly' && (
        <>
          {error.weekly && <div className="ai-error">⚠️ {error.weekly}</div>}
          {!weeklyCanonical
            ? <EmptyState onGenerate={generateWeeklyReport} loading={loading.weekly} label="주간 보고서" />
            : <div ref={weeklyRef}><WeeklyReport canonical={weeklyCanonical} /></div>
          }
        </>
      )}

      {tab === 'workplan' && (
        <>
          {error.workplan && <div className="ai-error">⚠️ {error.workplan}</div>}
          {error.terraform && <div className="ai-error">⚠️ {error.terraform}</div>}

          {!workplanData && (
            <div className="workplan-setup">
              <div className="workplan-setup-title">작업계획서 생성</div>
              <div className="workplan-setup-desc">생성된 보고서를 선택하면 AI가 작업계획서를 자동으로 만들어드립니다</div>
              {availableDocs.length === 0 ? (
                <div className="workplan-no-docs">
                  먼저 <strong>이벤트 보고서</strong> 또는 <strong>주간 보고서</strong>를 생성해주세요
                </div>
              ) : (
                <div className="workplan-doc-select">
                  <div className="workplan-doc-label">반영할 문서 선택</div>
                  <div className="workplan-doc-list">
                    {availableDocs.map((doc, i) => (
                      <button
                        key={i}
                        className={`workplan-doc-item ${selectedSourceDoc?.label === doc.label ? 'selected' : ''}`}
                        onClick={() => setSelectedSourceDoc(doc)}
                      >
                        {doc.type === 'event' ? '📋' : '📊'} {doc.label}
                      </button>
                    ))}
                  </div>
                  <button
                    className="btn-ai btn-ai-large"
                    onClick={generateWorkPlan}
                    disabled={!selectedSourceDoc || loading.workplan}
                  >
                    {loading.workplan ? '⏳ 작업계획서 생성 중...' : '✨ 작업계획서 생성'}
                  </button>
                </div>
              )}
            </div>
          )}

          {workplanData && (
            <>
              {workplanMode === 'view' ? (
                <>
                  <div ref={workplanRef}>
                    <WorkPlan data={workplanData} onEdit={() => setWorkplanMode('edit')} />
                  </div>
                  {!terraformFiles && (
                    <div className="terraform-btn-wrap">
                      <button className="btn-terraform" onClick={generateTerraform} disabled={loading.terraform}>
                        {loading.terraform ? '⏳ 테라폼 코드 생성 중...' : '🔧 테라폼 코드 생성'}
                      </button>
                    </div>
                  )}
                  {terraformFiles && (
                    <TerraformEditor
                      files={terraformFiles}
                      checkov={terraformCheckov}
                      onClose={() => { setTerraformFiles(null); setTerraformCheckov(null); }}
                    />
                  )}
                </>
              ) : (
                <WorkPlanForm initial={workplanData} onSubmit={handleSave} onCancel={() => setWorkplanMode('view')} />
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
