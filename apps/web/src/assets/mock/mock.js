/**
 * Mock 세션 데이터
 * API 연결 시 fetch('/api/me') 응답으로 교체
 */
const session = {
  name: "정지은",
  role: "선임연구원",
  auth: "leader",          // cognito:groups — "leader" | "user" | "auditor"
  company: {
    name: "CSLEE.",
    logoUrl:     "../assets/mock/logo.png",
    logoDarkUrl: "../assets/mock/logo_dark.png"
  }
};

/**
 * Mock 문서보관함 데이터
 * API 연결 시 fetch('/api/documents') 응답으로 교체
 */
const ALL_DOCS = [
  // 처리할 문서 (결재 필요 or 반려)
  { id: 1,  name: 'EKS 노드그룹 인스턴스 타입 변경 계획서', author: '이서연', date: '2026-02-24 14:22', type: '계획서',       status: 'progress', action: 'approve',  icon: '📝' },
  { id: 2,  name: 'RDS 스토리지 자동확장 활성화 계획서',     author: '김민준', date: '2026-02-23 09:45', type: '계획서',       status: 'progress', action: 'approve',  icon: '📝' },
  { id: 3,  name: 'GuardDuty IP 차단 조치',                 author: '박지훈', date: '2026-02-14 16:30', type: '이벤트보고서', status: 'rejected', action: 'rejected', icon: '🛡️' },
  // 전체 문서
  { id: 4,  name: '주간 보고서 (02.17~02.23)',              author: '시스템',  date: '2026-02-23 06:00', type: '주간보고서',   status: 'done',     action: null, icon: '📊' },
  { id: 5,  name: 'CloudTrail 재활성화 작업',               author: '홍길동', date: '2026-02-15 11:10', type: '이벤트보고서', status: 'done',     action: null, icon: '🔍' },
  { id: 6,  name: '비용 최적화 보고서 (Q1 2026)',           author: '시스템',  date: '2026-02-10 06:00', type: '비용최적화',   status: 'done',     action: null, icon: '💰' },
  { id: 7,  name: 'Security Hub 정책 강화 계획서',          author: '정수빈', date: '2026-02-08 13:55', type: '계획서',       status: 'failed',   action: null, icon: '📝' },
  { id: 8,  name: '주간 보고서 (02.10~02.16)',              author: '시스템',  date: '2026-02-16 06:00', type: '주간보고서',   status: 'done',     action: null, icon: '📊' },
  { id: 9,  name: 'IAM 미사용 권한 정리 계획서',            author: '홍길동', date: '2026-02-05 15:40', type: '계획서',       status: 'done',     action: null, icon: '📝' },
  { id: 10, name: 'ALB 액세스 로그 활성화 계획서',          author: '이서연', date: '2026-01-30 10:22', type: '계획서',       status: 'done',     action: null, icon: '📝' },
  { id: 11, name: '보안감사 보고서 Q1 2026',                author: '정수빈', date: '2026-01-31 18:00', type: '보안감사',     status: 'done',     action: null, icon: '🔒' },
  { id: 12, name: 'Lambda Cold Start 개선 계획서',          author: '김민준', date: '2026-01-28 09:30', type: '계획서',       status: 'rejected', action: null, icon: '📝' },
  { id: 13, name: '주간 보고서 (01.20~01.26)',              author: '시스템',  date: '2026-01-26 06:00', type: '주간보고서',   status: 'done',     action: null, icon: '📊' },
  { id: 14, name: 'ECS Fargate 전환 계획서',                author: '최현우', date: '2026-01-22 14:11', type: '계획서',       status: 'done',     action: null, icon: '📝' },
  { id: 15, name: 'CloudWatch 알람 임계값 조정',            author: '홍길동', date: '2026-01-20 16:55', type: '계획서',       status: 'done',     action: null, icon: '📝' },
  { id: 16, name: 'VPC Flow Log 이상 트래픽 감지',          author: '시스템',  date: '2026-01-18 03:14', type: '이벤트보고서', status: 'done',     action: null, icon: '⚠️' },
  { id: 17, name: '주간 보고서 (01.13~01.19)',              author: '시스템',  date: '2026-01-19 06:00', type: '주간보고서',   status: 'done',     action: null, icon: '📊' },
  { id: 18, name: 'S3 퍼블릭 접근 차단 계획서',             author: '정수빈', date: '2026-01-15 11:30', type: '계획서',       status: 'done',     action: null, icon: '📝' },
];

/**
 * Mock 문서 열람 데이터 — PLAN-2026-0224-001
 * API 연결 시 fetch('/api/documents/:id/refs') 응답으로 교체
 */
const REF_DOCS = {
  weekly: {
    icon: '📊',
    title: '주간 보고서 (02.17~02.23)',
    meta: [
      ['기간',  '2026.02.17 ~ 02.23'],
      ['생성',  '시스템 자동'],
      ['생성일', '2026.02.23 06:00']
    ],
    body: `
<h2 style="font-size:18px;font-weight:800;margin-bottom:8px;">주간 인프라 현황 보고서</h2>
<p style="font-size:12px;color:var(--text-muted);margin-bottom:20px;">2026.02.17 ~ 2026.02.23 | AWS Account: nexon-production</p>

<h3 style="font-size:13px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;">
  <span style="width:3px;height:13px;background:var(--mint);border-radius:2px;display:inline-block;"></span>핵심 이슈
</h3>
<div style="background:var(--red-soft);border:1px solid rgba(240,62,62,.2);border-radius:8px;padding:12px 14px;margin-bottom:16px;font-size:13px;color:var(--text-sub);line-height:1.7;">
  ⚠️ <strong>EKS production-ng CPU 사용률 지속 초과</strong><br>
  피크타임(18~22시) 평균 CPU 94%, 응답 지연 평균 +340ms 관측. 이번 주로 2주 연속 동일 이슈 발생. 즉각 조치 권고.
</div>

<h3 style="font-size:13px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;">
  <span style="width:3px;height:13px;background:var(--mint);border-radius:2px;display:inline-block;"></span>변경 이력 요약
</h3>
<table style="width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:16px;">
  <thead><tr style="background:var(--bg);">
    <th style="padding:8px 11px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text-muted);font-size:11.5px;">일시</th>
    <th style="padding:8px 11px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text-muted);font-size:11.5px;">리소스</th>
    <th style="padding:8px 11px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text-muted);font-size:11.5px;">변경 내용</th>
  </tr></thead>
  <tbody>
    <tr>
      <td style="padding:8px 11px;border:1px solid var(--border);color:var(--text-muted);">02.19 10:32</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">S3 bucket</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">버전관리 활성화</td>
    </tr>
    <tr>
      <td style="padding:8px 11px;border:1px solid var(--border);color:var(--text-muted);">02.21 15:44</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">Security Group</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">인바운드 규칙 3개 추가</td>
    </tr>
  </tbody>
</table>

<h3 style="font-size:13px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;">
  <span style="width:3px;height:13px;background:var(--mint);border-radius:2px;display:inline-block;"></span>액션 아이템
</h3>
<div style="font-size:13px;color:var(--text-sub);background:var(--bg);border-radius:8px;padding:12px 14px;border:1px solid var(--border);line-height:1.8;">
  1. EKS 노드그룹 인스턴스 타입 업그레이드 검토 (담당: 이서연)<br>
  2. CloudWatch CPU 알람 임계값 80%로 하향 조정<br>
  3. Security Hub 미해결 Findings 3건 처리
</div>`
  },

  eks: {
    icon: '📝',
    title: 'EKS 노드 추가 계획서',
    meta: [
      ['유형',  '계획서'],
      ['작성자', '이서연'],
      ['작성일', '2026.02.10 09:30'],
      ['상태',  '완료']
    ],
    body: `
<h2 style="font-size:18px;font-weight:800;margin-bottom:8px;">EKS 노드 추가 계획서</h2>
<p style="font-size:12px;color:var(--text-muted);margin-bottom:20px;">2026.02.10 | 작성자: 이서연</p>

<h3 style="font-size:13px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;">
  <span style="width:3px;height:13px;background:var(--mint);border-radius:2px;display:inline-block;"></span>개요
</h3>
<div style="font-size:13px;color:var(--text-sub);background:var(--bg);border-radius:8px;padding:12px 14px;border:1px solid var(--border);line-height:1.7;margin-bottom:16px;">
  production-ng 노드그룹의 노드 수를 2개에서 3개로 증설합니다. 증가하는 트래픽에 대응하기 위한 선제적 조치입니다.
</div>

<h3 style="font-size:13px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;">
  <span style="width:3px;height:13px;background:var(--mint);border-radius:2px;display:inline-block;"></span>변경 전 / 후
</h3>
<table style="width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:16px;">
  <thead><tr style="background:var(--bg);">
    <th style="padding:8px 11px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text-muted);font-size:11.5px;">항목</th>
    <th style="padding:8px 11px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text-muted);font-size:11.5px;">변경 전</th>
    <th style="padding:8px 11px;text-align:left;border:1px solid var(--border);font-weight:700;color:var(--text-muted);font-size:11.5px;">변경 후</th>
  </tr></thead>
  <tbody>
    <tr>
      <td style="padding:8px 11px;border:1px solid var(--border);">노드 수 (desired)</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">2</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">3</td>
    </tr>
    <tr>
      <td style="padding:8px 11px;border:1px solid var(--border);">인스턴스 타입</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">t3.medium</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">t3.medium (동일)</td>
    </tr>
    <tr>
      <td style="padding:8px 11px;border:1px solid var(--border);">예상 추가 비용</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">-</td>
      <td style="padding:8px 11px;border:1px solid var(--border);">+$36 / 월</td>
    </tr>
  </tbody>
</table>
<div style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:6px;font-size:11.5px;font-weight:700;background:var(--green-soft);color:var(--green);">
  <span style="width:5px;height:5px;border-radius:50%;background:var(--green);display:inline-block;"></span>결재 완료 · 적용됨
</div>`
  }
};

/**
 * Mock 계획서 작성 — 참조 문서 목록
 * API 연결 시 fetch('/api/documents?archived=true') 응답으로 교체
 */
const docData = [
  { no: 'DOC-2026-001', name: '주간 보고서 (02.17~02.23)',   author: 'system', date: '2026.02.23' },
  { no: 'DOC-2026-002', name: 'GuardDuty IP 차단 조치',      author: '박지훈', date: '2026.02.14' },
  { no: 'DOC-2026-003', name: 'CloudTrail 재활성화 작업',     author: '김민준', date: '2026.02.15' },
  { no: 'DOC-2026-004', name: 'EKS 노드 추가 계획서',         author: '이서연', date: '2026.02.10' },
  { no: 'DOC-2026-005', name: '보안감사 보고서 Q1',           author: '오지민', date: '2026.01.31' },
  { no: 'DOC-2026-006', name: 'S3 버킷 암호화 적용',          author: '최현우', date: '2026.01.25' },
  { no: 'DOC-2026-007', name: 'Lambda 함수 최적화',           author: '한동훈', date: '2026.01.20' },
  { no: 'DOC-2026-008', name: 'VPC 피어링 설정 계획서',       author: '정수빈', date: '2026.01.15' },
  { no: 'DOC-2026-009', name: 'IAM 정책 정비 보고서',         author: '오지민', date: '2026.01.10' },
  { no: 'DOC-2026-010', name: 'RDS 백업 정책 수립',           author: '이서연', date: '2026.01.07' },
  { no: 'DOC-2026-011', name: 'CloudFront 배포 설정',         author: '김민준', date: '2025.12.28' },
  { no: 'DOC-2025-012', name: '보안 취약점 점검 결과',        author: '박지훈', date: '2025.12.20' },
];

/**
 * Mock 계획서 작성 — 조직도 (결재자 추가 팝업)
 * API 연결 시 fetch('/api/org/members') 응답으로 교체
 */
const orgData = [
  { dept: '인프라팀',   members: [{ name: '김민준', rank: '시니어 엔지니어' }, { name: '한동훈', rank: '부팀장' }] },
  { dept: 'DevOps팀',   members: [{ name: '이서연', rank: '엔지니어' }] },
  { dept: '클라우드팀', members: [{ name: '최현우', rank: '매니저' }] },
  { dept: 'SRE팀',      members: [{ name: '정수빈', rank: '엔지니어' }] },
  { dept: '보안팀',     members: [{ name: '오지민', rank: '팀장' }] },
];

/**
 * Mock 문서열람 — 타입별 본문 콘텐츠
 * API 연결 시 fetch('/api/documents/:id/content') 응답으로 교체
 */
const _svgDoc = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 2H4a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V6l-4-4z"/><path d="M9 2v4h4"/></svg>`;
const MOCK_DOC_CONTENT = {
  '계획서': {
    hasTerraform: true,
    render: (doc) => `
      <h1 class="doc-title">${doc.name}</h1>
      <div class="doc-meta-row">
        <div class="doc-meta-item">📅 <strong>작업일</strong> 2026.03.05</div>
        <div class="doc-meta-item">👤 <strong>작성자</strong> ${doc.author}</div>
        <div class="doc-meta-item">🏷 <strong>유형</strong> 계획서</div>
        <div class="doc-meta-item">🕐 <strong>작성일시</strong> ${doc.date.slice(0,10).replace(/-/g,'.')}</div>
      </div>
      <div class="ref-docs-bar">
        <span class="ref-docs-label">📎 참조 문서</span>
        <a class="ref-doc-link" onclick="openRefDoc('weekly')">${_svgDoc} 주간 보고서 (02.17~02.23)</a>
        <a class="ref-doc-link" onclick="openRefDoc('eks')">${_svgDoc} EKS 노드 추가 계획서</a>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">개요</div>
        <div class="doc-text">EKS 노드그룹(production-ng)의 인스턴스 타입을 <strong>t3.medium에서 t3.large</strong>로 변경합니다. 피크 시간대(18~22시) CPU 사용률 90% 이상 초과로 인한 서비스 응답 지연 이슈에 대응하기 위함입니다. 해당 이슈는 주간 보고서에서 연속 2주간 지적된 사항으로, 즉각적인 조치가 필요합니다.</div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">변경 전 / 후 비교</div>
        <table class="doc-table">
          <thead><tr><th>항목</th><th>변경 전</th><th>변경 후</th></tr></thead>
          <tbody>
            <tr><td>인스턴스 타입</td><td>t3.medium (2 vCPU, 4GB)</td><td>t3.large (2 vCPU, 8GB)</td></tr>
            <tr><td>노드 수</td><td>3</td><td>3 (동일)</td></tr>
            <tr><td>예상 월 비용</td><td>$108 / 월</td><td>$216 / 월 (+$108)</td></tr>
          </tbody>
        </table>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">위험도 분석</div>
        <table class="doc-table">
          <thead><tr><th>위험 항목</th><th>수준</th><th>대응 방안</th></tr></thead>
          <tbody>
            <tr><td>노드 교체 중 파드 재스케줄</td><td><span class="risk-badge risk-low">낮음</span></td><td>Rolling update, PDB 설정으로 서비스 무중단</td></tr>
            <tr><td>비용 증가</td><td><span class="risk-badge risk-med">중간</span></td><td>월 $108 추가 예산 승인 필요</td></tr>
            <tr><td>인스턴스 가용성</td><td><span class="risk-badge risk-low">낮음</span></td><td>ap-northeast-2 리전 t3.large 충분히 확보</td></tr>
          </tbody>
        </table>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">롤백 계획</div>
        <div class="doc-text">변경 후 이상 징후 감지 시 t3.medium으로 즉시 롤백합니다. Terraform state를 통해 이전 상태 복구 가능하며, 예상 소요 시간은 약 5분입니다. 롤백 판단 기준: CPU 사용률 80% 이상 30분 지속 또는 에러율 1% 초과 시.</div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">작업 절차</div>
        <div class="doc-text">1. Terraform 코드 변경 (instance_types = ["t3.large"])<br>2. GitHub PR 생성 → terraform plan 검증<br>3. 결재 완료 후 PR Merge → terraform apply 자동 실행<br>4. 노드 Rolling update 진행 (약 10분 소요)<br>5. CloudWatch 메트릭 모니터링 (30분간 CPU / 응답시간 추적)</div>
      </div>`
  },

  '이벤트보고서': {
    hasTerraform: false,
    render: (doc) => `
      <h1 class="doc-title">${doc.name}</h1>
      <div class="doc-meta-row">
        <div class="doc-meta-item">📅 <strong>감지일시</strong> ${doc.date.slice(0,10).replace(/-/g,'.')}</div>
        <div class="doc-meta-item">👤 <strong>담당자</strong> ${doc.author}</div>
        <div class="doc-meta-item">🏷 <strong>유형</strong> 이벤트 보고서</div>
        <div class="doc-meta-item">⚠️ <strong>심각도</strong> 높음</div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">이벤트 개요</div>
        <table class="doc-table">
          <tbody>
            <tr><td style="width:140px;font-weight:600">감지 시스템</td><td>Amazon GuardDuty</td></tr>
            <tr><td style="font-weight:600">Finding 유형</td><td>UnauthorizedAccess:IAMUser/MaliciousIPCaller.Custom</td></tr>
            <tr><td style="font-weight:600">심각도</td><td>높음 (Score: 7.6)</td></tr>
            <tr><td style="font-weight:600">대상 리소스</td><td>IAM 사용자 svc-api-dev</td></tr>
            <tr><td style="font-weight:600">소스 IP</td><td>185.220.101.47 (악성 IP 목록 등재)</td></tr>
            <tr><td style="font-weight:600">감지 시각</td><td>${doc.date}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">이벤트 타임라인</div>
        <table class="doc-table">
          <thead><tr><th>일시</th><th>이벤트</th><th>비고</th></tr></thead>
          <tbody>
            <tr><td>16:12</td><td>GuardDuty Finding 생성</td><td>자동 감지</td></tr>
            <tr><td>16:15</td><td>SNS 알림 발송</td><td>보안팀 수신</td></tr>
            <tr><td>16:18</td><td>IAM 사용자 접근 차단 조치</td><td>수동 조치</td></tr>
            <tr><td>16:30</td><td>이상 트래픽 중단 확인</td><td>CloudTrail 검증</td></tr>
            <tr><td>16:45</td><td>원인 분석 완료</td><td>API 키 노출 추정</td></tr>
          </tbody>
        </table>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">영향 범위</div>
        <div class="doc-text">IAM 사용자 svc-api-dev 권한으로 접근 가능한 S3 버킷 3개, DynamoDB 테이블 2개가 노출 위험에 처했습니다. 실제 데이터 유출 여부는 CloudTrail 분석 결과 확인 불가(읽기 요청 로그 미보존). 서비스 중단은 없었으나 보안 정책 강화 필요.</div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">조치 내용</div>
        <div class="doc-text">1. IAM 사용자 svc-api-dev 즉시 비활성화<br>2. 해당 Access Key 폐기 및 재발급<br>3. 소스 IP 185.220.101.47 Security Group 차단 규칙 추가<br>4. IAM 자격증명 교체 후 정상 서비스 동작 확인</div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">재발 방지 대책</div>
        <div class="doc-text">• IAM Access Key 주기적 교체 정책 수립 (90일 만료)<br>• GuardDuty Findings → Lambda 자동 차단 파이프라인 구축<br>• 민감 API 키 Secrets Manager로 마이그레이션<br>• CloudTrail 데이터 이벤트 로깅 활성화 (S3, DynamoDB)</div>
      </div>`
  },

  '주간보고서': {
    hasTerraform: false,
    render: (doc) => `
      <h1 class="doc-title">${doc.name}</h1>
      <div class="doc-meta-row">
        <div class="doc-meta-item">📅 <strong>기간</strong> 2026.02.17 ~ 02.23</div>
        <div class="doc-meta-item">👤 <strong>생성</strong> 시스템 자동</div>
        <div class="doc-meta-item">🏷 <strong>유형</strong> 주간 보고서</div>
        <div class="doc-meta-item">🕐 <strong>생성일시</strong> 2026.02.23 06:00</div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">핵심 이슈</div>
        <div class="doc-text" style="background:var(--red-soft);border:1px solid rgba(240,62,62,.2);border-radius:8px;padding:12px 14px;">
          ⚠️ <strong>EKS production-ng CPU 사용률 지속 초과</strong><br>
          피크타임(18~22시) 평균 CPU 94%, 응답 지연 평균 +340ms 관측. 이번 주로 2주 연속 동일 이슈 발생. 즉각 조치 권고.
        </div>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">인프라 현황</div>
        <table class="doc-table">
          <thead><tr><th>항목</th><th>상태</th><th>비고</th></tr></thead>
          <tbody>
            <tr><td>EC2 / EKS 노드</td><td><span class="risk-badge risk-med">주의</span></td><td>production-ng CPU 94%</td></tr>
            <tr><td>RDS</td><td><span class="risk-badge risk-low">정상</span></td><td>스토리지 72% 사용</td></tr>
            <tr><td>보안 Findings</td><td><span class="risk-badge risk-med">주의</span></td><td>미해결 3건</td></tr>
            <tr><td>비용</td><td><span class="risk-badge risk-low">정상</span></td><td>예산 대비 94%</td></tr>
          </tbody>
        </table>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">변경 이력</div>
        <table class="doc-table">
          <thead><tr><th>일시</th><th>리소스</th><th>변경 내용</th><th>담당</th></tr></thead>
          <tbody>
            <tr><td>02.19 10:32</td><td>S3 bucket</td><td>버전관리 활성화</td><td>이서연</td></tr>
            <tr><td>02.21 15:44</td><td>Security Group</td><td>인바운드 규칙 3개 추가</td><td>김민준</td></tr>
            <tr><td>02.22 09:00</td><td>CloudWatch</td><td>알람 임계값 조정 (CPU 90→80%)</td><td>홍길동</td></tr>
          </tbody>
        </table>
      </div>
      <div class="doc-section">
        <div class="doc-section-title">액션 아이템</div>
        <div class="doc-text">1. EKS 노드그룹 인스턴스 타입 업그레이드 검토 (담당: 이서연, 기한: 02.28)<br>2. CloudWatch CPU 알람 임계값 80%로 하향 조정 (담당: 홍길동, 기한: 02.25)<br>3. Security Hub 미해결 Findings 3건 처리 (담당: 박지훈, 기한: 02.28)</div>
      </div>`
  }
};

/**
 * Mock 대시보드 데이터
 * API 연결 시 fetch('/api/dashboard') 응답으로 교체
 */
const dashboardData = {

  // 문서 현황 수치
  docStats: {
    pending: 4,
    ongoing: 3,
    newDoc:  8
  },

  // 공지사항 (최대 5개 표시)
  notices: [
    { id: 1024, type: 'notice', title: '2월 정기 보안 점검 일정 안내',      author: '관리자', date: '2026.02.20' },
    { id: 1023, type: 'update', title: 'AWS 비용 최적화 가이드 v2 배포',     author: '김민준', date: '2026.02.18' },
    { id: 1022, type: 'notice', title: '온콜 순번 변경 안내 (3월)',           author: '관리자', date: '2026.02.15' },
    { id: 1021, type: 'update', title: 'Terraform 모듈 v3.1 릴리즈 노트',    author: '이서연', date: '2026.02.10' },
    { id: 1020, type: 'update', title: '내부 보안 정책 개정 (IAM 가이드)',    author: '박지훈', date: '2026.02.05' },
    { id: 1019, type: 'notice', title: '전사 비밀번호 초기화 일정 공지',      author: '관리자', date: '2026.01.30' }
  ],

  // 처리할 문서 (최대 5개 표시)
  pendingDocs: [
    { docNum: '2026-DnDn-0089', title: 'S3 퍼블릭 ACL 즉시 차단',    status: 'waiting',  type: '이벤트', author: '김민준', date: '2026.02.24' },
    { docNum: '2026-DnDn-0088', title: 'RDS 백업 주기 복구',          status: 'waiting',  type: '이벤트', author: '김민준', date: '2026.02.23' },
    { docNum: '2026-DnDn-0087', title: 'EKS 노드그룹 스케일 조정',    status: 'waiting',  type: '계획서', author: '이서연', date: '2026.02.22' },
    { docNum: '2026-DnDn-0086', title: 'IAM svc-legacy 비활성화',     status: 'rejected', type: '계획서', author: '이서연', date: '2026.02.20' }
  ],

  // 완료된 문서 (최대 5개 표시)
  completedDocs: [
    { docNum: '2026-DnDn-0085', title: '보안그룹 SSH 인바운드 제거',  type: '이벤트', author: '김민준', date: '2026.02.18' },
    { docNum: '2026-DnDn-0084', title: '주간 보고서 (02.10~02.16)',   type: '주간',   author: '시스템', date: '2026.02.17' },
    { docNum: '2026-DnDn-0083', title: 'CloudTrail 재활성화 작업',    type: '이벤트', author: '김민준', date: '2026.02.15' },
    { docNum: '2026-DnDn-0082', title: 'GuardDuty IP 차단 조치',      type: '이벤트', author: '박지훈', date: '2026.02.14' },
    { docNum: '2026-DnDn-0081', title: 'EC2 인스턴스 스케일업',        type: '계획서', author: '이서연', date: '2026.02.13' }
  ],

  // 오늘의 업무
  tasks: [
    'EKS 노드그룹 스케일 조정 검토',
    '주간 보안 점검 미팅',
    'RDS 백업 주기 설정 확인',
    '계획서 최종 검토'
  ]

};

/**
 * Mock 워크스페이스 데이터
 * - 워크스페이스.html, 워크스페이스-생성.html 에서 공유
 * - API 연결 시 fetch('/api/workspaces') 응답으로 교체
 */

/* ── 아이콘 세트 ── */
const WS_ICONS = {
  server:   `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="14" height="6" rx="1.5"/><rect x="2" y="10" width="14" height="6" rx="1.5"/><circle cx="5" cy="5" r="0.8" fill="currentColor"/><circle cx="5" cy="13" r="0.8" fill="currentColor"/></svg>`,
  cloud:    `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 13.5a3.5 3.5 0 01-.35-6.97 5 5 0 019.7 0A3.5 3.5 0 0113.5 13.5h-9z"/></svg>`,
  shield:   `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 2l6 3v4c0 3.5-2.5 6.5-6 7.5-3.5-1-6-4-6-7.5V5l6-3z"/></svg>`,
  code:     `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="5.5 5 2 9 5.5 13"/><polyline points="12.5 5 16 9 12.5 13"/><line x1="10" y1="3" x2="8" y2="15"/></svg>`,
  database: `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="9" cy="4.5" rx="6" ry="2.5"/><path d="M3 4.5v9c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5v-9"/><path d="M3 9c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5"/></svg>`,
  flask:    `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 2h4M8 2v5l-4.5 7a1 1 0 00.87 1.5h9.26a1 1 0 00.87-1.5L10 7V2"/></svg>`,
  rocket:   `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14l-2 2-1-3-3-1 2-2"/><path d="M12.5 2.5c-3 0-6.5 3-7.5 6l5 5c3-1 6-4.5 6-7.5a2.5 2.5 0 00-3.5-3.5z"/><circle cx="12" cy="6" r="1"/></svg>`,
  lock:     `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="10" height="8" rx="1.5"/><path d="M6 8V5.5a3 3 0 016 0V8"/></svg>`,
};
const ICON_KEYS = Object.keys(WS_ICONS);

/* ── 공통 SVG ── */
const SVG = {
  edit:   `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2.5l2 2L5 11H3V9l6.5-6.5z"/></svg>`,
  del:    `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="2,4 12,4"/><path d="M5 4V3a1 1 0 011-1h2a1 1 0 011 1v1"/><path d="M3 4l1 8a1 1 0 001 1h4a1 1 0 001-1l1-8"/></svg>`,
  github: `<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>`,
  aws:    `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 13.5a3.5 3.5 0 01-.35-6.97 5 5 0 019.7 0A3.5 3.5 0 0113.5 13.5h-9z"/></svg>`,
  check:  `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 7 6 10 11 4"/></svg>`,
};

/* ── 워크스페이스 목록 ── */
const wsAccounts = [
  { alias: 'Production',  acctId: '451017115109', githubOrg: 'ACS-DnDn', repo: 'dndn-infra', path: 'envs/prd', branch: 'main',    icon: 'rocket', memo: '운영 환경 — 변경 시 RFC 필수' },
  { alias: 'Staging',     acctId: '123456789012', githubOrg: 'ACS-DnDn', repo: 'dndn-infra', path: 'envs/stg', branch: 'main',    icon: 'flask',  memo: '스테이징 테스트용' },
  { alias: 'Development', acctId: '987654321098', githubOrg: 'ACS-DnDn', repo: 'dndn-infra', path: 'envs/dev', branch: 'develop', icon: 'code',   memo: '' },
];

/* ── GitHub Mock 데이터 ── */
const MOCK_GH = {
  orgs: ['ACS-DnDn', 'my-personal'],
  repos: {
    'ACS-DnDn':    ['dndn-infra', 'dndn-app', 'dndn-docs'],
    'my-personal': ['side-project', 'dotfiles'],
  },
  branches: {
    'dndn-infra':    ['main', 'develop', 'feature/vpc'],
    'dndn-app':      ['main', 'develop'],
    'dndn-docs':     ['main'],
    'side-project':  ['main', 'dev'],
    'dotfiles':      ['main'],
  },
};
