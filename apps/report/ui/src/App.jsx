import { useState } from 'react';
import EventReport from './components/report/EventReport';
import WeeklyReport from './components/report/WeeklyReport';
import WorkPlan from './components/report/WorkPlan';
import WorkPlanForm from './components/report/WorkPlanForm';
import eventSample from './data/event.securityhub.sample.json';
import canonicalSample from './data/canonical.sample.json';
import './index.css';

const TABS = [
  { key: 'event', label: '이벤트 보고서' },
  { key: 'weekly', label: '주간 보고서' },
  { key: 'workplan', label: '작업계획서' },
];

const SAMPLE_WORKPLAN = {
  title: 'prod-api-alb WAF WebACL 생성 및 연결',
  doc_id: 'DOC-2026-03-002',
  created_at: '2026-03-01',
  reason: 'SecurityHub WAF.1 Finding (HIGH) 감지 — prod-api-alb WAF 미연결',
  resource: 'prod-api-alb',
  account_id: '123456789012 (dndn-prod)',
  scheduled_at: '결재 완료 후 즉시 — 무중단 작업',
  assignee: 'devops@dndn',
  before_after: [
    { item: 'WAF 연결', before: '미연결', after: 'WAF WebACL (prod-api-waf) 연결' },
    { item: '웹 공격 차단', before: '미적용', after: 'AWSManagedRulesCommonRuleSet 적용' },
    { item: '월 비용', before: 'WAF 비용 없음', after: '+약 $25/월' },
    { item: '다운타임', before: '—', after: '없음' },
  ],
  risks: [
    { item: '서비스 중단', level: 'LOW', description: 'WAF 연결은 무중단 — ALB 재시작 불필요' },
    { item: '오탐 차단', level: 'MEDIUM', description: '초기 Count 모드 적용 후 Block 전환 권장' },
    { item: '비용 증가', level: 'LOW', description: '월 ~$25 추가 — 예산 범위 내' },
  ],
  rollback: {
    trigger: 'WAF 적용 후 정상 트래픽 차단율 5% 초과 시',
    method: 'Count 모드 전환 → 오탐 분석 → WebACL 연결 해제',
    estimated_time: 'Count 모드 전환: 약 2~3분',
    assignee: 'devops@dndn',
  },
  steps: [
    { name: '사전 확인', description: 'CloudWatch ALB 트래픽 및 헬스체크 정상 확인', executor: '수동', assignee: 'devops' },
    { name: 'WAF 생성', description: 'aws_wafv2_web_acl 생성 — 초기 Count 모드', executor: 'Terraform', assignee: '자동' },
    { name: 'ALB 연결', description: 'aws_wafv2_web_acl_association으로 prod-api-alb 연결', executor: 'Terraform', assignee: '자동' },
    { name: 'Count 모니터링', description: '30분간 WAF 샘플링 로그 확인', executor: '수동', assignee: 'devops' },
    { name: 'Block 전환', description: '오탐 없음 확인 후 Block 모드 전환', executor: 'Terraform', assignee: '자동' },
    { name: '사후 모니터링', description: '24시간 CloudWatch WAF 지표 확인', executor: '수동', assignee: 'devops' },
  ],
  pr_url: 'https://github.com/dndn-org/dndn-infra/pull/52',
};

export default function App() {
  const [tab, setTab] = useState('event');
  const [workplanMode, setWorkplanMode] = useState('view');
  const [workplanData, setWorkplanData] = useState(SAMPLE_WORKPLAN);

  function handleSave(formData) {
    setWorkplanData({ ...formData, doc_id: workplanData.doc_id, created_at: workplanData.created_at });
    setWorkplanMode('view');
  }

  return (
    <>
      <div className="dev-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`dev-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'event' && <EventReport canonical={eventSample} />}
      {tab === 'weekly' && <WeeklyReport canonical={canonicalSample} />}
      {tab === 'workplan' && (
        workplanMode === 'view'
          ? <WorkPlan data={workplanData} onEdit={() => setWorkplanMode('edit')} />
          : <WorkPlanForm initial={workplanData} onSubmit={handleSave} onCancel={() => setWorkplanMode('view')} />
      )}
    </>
  );
}
