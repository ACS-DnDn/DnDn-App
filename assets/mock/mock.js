/**
 * Mock 세션 데이터
 * API 연결 시 fetch('/api/me') 응답으로 교체
 */
const session = {
  name: "정지은",
  role: "선임연구원",
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
