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

export default function EventReport({ canonical }) {
  const { meta, events = [], resources = [], collection_status = {} } = canonical;
  const triggerEvent = events[0] || {};
  const resource = resources[0]?.resource || {};
  const cloudtrailStatus = collection_status.cloudtrail || {};

  return (
    <div className="doc">

      {/* 헤더 */}
      <div className="doc-header">
        <div className="doc-header-top">
          <span className="doc-header-logo">DnDn</span>
          <div className="doc-header-meta">
            문서번호: EVT-{meta.run_id?.slice(-8) || 'UNKNOWN'}<br />
            작성일: {fmtDate(meta.generated_at)}
          </div>
        </div>
        <div className="doc-header-title">
          {triggerEvent.event_name || '이벤트'} — {resource.resource_id || '리소스 정보 없음'}
        </div>
      </div>

      {/* 문서 기본 정보 */}
      <table className="tbl-info">
        <tbody>
          <tr>
            <th>이벤트 ID</th>
            <td colSpan={3} className="td-main">{triggerEvent.event_id || '-'}</td>
          </tr>
          <tr>
            <th>감지 일시</th>
            <td>{fmtTime(triggerEvent.event_time)}</td>
            <th>생성 일시</th>
            <td>{fmtTime(meta.generated_at)}</td>
          </tr>
          <tr>
            <th>감지 방법</th>
            <td>{meta.trigger?.source || 'EVENTBRIDGE'} → DnDn Worker</td>
            <th>AWS 계정</th>
            <td>{meta.account_id}</td>
          </tr>
          <tr>
            <th>대상 리소스</th>
            <td><code>{resource.resource_id || '-'}</code> ({resource.region || '-'})</td>
            <th>리소스 유형</th>
            <td>{resource.resource_type || '-'}</td>
          </tr>
          <tr>
            <th>작업자</th>
            <td colSpan={3}>{triggerEvent.user_identity?.arn || '-'}</td>
          </tr>
        </tbody>
      </table>

      {/* 1. 이벤트 개요 */}
      <div className="section">
        <SectionTitle>1. 이벤트 개요</SectionTitle>
        <table className="tbl">
          <tbody>
            <tr>
              <th className="th-label">이벤트 유형</th>
              <td>{triggerEvent.event_name || '-'}</td>
            </tr>
            <tr>
              <th className="th-label">이벤트 소스</th>
              <td><code>{triggerEvent.event_source || '-'}</code></td>
            </tr>
            <tr>
              <th className="th-label">리전</th>
              <td>{triggerEvent.aws_region || '-'}</td>
            </tr>
            <tr>
              <th className="th-label">읽기 전용</th>
              <td>{triggerEvent.read_only ? '예 (읽기 작업)' : '아니오 (변경 작업)'}</td>
            </tr>
            {meta.trigger?.selector?.catalog && (
              <tr>
                <th className="th-label">감지 규칙</th>
                <td>
                  {meta.trigger.selector.catalog.pack_id} / {meta.trigger.selector.catalog.item_id}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 2. 이벤트 타임라인 */}
      <div className="section">
        <SectionTitle>2. 이벤트 타임라인</SectionTitle>
        {cloudtrailStatus.status === 'NA' ? (
          <NASection reason={cloudtrailStatus.na_reason} message={cloudtrailStatus.message} />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '130px' }}>시각 (KST)</th>
                <th style={{ width: '160px', textAlign: 'left' }}>구분</th>
                <th style={{ textAlign: 'left' }}>내용</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.event_id}>
                  <td className="td-time">{fmtTime(ev.event_time)}</td>
                  <td className="td-type">{ev.event_name}</td>
                  <td>
                    <code>{ev.event_source}</code> — {ev.user_identity?.arn || '-'}
                  </td>
                </tr>
              ))}
              {meta.trigger && (
                <tr>
                  <td className="td-time">{fmtTime(meta.trigger.received_at)}</td>
                  <td className="td-type">EventBridge 수신</td>
                  <td>DnDn Worker 트리거 → canonical.json 생성</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* 3. 변경 리소스 */}
      <div className="section">
        <SectionTitle>3. 변경 리소스</SectionTitle>
        {resources.length === 0 ? (
          <div className="na-box">연관 리소스 정보 없음</div>
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
                      {r.change_summary?.event_count ?? r.event_count ?? '-'}
                    </td>
                    <td>
                      {cfg.status === 'NA'
                        ? <span style={{ color: '#888' }}>N/A — {cfg.na_reason}</span>
                        : cfg.status === 'OK'
                        ? (cfg.before || cfg.after
                            ? `${cfg.before ?? '-'} → ${cfg.after ?? '-'}`
                            : '변경 없음')
                        : cfg.status || '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 푸터 */}
      <div className="doc-footer">
        <span>수집 계정: {meta.account_id} | 생성: {fmtTime(meta.generated_at)}</span>
        <span>run_id: {meta.run_id}</span>
      </div>
    </div>
  );
}