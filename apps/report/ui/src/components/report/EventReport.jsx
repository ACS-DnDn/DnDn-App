import SectionTitle from '../common/SectionTitle';
import NASection from '../common/NASection';

function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString('ko-KR', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  });
}

function fmtDate(iso) {
  if (!iso) return '-';
  return iso.slice(0, 10).replace(/-/g, '.');
}

function toSafeUrl(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch { return null; }
}

const SEVERITY_CLASS = { CRITICAL: 'r-hi', HIGH: 'r-hi', MEDIUM: 'r-mid', LOW: 'r-low' };
const SEVERITY_LABEL = { CRITICAL: '심각', HIGH: '상', MEDIUM: '중', LOW: '하' };

export default function EventReport({ canonical }) {
  if (!canonical) return <div className="na-box">데이터를 불러오는 중입니다...</div>;

  const { meta = {}, events = [], resources = [], collection_status = {} } = canonical;
  const triggerEvent = events[0] || {};
  const resourceEntry = resources[0] || {};
  const resource = resourceEntry.resource || {};
  const cloudtrailStatus = collection_status.cloudtrail || {};

  // 실제 Worker 구조: resources[0].extensions.security_finding
  const finding = resourceEntry.extensions?.security_finding || null;
  const isSecurityHub = !!finding;
  const safeRemediationUrl = toSafeUrl(finding?.remediation_url);

  const exposureText =
    finding?.exposure_scope === 'public' ? '있음 (인터넷 전체 노출)' :
    finding?.exposure_scope === 'internal' ? '없음 (내부망)' : '확인 필요';

  const readOnlyText =
    triggerEvent.read_only == null ? '확인 불가' :
    triggerEvent.read_only ? '예 (읽기 작업)' : '아니오 (변경 작업)';

  return (
    <div className="doc">

      {/* 헤더 */}
      <div className="doc-header">
        <div className="doc-header-top">
          <img src="/logo.png" alt="DnDn" className="doc-header-logo" />
          <div className="doc-header-meta">
            문서번호: EVT-{meta.run_id?.slice(-8) || 'UNKNOWN'}<br />
            작성일: {fmtDate(meta.generated_at)}
          </div>
        </div>
        <div className="doc-header-title">
          {isSecurityHub ? finding.title : `${triggerEvent.event_name} — ${resource.resource_id}`}
        </div>
      </div>

      {/* Overview */}
      <div className="section">
        <SectionTitle>Overview</SectionTitle>
        <table className="tbl-info" style={{ marginBottom: 0 }}>
          <tbody>
            <tr>
              <th>감지 이벤트</th>
              <td colSpan={3}>
                {isSecurityHub ? finding.description : `${triggerEvent.event_name} — ${triggerEvent.event_source}`}
              </td>
            </tr>
            <tr>
              <th>대상 리소스</th>
              <td><code>{resource.resource_id || '-'}</code> ({resource.region || '-'})</td>
              <th>AWS 계정</th>
              <td>{meta.account_id}</td>
            </tr>
            {isSecurityHub ? (
              <tr>
                <th>심각도</th>
                <td>
                  <span className={SEVERITY_CLASS[finding.severity]}>
                    <strong>{finding.severity}</strong>
                  </span>
                  {' '}({finding.control_id})
                </td>
                <th>감지 일시</th>
                <td>{fmtTime(finding.first_observed_at)} (KST)</td>
              </tr>
            ) : (
              <tr>
                <th>감지 일시</th>
                <td>{fmtTime(triggerEvent.event_time)}</td>
                <th>작업자</th>
                <td style={{ fontSize: '11.5px' }}>{triggerEvent.user_identity?.user_name || '-'}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 1. 이벤트 개요 */}
      <div className="section">
        <SectionTitle>1. 이벤트 개요</SectionTitle>
        <table className="tbl">
          <tbody>
            {isSecurityHub ? (
              <>
                <tr><th className="th-label">이벤트 유형</th><td>보안 구성 미준수</td></tr>
                <tr><th className="th-label">감지 출처</th><td>Amazon SecurityHub — {finding.control_id}</td></tr>
                <tr><th className="th-label">Finding ID</th><td style={{ fontFamily: 'monospace', fontSize: '11.5px' }}>{finding.finding_id}</td></tr>
                <tr><th className="th-label">영향 범위</th><td>{finding.description}</td></tr>
                <tr><th className="th-label">보안 표준</th><td>{finding.standards?.join(', ') || '-'}</td></tr>
                <tr><th className="th-label">이벤트 주체</th><td>{triggerEvent.user_identity?.user_name || 'Amazon SecurityHub (자동 감지)'}</td></tr>
              </>
            ) : (
              <>
                <tr><th className="th-label">이벤트 유형</th><td>{triggerEvent.event_name}</td></tr>
                <tr><th className="th-label">이벤트 소스</th><td><code>{triggerEvent.event_source}</code></td></tr>
                <tr><th className="th-label">리전</th><td>{triggerEvent.aws_region}</td></tr>
                <tr><th className="th-label">읽기 전용</th><td>{readOnlyText}</td></tr>
              </>
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
                <th style={{ width: '100px' }}>시각 (KST)</th>
                <th style={{ width: '120px' }}>구분</th>
                <th>내용</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.event_id}>
                  <td className="td-time">{fmtTime(ev.event_time)}</td>
                  <td className="td-type">{ev.event_source?.split('.')[0]}</td>
                  <td>{ev.event_name} — {ev.user_identity?.user_name || '-'}</td>
                </tr>
              ))}
              {meta.trigger?.received_at && (
                <tr>
                  <td className="td-time">{fmtTime(meta.trigger.received_at)}</td>
                  <td className="td-type">EventBridge</td>
                  <td>DnDn Worker 트리거 → canonical.json 생성</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* 3. 영향 분석 (SecurityHub만) */}
      {isSecurityHub && (
        <div className="section">
          <SectionTitle>3. 영향 분석</SectionTitle>
          <div className="sub-heading">영향 범위</div>
          <table className="tbl-info" style={{ marginBottom: '14px' }}>
            <tbody>
              <tr>
                <th>영향 리소스</th>
                <td><code>{finding.resource_display_name || resource.resource_id}</code> ({resource.region})</td>
                <th>리소스 유형</th>
                <td>{resource.resource_type}</td>
              </tr>
              <tr>
                <th>외부 노출</th>
                <td>{exposureText}</td>
                <th>준수 상태</th>
                <td style={{ fontWeight: 600, color: finding.compliance_status === 'FAILED' ? '#c00' : 'inherit' }}>
                  {finding.compliance_status}
                </td>
              </tr>
            </tbody>
          </table>

          <div className="sub-heading">위험도 분석</div>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '220px' }}>위험 항목</th>
                <th style={{ width: '55px' }}>수준</th>
                <th>분석</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="td-risk">{resource.resource_type} 미준수</td>
                <td style={{ textAlign: 'center', verticalAlign: 'middle' }}>
                  <span className={SEVERITY_CLASS[finding.severity]}>
                    {SEVERITY_LABEL[finding.severity]}
                  </span>
                </td>
                <td>{finding.description}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* 4. 보안 Finding 상세 (SecurityHub) / 3. 변경 리소스 (CloudTrail) */}
      {isSecurityHub ? (
        <div className="section">
          <SectionTitle>4. 보안 Finding 상세</SectionTitle>
          <table className="tbl">
            <tbody>
              <tr><th className="th-label">감지 서비스</th><td>Amazon SecurityHub</td></tr>
              <tr><th className="th-label">제어 ID</th><td><strong>{finding.control_id}</strong> — {finding.title}</td></tr>
              <tr><th className="th-label">보안 표준</th><td>{finding.standards?.join(', ') || '-'}</td></tr>
              <tr><th className="th-label">심각도</th><td><strong>{finding.severity}</strong> &nbsp;/&nbsp; Score: {finding.severity_normalized}</td></tr>
              <tr><th className="th-label">준수 상태</th><td>{finding.compliance_status}</td></tr>
              <tr><th className="th-label">리소스 유형</th><td><code>{resource.resource_type}</code></td></tr>
              <tr><th className="th-label">계정 별칭</th><td>{finding.account_alias || '-'}</td></tr>
              <tr><th className="th-label">최초 감지</th><td>{fmtTime(finding.first_observed_at)}</td></tr>
              <tr><th className="th-label">최근 감지</th><td>{fmtTime(finding.last_observed_at)}</td></tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="section">
          <SectionTitle>3. 변경 리소스</SectionTitle>
          {resources.length === 0 ? (
            <div className="na-box">연관 리소스 정보 없음</div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>리소스 ID</th>
                  <th>유형</th>
                  <th>리전</th>
                  <th style={{ textAlign: 'center' }}>변경 건수</th>
                  <th>Config 상태</th>
                </tr>
              </thead>
              <tbody>
                {resources.map((r, idx) => {
                  const cfg = r.config || {};
                  const rowKey = r.resource?.resource_id || `row-${idx}`;
                  return (
                    <tr key={rowKey}>
                      <td><code>{r.resource?.resource_id}</code></td>
                      <td>{r.resource?.resource_type}</td>
                      <td>{r.resource?.region}</td>
                      <td style={{ textAlign: 'center' }}>{r.change_summary?.event_count ?? '-'}</td>
                      <td>
                        {cfg.status === 'NA'
                          ? <span style={{ color: '#888' }}>N/A — {cfg.na_reason}</span>
                          : '변경 없음'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* 5. 권장 조치 */}
      {isSecurityHub && safeRemediationUrl && (
        <div className="section">
          <SectionTitle>5. 권장 조치</SectionTitle>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '70px' }}>구분</th>
                <th style={{ width: '44px' }}>순서</th>
                <th>조치 내용</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="td-step">참고</td>
                <td className="td-step">①</td>
                <td><a href={safeRemediationUrl} target="_blank" rel="noopener noreferrer">{safeRemediationUrl}</a></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* 푸터 */}
      <div className="doc-footer">
        <span>EVT-{meta.run_id?.slice(-8) || 'UNKNOWN'} &nbsp;/&nbsp; {fmtDate(meta.generated_at)}</span>
      </div>
    </div>
  );
}
