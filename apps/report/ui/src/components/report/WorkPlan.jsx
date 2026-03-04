import SectionTitle from '../common/SectionTitle';

export default function WorkPlan({ data, onEdit }) {
  const {
    title = '',
    doc_id = '',
    created_at = '',
    reason = '',
    resource = '',
    scheduled_at = '',
    account_id = '',
    assignee = '',
    before_after = [],
    risks = [],
    rollback = {},
    steps = [],
    pr_url = '',
  } = data || {};

  return (
    <div className="doc">

      {/* 헤더 */}
      <div className="doc-header">
        <div className="doc-header-top">
          <span className="doc-header-logo">DnDn</span>
          <div className="doc-header-meta">
            문서번호: {doc_id || '-'}<br />
            작성일: {created_at?.slice(0, 10).replace(/-/g, '.') || '-'}
          </div>
        </div>
        <div className="doc-header-title">{title || '작업계획서'}</div>
      </div>

      {/* 수정 버튼 */}
      {onEdit && (
        <div style={{ textAlign: 'right', marginBottom: '12px' }}>
          <button
            onClick={onEdit}
            style={{
              padding: '5px 14px',
              fontSize: '12px',
              background: '#1f3864',
              color: '#fff',
              border: 'none',
              borderRadius: '3px',
              cursor: 'pointer',
            }}
          >
            수정
          </button>
        </div>
      )}

      {/* 문서 기본 정보 */}
      <table className="tbl-info">
        <tbody>
          <tr>
            <th>작업명</th>
            <td colSpan={3} className="td-main">{title || '-'}</td>
          </tr>
          <tr>
            <th>작업 이유</th>
            <td colSpan={3}>{reason || '-'}</td>
          </tr>
          <tr>
            <th>대상 리소스</th>
            <td><code>{resource || '-'}</code></td>
            <th>AWS 계정</th>
            <td>{account_id || '-'}</td>
          </tr>
          <tr>
            <th>작업 예정일</th>
            <td>{scheduled_at || '-'}</td>
            <th>담당자</th>
            <td>{assignee || '-'}</td>
          </tr>
        </tbody>
      </table>

      {/* 1. Before / After */}
      <div className="section">
        <SectionTitle>1. 변경 Before / After</SectionTitle>
        {before_after.length === 0 ? (
          <div className="na-box">변경 정보 없음</div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '155px', textAlign: 'left' }}>항목</th>
                <th className="th-before" style={{ width: '40%' }}>Before</th>
                <th className="th-after">After</th>
              </tr>
            </thead>
            <tbody>
              {before_after.map((row, i) => (
                <tr key={i}>
                  <td className="td-item">{row.item}</td>
                  <td className="td-before">{row.before}</td>
                  <td className="td-after">{row.after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 2. 위험도 분석 */}
      <div className="section">
        <SectionTitle>2. 위험도 분석</SectionTitle>
        {risks.length === 0 ? (
          <div className="na-box">위험도 정보 없음</div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '185px' }}>위험 항목</th>
                <th style={{ width: '55px' }}>수준</th>
                <th>분석</th>
              </tr>
            </thead>
            <tbody>
              {risks.map((risk, i) => (
                <tr key={i}>
                  <td>{risk.item}</td>
                  <td style={{ textAlign: 'center' }}>
                    <span className={
                      risk.level === 'HIGH' ? 'r-hi' :
                      risk.level === 'MEDIUM' ? 'r-mid' : 'r-low'
                    }>
                      {risk.level === 'HIGH' ? '상' :
                       risk.level === 'MEDIUM' ? '중' : '하'}
                    </span>
                  </td>
                  <td>{risk.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 3. 롤백 계획 */}
      <div className="section">
        <SectionTitle>3. 롤백 계획</SectionTitle>
        <table className="tbl">
          <tbody>
            <tr>
              <th className="th-label">롤백 트리거</th>
              <td>{rollback.trigger || '-'}</td>
            </tr>
            <tr>
              <th className="th-label">롤백 방법</th>
              <td>{rollback.method || '-'}</td>
            </tr>
            <tr>
              <th className="th-label">예상 시간</th>
              <td>{rollback.estimated_time || '-'}</td>
            </tr>
            <tr>
              <th className="th-label">담당자</th>
              <td>{rollback.assignee || '-'}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 4. 작업 절차 */}
      <div className="section">
        <SectionTitle>4. 작업 절차</SectionTitle>
        {steps.length === 0 ? (
          <div className="na-box">작업 절차 없음</div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '44px' }}>단계</th>
                <th style={{ width: '115px', textAlign: 'left' }}>작업</th>
                <th style={{ textAlign: 'left' }}>내용</th>
                <th style={{ width: '78px' }}>실행</th>
                <th style={{ width: '58px' }}>담당</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step, i) => (
                <tr key={i}>
                  <td className="td-step">{'①②③④⑤⑥⑦⑧⑨⑩'[i] || i + 1}</td>
                  <td>{step.name}</td>
                  <td>{step.description}</td>
                  <td className="td-exec">{step.executor}</td>
                  <td className="td-exec">{step.assignee}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pr_url && (
          <p className="note">
            Terraform PR: <a href={pr_url} target="_blank" rel="noreferrer">{pr_url}</a>
          </p>
        )}
      </div>

      {/* 푸터 */}
      <div className="doc-footer">
        <span>{pr_url || '-'}</span>
        <span>{doc_id} / {created_at?.slice(0, 10).replace(/-/g, '.') || '-'}</span>
      </div>
    </div>
  );
}