import SectionTitle from '../common/SectionTitle';
import NASection from '../common/NASection';

function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
}

function fmtDate(iso) {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

const SEVERITY_CLASS = {
  HIGH: 'r-hi',
  MEDIUM: 'r-mid',
  LOW: 'r-low',
};

const CATEGORY_LABEL = {
  COST_OPTIMIZATION: '비용 최적화',
  FAULT_TOLERANCE: '내결함성',
  SERVICE_LIMITS: '서비스 한도',
  PERFORMANCE: '성능',
  SECURITY: '보안',
};

export default function WeeklyReport({ canonical }) {
  const { meta, events = [], resources = [], extensions = {}, collection_status = {} } = canonical;
  const advisorChecks = extensions.advisor_checks || [];
  const cloudtrailStatus = collection_status.cloudtrail || {};

  // advisor_checks 카테고리별 분류
  const checksByCategory = advisorChecks.reduce((acc, check) => {
    const cat = check.category || 'ETC';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(check);
    return acc;
  }, {});

  return (
    <div className="doc">

      {/* 헤더 */}
      <div className="doc-header">
        <div className="doc-header-top">
          <span className="doc-header-logo">DnDn</span>
          <div className="doc-header-meta">
            수집 계정: {meta.account_id}<br />
            보고 기간: {fmtDate(meta.time_range?.start)} ~ {fmtDate(meta.time_range?.end)}
          </div>
        </div>
        <div className="doc-header-title">주간 보고서 — {meta.partition?.year}년 {meta.partition?.week}주차</div>
      </div>

      {/* 문서 기본 정보 */}
      <table className="tbl-info">
        <tbody>
          <tr>
            <th>수집 계정</th>
            <td>{meta.account_id}</td>
            <th>리전</th>
            <td>{meta.regions?.join(', ') || '-'}</td>
          </tr>
          <tr>
            <th>보고 기간</th>
            <td>{fmtDate(meta.time_range?.start)} ~ {fmtDate(meta.time_range?.end)}</td>
            <th>생성 일시</th>
            <td>{fmtTime(meta.generated_at)}</td>
          </tr>
          <tr>
            <th>스키마 버전</th>
            <td>{meta.schema_version}</td>
            <th>수집기 버전</th>
            <td>{meta.collector?.version}</td>
          </tr>
        </tbody>
      </table>

      {/* 1. 변경 타임라인 */}
      <div className="section">
        <SectionTitle>1. 변경 타임라인</SectionTitle>
        {cloudtrailStatus.status === 'NA' ? (
          <NASection reason={cloudtrailStatus.na_reason} message={cloudtrailStatus.message} />
        ) : events.length === 0 ? (
          <div className="na-box">이번 주 변경 이벤트 없음</div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '130px' }}>시각 (KST)</th>
                <th style={{ width: '180px', textAlign: 'left' }}>이벤트</th>
                <th style={{ width: '160px', textAlign: 'left' }}>리소스</th>
                <th style={{ textAlign: 'left' }}>작업자</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.event_id}>
                  <td className="td-time">{fmtTime(ev.event_time)}</td>
                  <td><code>{ev.event_name}</code></td>
                  <td>{ev.resources?.[0]?.resource_id || '-'}</td>
                  <td style={{ fontSize: '11.5px', color: '#555' }}>
                    {ev.user_identity?.arn?.split('/').slice(-1)[0] || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 2. 변경 리소스 현황 */}
      <div className="section">
        <SectionTitle>2. 변경 리소스 현황</SectionTitle>
        {resources.length === 0 ? (
          <div className="na-box">이번 주 변경 리소스 없음</div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>리소스 ID</th>
                <th style={{ textAlign: 'left' }}>유형</th>
                <th style={{ textAlign: 'left' }}>리전</th>
                <th style={{ textAlign: 'center' }}>변경 건수</th>
                <th style={{ textAlign: 'left' }}>Config 상태</th>
              </tr>
            </thead>
            <tbody>
              {resources.map((r) => {
                const cfg = r.config || {};
                return (
                  <tr key={r.key}>
                    <td><code>{r.resource?.resource_id || '-'}</code></td>
                    <td>{r.resource?.resource_type || '-'}</td>
                    <td>{r.resource?.region || '-'}</td>
                    <td style={{ textAlign: 'center' }}>
                      {r.change_summary?.event_count ?? '-'}
                    </td>
                    <td>
                      {cfg.status === 'NA'
                        ? <span style={{ color: '#888' }}>N/A — {cfg.na_reason}</span>
                        : '정상'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 3. 최적화 권장 항목 (advisor_checks) */}
      <div className="section">
        <SectionTitle>3. 최적화 권장 항목</SectionTitle>
        {advisorChecks.length === 0 ? (
          <div className="na-box">권장 항목 없음</div>
        ) : (
          Object.entries(checksByCategory).map(([category, checks]) => (
            <div key={category} style={{ marginBottom: '14px' }}>
              <div className="sub-title">{CATEGORY_LABEL[category] || category}</div>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: '55px' }}>심각도</th>
                    <th style={{ width: '180px', textAlign: 'left' }}>항목</th>
                    <th style={{ textAlign: 'left' }}>내용</th>
                    <th style={{ textAlign: 'left' }}>권장 조치</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((check) => (
                    <tr key={check.check_id}>
                      <td style={{ textAlign: 'center' }}>
                        <span className={SEVERITY_CLASS[check.severity] || ''}>
                          {check.severity}
                        </span>
                      </td>
                      <td>{check.title}</td>
                      <td style={{ fontSize: '12px' }}>{check.summary}</td>
                      <td style={{ fontSize: '12px' }}>{check.recommendation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))
        )}
      </div>

      {/* 수집 상태 */}
      <div className="section">
        <SectionTitle>4. 수집 상태</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>모듈</th>
              <th style={{ textAlign: 'center' }}>상태</th>
              <th style={{ textAlign: 'left' }}>비고</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(collection_status).map(([module, status]) => (
              <tr key={module}>
                <td><code>{module}</code></td>
                <td style={{ textAlign: 'center' }}>
                  <span className={
                    status.status === 'OK' ? 'r-low' :
                    status.status === 'NA' ? 'r-mid' : 'r-hi'
                  }>
                    {status.status}
                  </span>
                </td>
                <td style={{ fontSize: '12px', color: '#666' }}>
                  {status.na_reason
                    ? `N/A — ${status.na_reason}`
                    : status.message || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 푸터 */}
      <div className="doc-footer">
        <span>수집 계정: {meta.account_id} | {fmtDate(meta.time_range?.start)} ~ {fmtDate(meta.time_range?.end)}</span>
        <span>run_id: {meta.run_id}</span>
      </div>
    </div>
  );
}