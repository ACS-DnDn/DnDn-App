import type { DashboardData } from '../types/dashboard';

export const dashboardData: DashboardData = {
  docStats: {
    pending: 4,
    ongoing: 3,
    newDoc: 8,
  },

  notices: [
    { id: 1024, type: 'notice', title: '2월 정기 보안 점검 일정 안내',      author: '관리자', date: '2026.02.20' },
    { id: 1023, type: 'update', title: 'AWS 비용 최적화 가이드 v2 배포',     author: '김민준', date: '2026.02.18' },
    { id: 1022, type: 'notice', title: '온콜 순번 변경 안내 (3월)',           author: '관리자', date: '2026.02.15' },
    { id: 1021, type: 'update', title: 'Terraform 모듈 v3.1 릴리즈 노트',    author: '이서연', date: '2026.02.10' },
    { id: 1020, type: 'update', title: '내부 보안 정책 개정 (IAM 가이드)',    author: '박지훈', date: '2026.02.05' },
    { id: 1019, type: 'notice', title: '전사 비밀번호 초기화 일정 공지',      author: '관리자', date: '2026.01.30' },
  ],

  pendingDocs: [
    { docNum: '2026-DnDn-0089', title: 'S3 퍼블릭 ACL 즉시 차단',    status: 'waiting',  type: '이벤트', author: '김민준', date: '2026.02.24', workspace: 'Production' },
    { docNum: '2026-DnDn-0088', title: 'RDS 백업 주기 복구',          status: 'waiting',  type: '이벤트', author: '김민준', date: '2026.02.23', workspace: 'Production' },
    { docNum: '2026-DnDn-0087', title: 'EKS 노드그룹 스케일 조정',    status: 'waiting',  type: '계획서', author: '이서연', date: '2026.02.22', workspace: 'Staging' },
    { docNum: '2026-DnDn-0086', title: 'IAM svc-legacy 비활성화',     status: 'rejected', type: '계획서', author: '이서연', date: '2026.02.20', workspace: 'Development' },
  ],

  completedDocs: [
    { docNum: '2026-DnDn-0085', title: '보안그룹 SSH 인바운드 제거',  type: '이벤트', author: '김민준', date: '2026.02.18', workspace: 'Production' },
    { docNum: '2026-DnDn-0084', title: '주간 보고서 (02.10~02.16)',   type: '주간',   author: '시스템', date: '2026.02.17', workspace: 'Staging' },
    { docNum: '2026-DnDn-0083', title: 'CloudTrail 재활성화 작업',    type: '이벤트', author: '김민준', date: '2026.02.15', workspace: 'Production' },
    { docNum: '2026-DnDn-0082', title: 'GuardDuty IP 차단 조치',      type: '이벤트', author: '박지훈', date: '2026.02.14', workspace: 'Production' },
    { docNum: '2026-DnDn-0081', title: 'EC2 인스턴스 스케일업',        type: '계획서', author: '이서연', date: '2026.02.13', workspace: 'Development' },
  ],

  tasks: [
    'EKS 노드그룹 스케일 조정 검토',
    '주간 보안 점검 미팅',
    'RDS 백업 주기 설정 확인',
    '계획서 최종 검토',
  ],
};
