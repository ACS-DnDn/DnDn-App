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

const SEVERITY_CLASS = { CRITICAL: 'r-hi', HIGH: 'r-hi', MEDIUM: 'r-mid', LOW: 'r-low' };
const SEVERITY_LABEL = { CRITICAL: '심각', HIGH: '상', MEDIUM: '중', LOW: '하' };

export default function EventReport({ canonical }) {
  const { meta, events = [], resources = [], collection_status = {}, extensions = {} } = canonical;
  const triggerEvent = events[0] || {};
  const resource = resources[0]?.resource || {};
  const cloudtrailStatus = collection_status.cloudtrail || {};
  const finding = extensions.securityhub_finding || null;
  const isSecurityHub = !!finding;

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
                  <span className={SEVERITY_CLASS[finding.severity?.label]}>
                    <strong>{finding.severity?.label}</strong>
                  </span>
                  {' '}({finding.compliance?.standards_control_arn?.split('/').slice(-1)[0]})
                </td>
                <th>감지 일시</th>
                <td>{fmtTime(meta.trigger?.event_time)} (KST)</td>
              </tr>
            ) : (
              <tr>
                <th>감지 일시</th>
                <td>{fmtTime(triggerEvent.event_time)}</td>
                <th>작업자</th>
                <td style={{ fontSize: '11.5px' }}>{triggerEvent.user_identity?.arn || '-'}</td>
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
                <tr><th className="th-label">감지 출처</th><td>Amazon SecurityHub — {finding.compliance?.standards_control_arn?.split('/').slice(-1)[0]}</td></tr>
                <tr><th className="th-label">Finding ID</th><td style={{ fontFamily: 'monospace', fontSize: '11.5px' }}>{finding.id}</td></tr>
                <tr><th className="th-label">영향 범위</th><td>{finding.description}</td></tr>
                <tr><th className="th-label">이벤트 주체</th><td>{triggerEvent.user_identity?.arn || 'Amazon SecurityHub (자동 감지)'}</td></tr>
              </>
            ) : (
              <>
                <tr><th className="th-label">이벤트 유형</th><td>{triggerEvent.event_name}</td></tr>
                <tr><th className="th-label">이벤트 소스</th><td><code>{triggerEvent.event_source}</code></td></tr>
                <tr><th className="th-label">리전</th><td>{triggerEvent.aws_region}</td></tr>
                <tr><th className="th-label">읽기 전용</th><td>{triggerEvent.read_only ? '예 (읽기 작업)' : '아니오 (변경 작업)'}</td></tr>
                {meta.trigger?.selector?.catalog && (
                  <tr>
                    <th className="th-label">감지 규칙</th>
                    <td>{meta.trigger.selector.catalog.pack_id} / {meta.trigger.selector.catalog.item_id}</td>
                  </tr>
                )}
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
                  <td>{ev.event_name} — {ev.user_identity?.arn || '-'}</td>
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
                <td><code>{resource.resource_id}</code> ({resource.region})</td>
                <th>리소스 유형</th>
                <td>{resource.resource_type}</td>
              </tr>
              <tr>
                <th>외부 노출</th>
                <td>{finding.description?.includes('0.0.0.0/0') ? '있음 (인터넷 전체 노출)' : '확인 필요'}</td>
                <th>현재 상태</th>
                <td style={{ fontWeight: 600, color: '#c00' }}>미조치</td>
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
                <td className="td-risk">{resource.resource_type} 노출</td>
                <td style={{ textAlign: 'center', verticalAlign: 'middle' }}>
                  <span className={SEVERITY_CLASS[finding.severity?.label]}>
                    {SEVERITY_LABEL[finding.severity?.label]}
                  </span>
                </td>
                <td>{finding.description}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* 3 or 4. 변경 리소스 (CloudTrail) / Finding 상세 (SecurityHub) */}
      {isSecurityHub ? (
        <div className="section">
          <SectionTitle>4. 보안 Finding 상세</SectionTitle>
          <table className="tbl">
            <tbody>
              <tr><th className="th-label">감지 서비스</th><td>{finding.source}</td></tr>
              <tr><th className="th-label">Finding 유형</th><td>{finding.title}</td></tr>
              <tr>
                <th className="th-label">보안 표준</th>
                <td>{finding.compliance?.standards_control_arn?.split('/').slice(0, 4).join('/')}</td>
              </tr>
              <tr>
                <th className="th-label">제어 ID</th>
                <td>
                  <strong>{finding.compliance?.standards_control_arn?.split('/').slice(-1)[0]}</strong>
                  {' '}— {finding.title}
                </td>
              </tr>
              <tr>
                <th className="th-label">심각도</th>
                <td>
                  <strong>{finding.severity?.label}</strong> &nbsp;/&nbsp;
                  Score: {finding.severity?.normalized}
                </td>
              </tr>
              <tr>
                <th className="th-label">리소스 유형</th>
                <td><code>{resource.resource_type}</code></td>
              </tr>
              <tr>
                <th className="th-label">레코드 상태</th>
                <td>{finding.compliance?.status}</td>
              </tr>
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

      {/* 5. 권장 조치 (SecurityHub만) */}
      {isSecurityHub && finding.remediation && (
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
                <td className="td-step">조치</td>
                <td className="td-step">①</td>
                <td>{finding.remediation.text}</td>
              </tr>
              {finding.remediation.url && (
                <tr>
                  <td className="td-step">참고</td>
                  <td className="td-step">②</td>
                  <td><a href={finding.remediation.url} target="_blank" rel="noreferrer">{finding.remediation.url}</a></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* 푸터 */}
      <div className="doc-footer">
        <span>EVT-{meta.run_id?.slice(-8)} &nbsp;/&nbsp; {fmtDate(meta.generated_at)}</span>
      </div>
    </div>
  );
}
