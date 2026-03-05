import SectionTitle from '../common/SectionTitle';

function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return `${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function fmtDate(iso) {
  if (!iso) return '-';
  return iso.slice(0,10).replace(/-/g,'.');
}

const MOCK = {
  kpi: {
    changes: '3건',
    unauthorized: '0건',
    security: 'CRITICAL 1건',
    cost_delta: '▲ +19%',
  },
  changes: {
    total: '총 3건 (승인 3건 / 미승인 0건)',
    security: 'SecurityHub CRITICAL 1건 — EC2.19 SSH 포트 노출',
    cost: '이번 주 $1,240 / 전주 $1,041 — ▲ +$199 (+19%)',
    rfc: 'RFC-2026-0221-002 결재 완료 (EC2 스케일업)',
  },
  timeline: [
    { date: '02.23 10:15', actor: 'jenkins', resource: 'my-eks-cluster', action: 'UpdateClusterVersion', result: 'ok' },
    { date: '02.24 09:30', actor: 'terraform', resource: 'i-0abc123def456', action: 'StopInstances', result: 'ok' },
    { date: '02.26 18:00', actor: 'admin', resource: 'sg-0abc123def456', action: 'AuthorizeSecurityGroupIngress', result: 'warn' },
  ],
  resources: [
    { id: 'my-eks-cluster', type: 'EKS', item: '클러스터 버전', change: '1.28 → 1.29', note: 'RFC-2026-0221-001' },
    { id: 'i-0abc123def456', type: 'EC2', item: '인스턴스 타입', change: 't3.medium → t3.large', note: 'RFC-2026-0221-002' },
    { id: 'sg-0abc123def456', type: 'EC2', item: 'Inbound 규칙', change: 'SSH 0.0.0.0/0 추가', note: '⚠ 미승인 변경' },
  ],
  cost: {
    services: [
      { name: 'EC2', prev: '$620', curr: '$740', delta: '+$120', pct: '+19%', up: true },
      { name: 'EKS', prev: '$310', curr: '$380', delta: '+$70', pct: '+23%', up: true },
      { name: 'S3', prev: '$111', curr: '$120', delta: '+$9', pct: '+8%', up: true },
    ],
    total: { prev: '$1,041', curr: '$1,240', delta: '+$199', pct: '+19%' },
    advisors: [
      { item: '미사용 Elastic IP', resource: 'eipalloc-0abc123', status: '주의', action: '미사용 EIP release 또는 인스턴스 연결' },
      { item: '미연결 EBS 볼륨', resource: 'vol-0abc123def456', status: '주의', action: '스냅샷 후 삭제 또는 태그 관리' },
    ],
  },
  security: {
    findings: [
      { severity: 'CRITICAL', content: 'EC2.19 — 보안그룹 SSH 포트(22) 0.0.0.0/0 허용', trigger: 'SecurityHub', new: '1건', resolved: '0건', newRed: true },
    ],
    standard: 'AWS Foundational Security Best Practices v1.0.0',
    analyzer: [
      { type: 'S3 버킷', resource: 'dndn-logs', content: '퍼블릭 읽기 접근 허용', status: 'warn' },
    ],
    controls: [
      { item: 'AWS Config', status: 'ok', note: '활성화 — 전 리전 기록 중' },
      { item: 'GuardDuty', status: 'ok', note: '활성화 — 위협 감지 중' },
      { item: 'CloudTrail', status: 'ok', note: '활성화 — S3 로깅 중' },
      { item: 'IAM MFA', status: 'warn', note: 'admin 계정 MFA 미설정' },
    ],
  },
  iam: [
    { type: 'Console 로그인', resource: 'admin', note: 'MFA 미사용' },
    { type: 'AssumeRole', resource: 'arn:aws:iam::123456789012:role/Admin', note: 'terraform' },
  ],
  fault_tolerance: [
    { item: 'RDS 백업 미설정', resource: 'rds-prod-01', status: 'warn', action: '자동 백업 활성화 및 보존 기간 설정' },
    { item: 'EC2 단일 AZ 배포', resource: 'i-0abc123def456', status: 'warn', action: 'Multi-AZ 또는 ASG 구성 검토' },
  ],
  performance: [
    { id: 'i-0abc123def456', type: 'EC2', metric: 'CPU 사용률', value: '89%', threshold: '80%', status: 'crit' },
    { id: 'rds-prod-01', type: 'RDS', metric: 'DB 연결 수', value: '45', threshold: '100', status: 'ok' },
  ],
  limits: [
    { item: 'EC2 인스턴스 (ap-northeast-2)', limit: '32', used: '12', pct: '37%', status: 'ok' },
    { item: 'VPC (ap-northeast-2)', limit: '5', used: '4', pct: '80%', status: 'warn' },
  ],
  actions: [
    { priority: 'High', category: '보안', direction: 'EC2.19 — sg-0abc123def456 SSH 인바운드 규칙 즉시 제거' },
    { priority: 'Medium', category: '비용', direction: '미사용 EIP release · 미연결 EBS 볼륨 정리' },
    { priority: 'Low', category: '내결함성', direction: 'RDS 백업 설정 · EC2 Multi-AZ 구성 검토' },
  ],
  evidence: [
    { file: 'canonical.json', uri: 's3://dndn-data/account_id=123456789012/...', sha: 'e3b0c44298fc1c14' },
    { file: 'cloudtrail.json', uri: 's3://dndn-data/account_id=123456789012/...', sha: 'a87ff679a2f3e71d' },
  ],
};

const STATUS_CLASS = { ok: 'st-ok', warn: 'st-warn', crit: 'st-crit', high: 'st-high', danger: 'st-danger' };
const STATUS_LABEL = { ok: '정상', warn: '주의', crit: '위험', high: 'High', danger: '위험' };

export default function WeeklyReport({ canonical }) {
  if (!canonical) return <div className="na-box">데이터를 불러오는 중입니다...</div>;

  const { meta = {}, events = [], resources = [], collection_status = {}, advisor_checks = [] } = canonical;

  const weekStart = meta.time_range?.start?.slice(0,10).replace(/-/g,'.') || '-';
  const weekEnd   = meta.time_range?.end?.slice(0,10).replace(/-/g,'.') || '-';
  const weekNum   = meta.partition?.week || '?';

  return (
    <div className="doc">

      {/* 헤더 */}
      <div className="doc-header">
        <div className="doc-header-top">
          <img src="/logo.png" alt="DnDn" className="doc-header-logo" />
          <div className="doc-header-meta">
            수집 계정: {meta.account_id || '-'}<br />
            보고 기간: {weekStart} ~ {weekEnd}
          </div>
        </div>
        <div className="doc-header-title">주간 보고서 — {meta.partition?.year}년 {weekNum}주차</div>
      </div>

      {/* Overview */}
      <div className="section">
        <SectionTitle>Overview</SectionTitle>
        <table className="tbl-info" style={{ marginBottom: 0 }}>
          <tbody>
            <tr>
              <th>AWS 계정</th>
              <td>{meta.account_id || '-'}</td>
              <th>수집 기간</th>
              <td>{weekStart} ~ {weekEnd}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* KPI 카드 */}
      <table className="tbl-summary">
        <tbody>
          <tr>
            <td><div className="s-label">주간 변경 건수</div><div className="s-value">{MOCK.kpi.changes}</div></td>
            <td><div className="s-label">미승인 변경</div><div className="s-value">{MOCK.kpi.unauthorized}</div></td>
            <td><div className="s-label">보안 알림</div><div className="s-value red">{MOCK.kpi.security}</div></td>
            <td><div className="s-label">비용 증감 (전주 대비)</div><div className="s-value orange">{MOCK.kpi.cost_delta}</div></td>
          </tr>
        </tbody>
      </table>

      {/* 1. 변경 현황 */}
      <div className="section">
        <SectionTitle>1. 변경 현황</SectionTitle>
        <table className="tbl">
          <tbody>
            <tr><th className="th-label">주간 변경 건수</th><td>{MOCK.changes.total}</td></tr>
            <tr><th className="th-label">보안 알림</th><td><span className="st-crit">{MOCK.changes.security}</span></td></tr>
            <tr><th className="th-label">비용 현황</th><td><span className="cost-up">{MOCK.changes.cost}</span></td></tr>
            <tr><th className="th-label">RFC 결재</th><td>{MOCK.changes.rfc}</td></tr>
          </tbody>
        </table>
      </div>

      {/* 2. 변경 타임라인 */}
      <div className="section">
        <SectionTitle>2. 변경 타임라인</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '80px' }}>일시</th>
              <th style={{ width: '105px' }}>작업자</th>
              <th style={{ width: '160px' }}>리소스</th>
              <th>작업</th>
              <th style={{ width: '65px' }}>결과</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.timeline.map((row, i) => (
              <tr key={i}>
                <td className="td-time">{row.date}</td>
                <td style={{ textAlign: 'center' }}>{row.actor}</td>
                <td style={{ textAlign: 'center' }}><code>{row.resource}</code></td>
                <td style={{ textAlign: 'center' }}>{row.action}</td>
                <td style={{ textAlign: 'center' }}>
                  <span className={STATUS_CLASS[row.result]}>{STATUS_LABEL[row.result]}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 3. 변경 리소스 */}
      <div className="section">
        <SectionTitle>3. 변경 리소스</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '160px' }}>리소스</th>
              <th style={{ width: '60px' }}>Type</th>
              <th style={{ width: '110px' }}>항목</th>
              <th>변경 내용</th>
              <th style={{ width: '110px' }}>비고</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.resources.map((r, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}><code>{r.id}</code></td>
                <td style={{ textAlign: 'center' }}>{r.type}</td>
                <td style={{ textAlign: 'center' }}>{r.item}</td>
                <td style={{ textAlign: 'center' }}>{r.change}</td>
                <td style={{ textAlign: 'center' }}>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 4. 비용 영향 */}
      <div className="section">
        <SectionTitle>4. 비용 영향</SectionTitle>
        <div className="sub-heading">서비스별 비용 현황</div>
        <table className="tbl" style={{ marginBottom: '14px' }}>
          <thead>
            <tr>
              <th style={{ width: '120px' }}>서비스</th>
              <th style={{ width: '100px' }}>전주 비용</th>
              <th style={{ width: '110px' }}>이번 주 비용</th>
              <th style={{ width: '90px' }}>증감액</th>
              <th style={{ width: '80px' }}>증감률</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.cost.services.map((s, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}>{s.name}</td>
                <td style={{ textAlign: 'center' }}>{s.prev}</td>
                <td style={{ textAlign: 'center' }}>{s.curr}</td>
                <td style={{ textAlign: 'center' }} className={s.up ? 'cost-up' : 'cost-down'}>{s.delta}</td>
                <td style={{ textAlign: 'center' }} className={s.up ? 'cost-up' : 'cost-down'}>{s.pct}</td>
              </tr>
            ))}
            <tr className="cost-sum">
              <td style={{ textAlign: 'center' }}><strong>합계</strong></td>
              <td style={{ textAlign: 'center' }}><strong>{MOCK.cost.total.prev}</strong></td>
              <td style={{ textAlign: 'center' }}><strong>{MOCK.cost.total.curr}</strong></td>
              <td style={{ textAlign: 'center' }} className="cost-up"><strong>{MOCK.cost.total.delta}</strong></td>
              <td style={{ textAlign: 'center' }} className="cost-up"><strong>{MOCK.cost.total.pct}</strong></td>
            </tr>
          </tbody>
        </table>

        <div className="sub-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          비용 최적화 권장 항목
          <span style={{ fontSize: '11px', fontWeight: 400, color: '#666' }}>※ AWS Trusted Advisor 기준</span>
        </div>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '160px' }}>점검 항목</th>
              <th style={{ width: '185px' }}>대상 리소스</th>
              <th style={{ width: '150px' }}>현황</th>
              <th>권장 조치</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.cost.advisors.map((a, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center', verticalAlign: 'middle' }}>{a.item}</td>
                <td style={{ textAlign: 'center', verticalAlign: 'middle' }}><code>{a.resource}</code></td>
                <td style={{ textAlign: 'center', verticalAlign: 'middle' }}><span className="st-warn">주의</span> {a.status}</td>
                <td style={{ textAlign: 'center', verticalAlign: 'middle' }}>{a.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 5. 보안 Findings */}
      <div className="section">
        <SectionTitle>5. 보안 Findings</SectionTitle>
        <div className="sub-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          Security Hub
          <span style={{ fontSize: '11px', fontWeight: 400, color: '#666' }}>※ {MOCK.security.standard}</span>
        </div>
        <table className="tbl" style={{ marginBottom: '14px' }}>
          <thead>
            <tr>
              <th style={{ width: '95px' }}>심각도</th>
              <th style={{ width: '335px' }}>내용</th>
              <th style={{ width: '100px' }}>트리거</th>
              <th style={{ width: '55px' }}>신규</th>
              <th style={{ width: '55px' }}>해결</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.security.findings.map((f, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}><span className="st-crit">{f.severity}</span></td>
                <td style={{ textAlign: 'center' }}>{f.content}</td>
                <td style={{ textAlign: 'center' }}>{f.trigger}</td>
                <td style={{ textAlign: 'center', fontWeight: 700, color: f.newRed ? '#c00' : '#888' }}>{f.new}</td>
                <td style={{ textAlign: 'center', color: '#888' }}>{f.resolved}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="sub-heading">Access Analyzer</div>
        <table className="tbl" style={{ marginBottom: '14px' }}>
          <thead>
            <tr>
              <th style={{ width: '130px' }}>유형</th>
              <th style={{ width: '345px' }}>리소스 / 내용</th>
              <th style={{ width: '65px' }}>조치상태</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.security.analyzer.map((a, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}>{a.type}</td>
                <td style={{ textAlign: 'center' }}><code>{a.resource}</code> — {a.content}</td>
                <td style={{ textAlign: 'center' }}><span className="st-warn">주의</span></td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="sub-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          보안 통제 현황
          <span style={{ fontSize: '11px', fontWeight: 400, color: '#666' }}>※ AWS Config · GuardDuty · CloudTrail · IAM</span>
        </div>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '160px' }}>보안 항목</th>
              <th style={{ width: '80px' }}>상태</th>
              <th>비고</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.security.controls.map((c, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}>{c.item}</td>
                <td style={{ textAlign: 'center' }}><span className={STATUS_CLASS[c.status]}>{STATUS_LABEL[c.status]}</span></td>
                <td style={{ textAlign: 'center' }}>{c.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 6. IAM 활동 요약 */}
      <div className="section">
        <SectionTitle>6. IAM 활동 요약</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '120px' }}>구분</th>
              <th>내용</th>
              <th style={{ width: '180px' }}>비고</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.iam.map((row, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}>{row.type}</td>
                <td style={{ textAlign: 'center' }}><code>{row.resource}</code></td>
                <td style={{ textAlign: 'center' }}>{row.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 7. 내결함성 현황 */}
      <div className="section">
        <SectionTitle>7. 내결함성 현황</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '190px' }}>점검 항목</th>
              <th style={{ width: '145px' }}>대상 리소스</th>
              <th style={{ width: '165px' }}>현황</th>
              <th>권장 조치</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.fault_tolerance.map((row, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}>{row.item}</td>
                <td style={{ textAlign: 'center' }}><code>{row.resource}</code></td>
                <td style={{ textAlign: 'center' }}><span className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</span></td>
                <td style={{ textAlign: 'center' }}>{row.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 8. 성능 현황 */}
      <div className="section">
        <SectionTitle>8. 성능 현황</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '155px' }}>리소스</th>
              <th style={{ width: '60px' }}>Type</th>
              <th style={{ width: '130px' }}>지표</th>
              <th style={{ width: '80px', textAlign: 'center' }}>현재값</th>
              <th style={{ width: '115px', textAlign: 'center' }}>임계값</th>
              <th style={{ width: '80px', textAlign: 'center' }}>상태</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.performance.map((row, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}><code>{row.id}</code></td>
                <td style={{ textAlign: 'center' }}>{row.type}</td>
                <td style={{ textAlign: 'center' }}>{row.metric}</td>
                <td style={{ textAlign: 'center', fontWeight: row.status === 'crit' ? 700 : 400, color: row.status === 'crit' ? '#c00' : '#1a1a1a' }}>{row.value}</td>
                <td style={{ textAlign: 'center' }}>{row.threshold}</td>
                <td style={{ textAlign: 'center' }}><span className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 9. 서비스 한도 현황 */}
      <div className="section">
        <SectionTitle>9. 서비스 한도 현황</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '190px' }}>서비스 / 항목</th>
              <th style={{ width: '80px', textAlign: 'center' }}>한도</th>
              <th style={{ width: '100px', textAlign: 'center' }}>현재 사용량</th>
              <th style={{ width: '70px', textAlign: 'center' }}>사용률</th>
              <th style={{ width: '90px', textAlign: 'center' }}>상태</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.limits.map((row, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}>{row.item}</td>
                <td style={{ textAlign: 'center' }}>{row.limit}</td>
                <td style={{ textAlign: 'center' }}>{row.used}</td>
                <td style={{ textAlign: 'center' }}>{row.pct}</td>
                <td style={{ textAlign: 'center' }}><span className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 10. 액션 아이템 */}
      <div className="section">
        <SectionTitle>10. 액션 아이템</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '90px', textAlign: 'center' }}>우선순위</th>
              <th style={{ width: '130px', textAlign: 'center' }}>카테고리</th>
              <th>권장 방향</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.actions.map((row, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center', fontWeight: 700 }}>
                  <span className={row.priority === 'High' ? 'st-crit' : row.priority === 'Medium' ? 'st-high' : 'st-skip'}>
                    {row.priority}
                  </span>
                </td>
                <td style={{ textAlign: 'center' }}>{row.category}</td>
                <td style={{ textAlign: 'center' }}>{row.direction}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 11. Evidence Index */}
      <div className="section">
        <SectionTitle>11. Evidence Index</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '190px' }}>파일명</th>
              <th>S3 URI</th>
              <th style={{ width: '135px' }}>SHA256 (앞 16자)</th>
            </tr>
          </thead>
          <tbody>
            {MOCK.evidence.map((e, i) => (
              <tr key={i}>
                <td style={{ textAlign: 'center' }}><code>{e.file}</code></td>
                <td style={{ fontFamily: 'monospace', fontSize: '11.5px' }}>{e.uri}</td>
                <td style={{ textAlign: 'center', fontFamily: 'monospace', fontSize: '11.5px' }}>{e.sha}...</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 12. 수집 상태 */}
      <div className="section">
        <SectionTitle>12. 수집 상태</SectionTitle>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '160px' }}>모듈</th>
              <th style={{ width: '80px' }}>상태</th>
              <th>비고</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(collection_status).map(([key, val]) => (
              <tr key={key}>
                <td style={{ textAlign: 'center' }}><code>{key}</code></td>
                <td style={{ textAlign: 'center', fontWeight: 700, color: val.status === 'OK' ? '#197340' : val.status === 'NA' ? '#888' : '#c00' }}>
                  {val.status}
                </td>
                <td style={{ textAlign: 'center' }}>{val.na_reason || val.message || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 푸터 */}
      <div className="doc-footer">
        <span>수집 계정: {meta.account_id} | {weekStart} ~ {weekEnd} run_id: {meta.run_id}</span>
      </div>
    </div>
  );
}
