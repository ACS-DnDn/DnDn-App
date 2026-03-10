import type { ReportSettings } from '../types/report';

export const reportSettings: ReportSettings = {
  summary: {
    repeatEnabled: true,
    intervalHours: 168,
    lastRun: '2026-03-02 06:00',
  },

  schedules: [
    { id: 1, title: '주간보고서', preset: 'weekly', dayOfWeek: 1, time: '06:00', includeRange: true },
    { id: 2, title: '월간보고서', preset: 'monthly', dayOfMonth: 1, time: '00:00', includeRange: true },
    { id: 3, title: '일일점검', preset: 'daily', time: '09:00', includeRange: false },
  ],

  eventSettings: {
    /* Security Hub — GuardDuty */
    'sh-malicious-network': true, 'sh-unauthorized-access': true,
    'sh-anomalous-behavior': true, 'sh-recon': false, 'sh-exfiltration': true,
    /* Security Hub — Access Analyzer */
    'sh-external-access': true, 'sh-unused-access': false,
    /* Security Hub — FSBP/CIS */
    'sh-network': true, 'sh-data-protection': true, 'sh-iam': true,
    'sh-logging': true, 'sh-compute': false, 'sh-database': true,
    /* Security Hub — Inspector */
    'sh-vulnerability': false,
    /* AWS Health */
    'ah-ec2-maint': true, 'ah-rds-maint': true, 'ah-other-maint': false,
    'ah-ec2-retire': true, 'ah-ebs-issue': true, 'ah-rds-hw': true,
    'ah-service-event': true, 'ah-cert-expire': true,
    'ah-abuse': false,
  },

  opa: [
    { category: '네트워크 보안', items: [
      { key: 'net-sg-open', label: '보안그룹 전체 개방(0.0.0.0/0) 차단', on: true, severity: 'block',
        params: { type: 'list', label: '허용 CIDR', values: ['10.0.0.0/8', '172.16.0.0/12'] }, exceptions: [] },
      { key: 'net-rds-public', label: 'RDS 퍼블릭 접근 차단', on: true, severity: 'block',
        params: null, exceptions: [] },
      { key: 'net-flow-log', label: 'VPC Flow Log 활성화 필수', on: false, severity: 'warn',
        params: null, exceptions: [] },
    ]},
    { category: 'IAM 보안', items: [
      { key: 'iam-wildcard', label: '와일드카드(*) 권한 사용 금지', on: true, severity: 'block',
        params: null, exceptions: [] },
      { key: 'iam-admin-attach', label: 'AdministratorAccess 정책 직접 연결 금지', on: true, severity: 'block',
        params: null, exceptions: [] },
      { key: 'iam-boundary', label: 'Permission Boundary 적용 필수', on: false, severity: 'warn',
        params: { type: 'list', label: '허용 Boundary ARN 패턴', values: [] }, exceptions: [] },
    ]},
    { category: '스토리지 보안', items: [
      { key: 'stor-s3-public', label: 'S3 퍼블릭 접근 금지', on: true, severity: 'block',
        params: null, exceptions: [] },
      { key: 'stor-s3-encrypt', label: 'S3 버킷 암호화 필수', on: true, severity: 'warn',
        params: null, exceptions: [] },
      { key: 'stor-rds-encrypt', label: 'RDS 스토리지 암호화 필수', on: true, severity: 'block',
        params: null, exceptions: [] },
      { key: 'stor-ebs-encrypt', label: 'EBS 볼륨 암호화 필수', on: false, severity: 'warn',
        params: null, exceptions: [] },
    ]},
    { category: '컴퓨팅 제어', items: [
      { key: 'comp-ec2-public-ip', label: 'EC2 퍼블릭 IP 자동 할당 금지', on: true, severity: 'block',
        params: null, exceptions: [] },
      { key: 'comp-instance', label: '허용 인스턴스 타입 제한', on: false, severity: 'warn',
        params: { type: 'list', label: '허용 타입', values: ['t3.micro', 't3.small', 't3.medium'] }, exceptions: [] },
      { key: 'comp-tag', label: '필수 태그 정책 강제', on: true, severity: 'warn',
        params: { type: 'list', label: '필수 태그 키', values: ['Environment', 'Team', 'Service'] }, exceptions: [] },
    ]},
    { category: '로깅 / 모니터링', items: [
      { key: 'log-cloudtrail', label: 'CloudTrail 활성화 필수', on: true, severity: 'block',
        params: null, exceptions: [] },
    ]},
    { category: '비용 관리', items: [
      { key: 'cost-region', label: '허용 리전 제한', on: false, severity: 'warn',
        params: { type: 'list', label: '허용 리전', values: ['us-east-1', 'ap-northeast-2'] }, exceptions: [] },
    ]},
    { category: '가용성', items: [
      { key: 'avail-multi-az', label: 'Multi-AZ 배포 필수', on: true, severity: 'warn',
        params: { type: 'services', label: '적용 서비스', values: ['RDS'], options: ['RDS', 'ElastiCache', 'Aurora'] }, exceptions: [] },
      { key: 'avail-backup', label: '백업 보존 기간 최소값', on: true, severity: 'warn',
        params: { type: 'number', label: '최소 보존일', value: 7, unit: '일' }, exceptions: [] },
    ]},
  ],
};
