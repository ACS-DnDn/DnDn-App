import { useState } from 'react';
import SectionTitle from '../common/SectionTitle';

const EMPTY_FORM = {
  title: '',
  reason: '',
  resource: '',
  account_id: '',
  scheduled_at: '',
  assignee: '',
  before_after: [{ item: '', before: '', after: '' }],
  risks: [{ item: '', level: 'MEDIUM', description: '' }],
  rollback: { trigger: '', method: '', estimated_time: '', assignee: '' },
  steps: [{ name: '', description: '', executor: 'Terraform', assignee: 'devops' }],
  pr_url: '',
};

export default function WorkPlanForm({ initial = EMPTY_FORM, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);

  // 최상위 필드 변경
  function setField(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // 배열 필드 변경
  function setArrayField(key, index, subKey, value) {
    setForm((f) => {
      const arr = [...f[key]];
      arr[index] = { ...arr[index], [subKey]: value };
      return { ...f, [key]: arr };
    });
  }

  // 배열 행 추가
  function addRow(key, emptyRow) {
    setForm((f) => ({ ...f, [key]: [...f[key], emptyRow] }));
  }

  // 배열 행 삭제
  function removeRow(key, index) {
    setForm((f) => ({ ...f, [key]: f[key].filter((_, i) => i !== index) }));
  }

  // rollback 필드
  function setRollback(key, value) {
    setForm((f) => ({ ...f, rollback: { ...f.rollback, [key]: value } }));
  }

  return (
    <div className="doc">

      {/* 헤더 */}
      <div className="doc-header">
        <div className="doc-header-top">
          <span className="doc-header-logo">DnDn</span>
        </div>
        <div className="doc-header-title">작업계획서 작성</div>
      </div>

      {/* 기본 정보 */}
      <table className="tbl-info" style={{ marginBottom: '22px' }}>
        <tbody>
          <tr>
            <th>작업명</th>
            <td colSpan={3}>
              <input style={inputStyle} value={form.title}
                onChange={(e) => setField('title', e.target.value)}
                placeholder="작업명을 입력하세요" />
            </td>
          </tr>
          <tr>
            <th>작업 이유</th>
            <td colSpan={3}>
              <input style={inputStyle} value={form.reason}
                onChange={(e) => setField('reason', e.target.value)}
                placeholder="작업 이유를 입력하세요" />
            </td>
          </tr>
          <tr>
            <th>대상 리소스</th>
            <td>
              <input style={inputStyle} value={form.resource}
                onChange={(e) => setField('resource', e.target.value)}
                placeholder="리소스 ID" />
            </td>
            <th>AWS 계정</th>
            <td>
              <input style={inputStyle} value={form.account_id}
                onChange={(e) => setField('account_id', e.target.value)}
                placeholder="123456789012" />
            </td>
          </tr>
          <tr>
            <th>작업 예정일</th>
            <td>
              <input style={inputStyle} value={form.scheduled_at}
                onChange={(e) => setField('scheduled_at', e.target.value)}
                placeholder="2026.03.01 02:00 ~ 04:00" />
            </td>
            <th>담당자</th>
            <td>
              <input style={inputStyle} value={form.assignee}
                onChange={(e) => setField('assignee', e.target.value)}
                placeholder="devops@dndn" />
            </td>
          </tr>
        </tbody>
      </table>

      {/* 1. Before / After */}
      <div className="section">
        <SectionTitle>1. 변경 Before / After</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '155px', textAlign: 'left' }}>항목</th>
              <th className="th-before" style={{ width: '35%' }}>Before</th>
              <th className="th-after" style={{ width: '35%' }}>After</th>
              <th style={{ width: '40px' }}></th>
            </tr>
          </thead>
          <tbody>
            {form.before_after.map((row, i) => (
              <tr key={i}>
                <td><input style={inputStyle} value={row.item}
                  onChange={(e) => setArrayField('before_after', i, 'item', e.target.value)}
                  placeholder="항목명" /></td>
                <td><input style={inputStyle} value={row.before}
                  onChange={(e) => setArrayField('before_after', i, 'before', e.target.value)}
                  placeholder="변경 전" /></td>
                <td><input style={inputStyle} value={row.after}
                  onChange={(e) => setArrayField('before_after', i, 'after', e.target.value)}
                  placeholder="변경 후" /></td>
                <td style={{ textAlign: 'center' }}>
                  <button style={btnRemove} onClick={() => removeRow('before_after', i)}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button style={btnAdd}
          onClick={() => addRow('before_after', { item: '', before: '', after: '' })}>
          + 행 추가
        </button>
      </div>

      {/* 2. 위험도 분석 */}
      <div className="section">
        <SectionTitle>2. 위험도 분석</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '185px', textAlign: 'left' }}>위험 항목</th>
              <th style={{ width: '80px' }}>수준</th>
              <th>분석</th>
              <th style={{ width: '40px' }}></th>
            </tr>
          </thead>
          <tbody>
            {form.risks.map((risk, i) => (
              <tr key={i}>
                <td><input style={inputStyle} value={risk.item}
                  onChange={(e) => setArrayField('risks', i, 'item', e.target.value)}
                  placeholder="위험 항목" /></td>
                <td>
                  <select style={inputStyle} value={risk.level}
                    onChange={(e) => setArrayField('risks', i, 'level', e.target.value)}>
                    <option value="HIGH">상</option>
                    <option value="MEDIUM">중</option>
                    <option value="LOW">하</option>
                  </select>
                </td>
                <td><input style={inputStyle} value={risk.description}
                  onChange={(e) => setArrayField('risks', i, 'description', e.target.value)}
                  placeholder="위험 분석 내용" /></td>
                <td style={{ textAlign: 'center' }}>
                  <button style={btnRemove} onClick={() => removeRow('risks', i)}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button style={btnAdd}
          onClick={() => addRow('risks', { item: '', level: 'MEDIUM', description: '' })}>
          + 행 추가
        </button>
      </div>

      {/* 3. 롤백 계획 */}
      <div className="section">
        <SectionTitle>3. 롤백 계획</SectionTitle>
        <table className="tbl">
          <tbody>
            <tr>
              <th className="th-label">롤백 트리거</th>
              <td><input style={inputStyle} value={form.rollback.trigger}
                onChange={(e) => setRollback('trigger', e.target.value)}
                placeholder="롤백 트리거 조건" /></td>
            </tr>
            <tr>
              <th className="th-label">롤백 방법</th>
              <td><input style={inputStyle} value={form.rollback.method}
                onChange={(e) => setRollback('method', e.target.value)}
                placeholder="롤백 방법" /></td>
            </tr>
            <tr>
              <th className="th-label">예상 시간</th>
              <td><input style={inputStyle} value={form.rollback.estimated_time}
                onChange={(e) => setRollback('estimated_time', e.target.value)}
                placeholder="약 5~10분" /></td>
            </tr>
            <tr>
              <th className="th-label">담당자</th>
              <td><input style={inputStyle} value={form.rollback.assignee}
                onChange={(e) => setRollback('assignee', e.target.value)}
                placeholder="devops@dndn" /></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 4. 작업 절차 */}
      <div className="section">
        <SectionTitle>4. 작업 절차</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '44px' }}>단계</th>
              <th style={{ width: '115px', textAlign: 'left' }}>작업</th>
              <th style={{ textAlign: 'left' }}>내용</th>
              <th style={{ width: '90px' }}>실행</th>
              <th style={{ width: '80px' }}>담당</th>
              <th style={{ width: '40px' }}></th>
            </tr>
          </thead>
          <tbody>
            {form.steps.map((step, i) => (
              <tr key={i}>
                <td className="td-step">{'①②③④⑤⑥⑦⑧⑨⑩'[i] || i + 1}</td>
                <td><input style={inputStyle} value={step.name}
                  onChange={(e) => setArrayField('steps', i, 'name', e.target.value)}
                  placeholder="작업명" /></td>
                <td><input style={inputStyle} value={step.description}
                  onChange={(e) => setArrayField('steps', i, 'description', e.target.value)}
                  placeholder="작업 내용" /></td>
                <td>
                  <select style={inputStyle} value={step.executor}
                    onChange={(e) => setArrayField('steps', i, 'executor', e.target.value)}>
                    <option value="Terraform">Terraform</option>
                    <option value="수동">수동</option>
                    <option value="자동">자동</option>
                  </select>
                </td>
                <td><input style={inputStyle} value={step.assignee}
                  onChange={(e) => setArrayField('steps', i, 'assignee', e.target.value)}
                  placeholder="담당자" /></td>
                <td style={{ textAlign: 'center' }}>
                  <button style={btnRemove} onClick={() => removeRow('steps', i)}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button style={btnAdd}
          onClick={() => addRow('steps', { name: '', description: '', executor: 'Terraform', assignee: 'devops' })}>
          + 행 추가
        </button>
      </div>

      {/* PR URL */}
      <div className="section">
        <table className="tbl">
          <tbody>
            <tr>
              <th className="th-label">Terraform PR</th>
              <td><input style={inputStyle} value={form.pr_url}
                onChange={(e) => setField('pr_url', e.target.value)}
                placeholder="https://github.com/..." /></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 하단 버튼 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
        {onCancel && (
          <button style={btnCancel} onClick={onCancel}>취소</button>
        )}
        <button style={btnSubmit} onClick={() => onSubmit(form)}>저장</button>
      </div>

    </div>
  );
}

// 인라인 스타일
const inputStyle = {
  width: '100%',
  padding: '4px 6px',
  fontSize: '12px',
  border: '1px solid #ccc',
  borderRadius: '2px',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
};

const btnAdd = {
  marginTop: '6px',
  padding: '4px 12px',
  fontSize: '11.5px',
  background: '#f0f0f0',
  border: '1px solid #bbb',
  borderRadius: '2px',
  cursor: 'pointer',
  color: '#444',
};

const btnRemove = {
  padding: '2px 6px',
  fontSize: '11px',
  background: '#fff',
  border: '1px solid #ddd',
  borderRadius: '2px',
  cursor: 'pointer',
  color: '#999',
};

const btnSubmit = {
  padding: '6px 20px',
  fontSize: '12px',
  background: '#1f3864',
  color: '#fff',
  border: 'none',
  borderRadius: '3px',
  cursor: 'pointer',
};

const btnCancel = {
  padding: '6px 20px',
  fontSize: '12px',
  background: '#fff',
  color: '#444',
  border: '1px solid #bbb',
  borderRadius: '3px',
  cursor: 'pointer',
};