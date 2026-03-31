import { useState, useCallback, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useSearchParams } from 'react-router-dom';
import { useSession } from '@/hooks/useSession';
import { getReportSettings, createSchedule, updateSchedule, deleteSchedule, updateEventSettings, createSummaryReport } from '@/services/report.service';
import { startGenerateTracking } from '@/components/GenerateProgress';
import { getWorkspaces } from '@/services/workspace.service';
import type { Schedule, SchedulePreset, EventSettingsKey } from '@/mocks';
import './ReportSettingsPage.css';

/* ── 상수 ── */
const PRESETS: Record<string, string> = { daily: '일일', weekly: '주간', monthly: '월간', quarterly: '분기' };
const PRESET_NAMES: Record<string, string> = { daily: '일일 인프라 활동 보고서', weekly: '주간 인프라 활동 보고서', monthly: '월간 인프라 활동 보고서', quarterly: '분기 인프라 활동 보고서' };
const PRESET_DAYS: Record<string, number> = { daily: 1, weekly: 7, monthly: 30, quarterly: 90 };
const DAY_NAMES = ['일', '월', '화', '수', '목', '금', '토'];
/* ── 시간 목록 (30분 단위, 구글캘린더 스타일) ── */
const TIME_OPTIONS: string[] = [];
for (let h = 0; h < 24; h++) { for (const m of ['00', '30']) TIME_OPTIONS.push(`${String(h).padStart(2, '0')}:${m}`); }

function TimePicker({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  useEffect(() => {
    if (open && listRef.current) {
      const idx = TIME_OPTIONS.indexOf(value);
      if (idx >= 0) listRef.current.scrollTop = idx * 34 - 68;
    }
  }, [open, value]);

  return (
    <div className="cal-time-group" ref={ref}>
      <span className="cal-time-label">{label}</span>
      <button className="time-trigger" onClick={() => setOpen(v => !v)}>
        <svg className="time-trigger-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/></svg>
        {value}
      </button>
      {open && (
        <div className="time-dropdown" ref={listRef}>
          {TIME_OPTIONS.map(t => (
            <div key={t} className={`time-option${t === value ? ' selected' : ''}`}
              onClick={() => { onChange(t); setOpen(false); }}>{t}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 이벤트 정의 ── */
interface EventItem { key: EventSettingsKey; label: string; svc: string; desc: string; }
interface EventSubGroup { sub: string; items: EventItem[]; }
interface EventGroup { category: string; ico: string; icoSvg: string; desc: string; groups: EventSubGroup[]; }

const EVENT_DEFS: EventGroup[] = [
  { category: 'Security Hub', ico: 'ico-sh', desc: '보안 위협 및 구성 위반 탐지',
    icoSvg: '<path d="M8 1.5l5.5 2.5v4c0 3-2.2 5.5-5.5 6.5-3.3-1-5.5-3.5-5.5-6.5V4z"/><path d="M6 8l1.5 1.5L10 6"/>',
    groups: [
      { sub: 'GuardDuty — 위협 탐지', items: [
        { key: 'sh-malicious-network', label: '악성 네트워크 활동', svc: 'GuardDuty', desc: 'C&C 서버, 악성 IP, 암호화폐 채굴 풀과 EC2 인스턴스 간 통신을 탐지합니다.' },
        { key: 'sh-unauthorized-access', label: '비인가 접근 시도', svc: 'GuardDuty', desc: 'SSH/RDP 무차별 대입 공격, 비정상 콘솔 로그인, 유출된 자격증명 사용을 탐지합니다.' },
        { key: 'sh-anomalous-behavior', label: '비정상 API/권한 활동', svc: 'GuardDuty', desc: '권한 상승 시도, 비정상 정책 변경, 지속성 확보 활동을 머신러닝 기반으로 탐지합니다.' },
        { key: 'sh-recon', label: '정찰 및 포트 스캔', svc: 'GuardDuty', desc: '외부에서의 포트 프로빙, EC2 인스턴스 대상 네트워크 스캐닝을 탐지합니다.' },
        { key: 'sh-exfiltration', label: '데이터 유출 시도', svc: 'GuardDuty', desc: 'DNS 터널링, S3 비정상 대량 다운로드 등 데이터 유출 패턴을 탐지합니다.' },
      ]},
      { sub: 'Access Analyzer — 접근 분석', items: [
        { key: 'sh-external-access', label: '외부 공개 리소스', svc: 'Access Analyzer', desc: 'S3 버킷, IAM 역할, KMS 키, Lambda 함수, SQS 큐 등이 외부 계정이나 인터넷에 공개된 상태를 탐지합니다.' },
        { key: 'sh-unused-access', label: '미사용 접근 권한', svc: 'Access Analyzer', desc: '90일 이상 사용되지 않은 IAM 역할, 정책, 액세스 키를 식별합니다. Unused Access 타입 Analyzer 별도 생성이 필요합니다.' },
      ]},
      { sub: 'FSBP / CIS — 보안 구성', items: [
        { key: 'sh-network', label: '네트워크 보안 위반', svc: 'FSBP/CIS',
          desc: '보안그룹, 로드밸런서, VPC, API Gateway, CloudFront, WAF 등 네트워크 보안 구성 위반을 탐지합니다.<br/><br/><strong>해당 Controls</strong><br/><code>EC2.2, EC2.13, EC2.18, EC2.19, EC2.21</code> · <code>ELB.1~16</code> · <code>CloudFront.1~12</code> · <code>APIGateway.1~5</code> · <code>WAF.*</code>' },
        { key: 'sh-data-protection', label: '데이터 보호 위반', svc: 'FSBP',
          desc: 'S3 접근 제어, 스토리지 암호화(EBS, RDS, S3, DynamoDB), KMS 키 관리 관련 위반을 탐지합니다.<br/><br/><strong>해당 Controls</strong><br/><code>S3.1~19</code> · <code>EBS.1~4</code> · <code>KMS.1~4</code> · <code>SSM.4</code> · <code>ES/OpenSearch.*</code>' },
        { key: 'sh-iam', label: '계정/인증 관리 위반', svc: 'FSBP/CIS',
          desc: 'IAM 정책, 루트 계정 보호, MFA 적용, 패스워드 정책, 액세스 키 교체 관련 위반을 탐지합니다.<br/><br/><strong>해당 Controls</strong><br/><code>IAM.1~21</code> · <code>CIS 1.4~1.16</code> · <code>STS.1~2</code>' },
        { key: 'sh-logging', label: '로깅/모니터링 위반', svc: 'FSBP/CIS',
          desc: 'CloudTrail, CloudWatch 알람, VPC Flow Log, AWS Config 활성화 관련 위반을 탐지합니다.<br/><br/><strong>해당 Controls</strong><br/><code>CloudTrail.1~7</code> · <code>CloudWatch.1~14</code> · <code>EC2.6</code> · <code>Config.1</code>' },
        { key: 'sh-compute', label: '컴퓨팅 보안 위반', svc: 'FSBP',
          desc: 'EC2 인스턴스 설정, Lambda 함수 보안, ECS/EKS 컨테이너 보안 구성 위반을 탐지합니다.<br/><br/><strong>해당 Controls</strong><br/><code>EC2.1/3/8/9/15~25</code> · <code>Lambda.1~5</code> · <code>ECS.1~12</code> · <code>EKS.1~8</code> · <code>ECR.1~3</code>' },
        { key: 'sh-database', label: '데이터베이스 보안 위반', svc: 'FSBP',
          desc: 'RDS, DynamoDB, ElastiCache, Redshift, DocumentDB 등 데이터베이스 보안 구성 위반을 탐지합니다.<br/><br/><strong>해당 Controls</strong><br/><code>RDS.1~25</code> · <code>DynamoDB.1~6</code> · <code>ElastiCache.1~7</code> · <code>Redshift.1~10</code>' },
      ]},
      { sub: 'Inspector — 취약점 스캔', items: [
        { key: 'sh-vulnerability', label: '소프트웨어 취약점', svc: 'Inspector', desc: 'EC2, ECR 이미지, Lambda 함수의 알려진 취약점(CVE)을 스캐닝합니다. Inspector 서비스 활성화가 필요합니다.' },
      ]},
    ]},
  { category: 'AWS Health', ico: 'ico-ah', desc: '인프라 유지보수 및 운영 이슈',
    icoSvg: '<path d="M1 8h3l1.5-3 2 6 2-4 1.5 1H15"/>',
    groups: [
      { sub: '예정 유지보수', items: [
        { key: 'ah-ec2-maint', label: 'EC2 인스턴스 예정 유지보수', svc: 'EC2', desc: 'AWS 호스트 시스템 유지보수로 인해 인스턴스 재부팅 또는 중지가 예정된 상태입니다.' },
        { key: 'ah-rds-maint', label: 'RDS 예정 유지보수', svc: 'RDS', desc: 'RDS 인스턴스에 하드웨어·OS·엔진 패치 등 유지보수가 예정된 상태입니다.' },
        { key: 'ah-other-maint', label: '기타 서비스 유지보수 알림', svc: 'EBS/ELB', desc: 'EBS, ELB, ElastiCache 등 기타 서비스에 대한 예정된 유지보수 알림입니다.' },
      ]},
      { sub: '운영 이슈', items: [
        { key: 'ah-ec2-retire', label: 'EC2 인스턴스 Retirement', svc: 'EC2', desc: '기반 하드웨어 장애로 인스턴스가 영구 중지 예정입니다. 마이그레이션이 필요합니다.' },
        { key: 'ah-ebs-issue', label: 'EBS 볼륨 이슈', svc: 'EBS', desc: 'EBS 볼륨의 I/O 성능 저하 또는 하드웨어 오류가 감지된 상태입니다.' },
        { key: 'ah-rds-hw', label: 'RDS 하드웨어 이슈', svc: 'RDS', desc: 'RDS 인스턴스의 기반 하드웨어에 문제가 감지되어 장애 조치가 필요한 상태입니다.' },
        { key: 'ah-service-event', label: '리전 서비스 장애', svc: 'Regional', desc: '특정 리전에서 AWS 서비스 장애 또는 성능 저하가 발생한 상태입니다.' },
      ]},
      { sub: '계정 알림', items: [
        { key: 'ah-cert-expire', label: 'ACM 인증서 만료 예정', svc: 'ACM', desc: 'AWS Certificate Manager 인증서가 만료 예정이며 갱신이 필요한 상태입니다.' },
        { key: 'ah-abuse', label: '계정 Abuse 알림', svc: 'Trust & Safety', desc: 'AWS Trust & Safety에서 계정 리소스의 악용(스팸, DDoS 등)을 감지한 상태입니다.' },
      ]},
    ]},
];

/* ── 헬퍼 ── */
function pad(n: number) { return String(n).padStart(2, '0'); }
function fmtDate(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; }

interface TimingValues { time: string; dayOfWeek?: number; dayOfMonth?: number; }

function calcNextRun(preset: string, tv: TimingValues): Date | null {
  const now = new Date();
  const [h, m] = tv.time.split(':').map(Number);
  if (preset === 'daily') {
    const n = new Date(now); n.setHours(h ?? 0, m ?? 0, 0, 0);
    if (n <= now) n.setDate(n.getDate() + 1);
    return n;
  }
  if (preset === 'weekly') {
    const n = new Date(now); n.setHours(h ?? 0, m ?? 0, 0, 0);
    let diff = ((tv.dayOfWeek ?? 0) - n.getDay() + 7) % 7;
    if (diff === 0 && n <= now) diff = 7;
    n.setDate(n.getDate() + diff);
    return n;
  }
  if (preset === 'monthly') {
    const dom = tv.dayOfMonth ?? 1;
    const n = new Date(now.getFullYear(), now.getMonth(), dom, h ?? 0, m ?? 0);
    if (n <= now) n.setMonth(n.getMonth() + 1);
    return n;
  }
  if (preset === 'quarterly') {
    const dom = tv.dayOfMonth ?? 1;
    const qMonths = [0, 3, 6, 9];
    for (const qm of qMonths) {
      const d = new Date(now.getFullYear(), qm, dom, h ?? 0, m ?? 0);
      if (d > now) return d;
    }
    return new Date(now.getFullYear() + 1, 0, dom, h ?? 0, m ?? 0);
  }
  return null;
}

function toLocalDateTimeInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* ── 컴포넌트 ── */
export function ReportSettingsPage() {
  const session = useSession();
  const isLeader = session.auth === 'leader';
  const [params, setParams] = useSearchParams();
  const section = params.get('section') === 'events' ? 'events' : 'summary';
  const setSection = (s: 'summary' | 'events') => setParams({ section: s });

  /* 기간 선택 (캘린더) */
  const PERIOD_PRESETS = [
    { key: '1w', label: '1주', days: 7 },
    { key: '2w', label: '2주', days: 14 },
    { key: '1m', label: '1개월', days: 30 },
  ] as const;

  function initRange(days: number) {
    const now = new Date(); now.setHours(0, 0, 0, 0);
    const start = new Date(now); start.setDate(now.getDate() - days);
    return { start, end: now };
  }

  const [rangeStart, setRangeStart] = useState<Date | null>(() => initRange(7).start);
  const [rangeEnd, setRangeEnd] = useState<Date | null>(() => initRange(7).end);
  const [reportTitle, setReportTitle] = useState('');
  const reportTitleEdited = useRef(false);
  const [startTime, setStartTime] = useState('00:00');
  const [endTime, setEndTime] = useState('00:00');
  const [calMonth, setCalMonth] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  const [picking, setPicking] = useState<'start' | 'end'>('start');
  const [calOpen, setCalOpen] = useState(false);
  const [calPos, setCalPos] = useState({ top: 0, left: 0 });
  const calRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  /* 드롭다운 위치 — 스크롤/리사이즈 시 실시간 추적 + 하단 여백 확보 */
  useEffect(() => {
    if (!calOpen) return;
    const spacer = document.createElement('div');
    spacer.style.height = '0';
    spacer.dataset.calSpacer = '1';
    document.body.appendChild(spacer);

    // 드롭다운 렌더 후 필요한 만큼만 spacer 높이 설정
    requestAnimationFrame(() => {
      if (calRef.current) {
        const dropRect = calRef.current.getBoundingClientRect();
        const overflow = dropRect.bottom - window.innerHeight + 80;
        spacer.style.height = overflow > 0 ? `${overflow}px` : '0';
      }
    });

    function update() {
      if (!triggerRef.current) return;
      const r = triggerRef.current.getBoundingClientRect();
      const dropW = 360;
      const left = Math.min(r.left, window.innerWidth - dropW - 12);
      setCalPos({ top: r.bottom + 6, left: Math.max(8, left) });
    }
    update();
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
      spacer.remove();
    };
  }, [calOpen]);

  function handlePresetClick(days: number) {
    const { start, end } = initRange(days);
    setRangeStart(start);
    setRangeEnd(end);
    setStartTime('00:00');
    setEndTime('00:00');
    setPicking('start');
    setCalOpen(false);
  }

  /* 캘린더 외부 클릭 닫기 */
  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      const t = e.target as Node;
      if (calRef.current && !calRef.current.contains(t) && triggerRef.current && !triggerRef.current.contains(t)) setCalOpen(false);
    }
    if (calOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [calOpen]);

  function handleCalDayClick(d: Date) {
    if (picking === 'start') {
      setRangeStart(d);
      setRangeEnd(null);
      setPicking('end');
    } else {
      if (rangeStart && d < rangeStart) {
        setRangeStart(d);
        setRangeEnd(rangeStart);
      } else {
        setRangeEnd(d);
      }
      setPicking('start');
    }
  }

  function isSameDay(a: Date, b: Date) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
  function dayStr(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }

  function applyTime(d: Date, time: string): Date {
    const [h, m] = time.split(':').map(Number);
    const r = new Date(d); r.setHours(h ?? 0, m ?? 0, 0, 0);
    return r;
  }
  const summaryStart = rangeStart ? toLocalDateTimeInput(applyTime(rangeStart, startTime)) : '';
  const summaryEnd = rangeEnd ? toLocalDateTimeInput(applyTime(rangeEnd, endTime)) : '';
  // 날짜 변경 시 사용자가 직접 수정하지 않았으면 기본 제목 자동 설정
  useEffect(() => {
    if (reportTitleEdited.current) return;
    setReportTitle(rangeStart && rangeEnd ? `인프라 활동 보고서 ${dayStr(rangeStart)} ~ ${dayStr(rangeEnd)}` : '인프라 활동 보고서');
  }, [rangeStart, rangeEnd]);

  /* 캘린더 그리드 생성 */
  function buildCalDays(base: Date): (Date | null)[] {
    const y = base.getFullYear(), m = base.getMonth();
    const first = new Date(y, m, 1);
    const startDow = first.getDay(); // 0=일
    const lastDate = new Date(y, m + 1, 0).getDate();
    const cells: (Date | null)[] = [];
    for (let i = 0; i < startDow; i++) cells.push(null);
    for (let d = 1; d <= lastDate; d++) cells.push(new Date(y, m, d));
    return cells;
  }
  function prevMonth() { setCalMonth(p => { const d = new Date(p); d.setMonth(d.getMonth() - 1); return d; }); }
  function nextMonth() { setCalMonth(p => { const d = new Date(p); d.setMonth(d.getMonth() + 1); return d; }); }

  /* 워크스페이스 */
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  /* 스케줄 */
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [schTitle, setSchTitle] = useState('');
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [schTime, setSchTime] = useState('06:00');
  const [schDayOfWeek, setSchDayOfWeek] = useState(1);
  const [schDayOfMonth, setSchDayOfMonth] = useState(1);
  const [schIncludeRange, setSchIncludeRange] = useState(true);
  const autoFilled = useRef(false);

  /* 이벤트 */
  const [evtSettings, setEvtSettings] = useState<Record<string, boolean>>({});
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState(false);

  useEffect(() => {
    setSettingsLoading(true);
    setSettingsError(false);
    getWorkspaces()
      .then(ws => {
        if (ws.length === 0) throw new Error('NO_WORKSPACE');
        const wsId = ws[0]!.id;
        setWorkspaceId(wsId);
        return getReportSettings(wsId);
      })
      .then(settings => {
        setSchedules([...settings.schedules]);
        setEvtSettings({ ...settings.eventSettings });
      })
      .catch(() => {
        setSettingsError(true);
      })
      .finally(() => {
        setSettingsLoading(false);
      });
  }, []);
  const [openDescs, setOpenDescs] = useState<Set<string>>(new Set());

  /* 토스트 */
  const [toast, setToast] = useState('');
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const showToast = useCallback((msg: string) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 2500);
  }, []);

  /* 스케줄 모달 */
  function openSchModal(id?: string) {
    const sch = id ? schedules.find(s => s.id === id) : undefined;
    setEditId(id ?? null);
    setSchTitle(sch ? sch.title : '');
    setSchIncludeRange(sch ? sch.includeRange !== false : true);
    setSelectedPreset(sch ? sch.preset : null);
    setSchTime(sch ? sch.time : '06:00');
    setSchDayOfWeek(sch?.dayOfWeek ?? 1);
    setSchDayOfMonth(sch?.dayOfMonth ?? 1);
    autoFilled.current = false;
    setModalOpen(true);
  }

  function closeSchModal() { setModalOpen(false); }

  function handlePreset(p: string) {
    setSelectedPreset(p);
    if (!schTitle.trim() || autoFilled.current) {
      setSchTitle(PRESET_NAMES[p] ?? '');
      autoFilled.current = true;
    }
  }

  /* 다음 발행일 계산 */
  const tv: TimingValues = { time: schTime, dayOfWeek: schDayOfWeek, dayOfMonth: schDayOfMonth };
  const nextRun = selectedPreset ? calcNextRun(selectedPreset, tv) : null;
  const nextRunStr = nextRun ? fmtDate(nextRun) : '—';

  /* 제목 미리보기 */
  function getPreviewTitle() {
    if (!schTitle || !selectedPreset) return schTitle || '—';
    if (!schIncludeRange) return schTitle;
    if (!nextRun) return schTitle;
    const days = PRESET_DAYS[selectedPreset] ?? 1;
    const start = new Date(nextRun.getTime() - days * 864e5);
    const yy = (d: Date) => String(d.getFullYear()).slice(2);
    const ds = `${yy(start)}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`;
    const de = `${yy(nextRun)}-${pad(nextRun.getMonth() + 1)}-${pad(nextRun.getDate())}`;
    return days === 1 ? `${schTitle} ${de}` : `${schTitle} (${ds} ~ ${de})`;
  }

  async function saveSch() {
    if (!schTitle.trim()) { showToast('보고서 제목을 입력해주세요.'); return; }
    if (!selectedPreset) { showToast('반복 주기를 선택해주세요.'); return; }
    if (!workspaceId) { showToast('워크스페이스를 찾을 수 없습니다.'); return; }
    const req = {
      title: schTitle,
      preset: selectedPreset as SchedulePreset,
      time: schTime,
      includeRange: schIncludeRange,
      dayOfWeek: selectedPreset === 'weekly' ? schDayOfWeek : undefined,
      dayOfMonth: (selectedPreset === 'monthly' || selectedPreset === 'quarterly') ? schDayOfMonth : undefined,
    };
    try {
      if (editId) {
        await updateSchedule(workspaceId, editId, req);
        setSchedules(prev => prev.map(s => s.id === editId ? { ...req, id: editId } : s));
      } else {
        const { id } = await createSchedule(workspaceId, req);
        setSchedules(prev => [...prev, { ...req, id }]);
      }
      closeSchModal();
      showToast(editId ? '스케줄이 수정되었습니다.' : '스케줄이 추가되었습니다.');
    } catch {
      showToast('저장 중 오류가 발생했습니다.');
    }
  }

  async function delSchedule(id: string) {
    if (!workspaceId) return;
    try {
      await deleteSchedule(workspaceId, id);
      setSchedules(prev => prev.filter(s => s.id !== id));
      showToast('스케줄이 삭제되었습니다.');
    } catch {
      showToast('삭제 중 오류가 발생했습니다.');
    }
  }

  /* 이벤트 토글 */
  function toggleEvt(key: EventSettingsKey) {
    setEvtSettings(prev => ({ ...prev, [key]: !(prev[key] !== false) }));
  }
  function toggleDesc(key: string) {
    setOpenDescs(prev => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key); else n.add(key);
      return n;
    });
  }

  /* 현황 보고서 생성 */
  async function generateNow() {
    if (!reportTitle.trim()) { showToast('보고서 제목을 입력해주세요.'); return; }
    if (!summaryStart || !summaryEnd) { showToast('기간을 선택해주세요.'); return; }
    if (summaryStart > summaryEnd) { showToast('시작일시가 종료일시보다 클 수 없습니다.'); return; }
    if (!workspaceId) { showToast('워크스페이스를 찾을 수 없습니다.'); return; }
    try {
      const { runId } = await createSummaryReport(workspaceId, reportTitle, new Date(summaryStart).toISOString(), new Date(summaryEnd).toISOString());
      showToast('보고서 생성을 요청했습니다.');
      startGenerateTracking(runId, workspaceId);
    } catch {
      showToast('보고서 생성 요청 중 오류가 발생했습니다.');
    }
  }

  /* 섹션 전환 시 breadcrumb */
  const SEC_LABELS: Record<string, string> = { summary: '인프라 활동 보고서', events: '이벤트 보고서' };

  /* ── 사이드 서브메뉴 연동 ── */
  useEffect(() => {
    const subItems = document.querySelectorAll<HTMLElement>('.nav-sub-item[data-section]');
    subItems.forEach(el => {
      el.classList.toggle('active', el.dataset.section === section);
    });
    const crumb = document.getElementById('crumb-sub');
    if (crumb) crumb.textContent = SEC_LABELS[section] ?? '';
  }, [section]);

  return (
    <div className="rpt-page">
      {createPortal(<div className={`rpt-toast${toast ? ' show' : ''}`}>{toast}</div>, document.body)}

      <div className="page-inner">
        {/* 섹션 탭 */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          <button
            className={`preset-btn${section === 'summary' ? ' active' : ''}`}
            style={{ flex: 'none', padding: '8px 20px' }}
            onClick={() => setSection('summary')}
          >인프라 활동 보고서</button>
          <button
            className={`preset-btn${section === 'events' ? ' active' : ''}`}
            style={{ flex: 'none', padding: '8px 20px' }}
            onClick={() => setSection('events')}
          >이벤트 보고서</button>
        </div>

        {/* ═══ 섹션 1: 인프라 활동 보고서 ═══ */}
        <div className={`rpt-section${section === 'summary' ? ' active' : ''}`}>
          <div className="rpt-card">
            <div className="rpt-card-header">
              <span className="rpt-card-title">인프라 활동 보고서</span>
              <p className="rpt-card-desc">선택한 기간의 AWS 인프라 활동 이력을 수집·분석하여 보고서를 생성합니다</p>
            </div>
            <div className="card-form">
              <div className="fg">
                <label className="fg-label">보고서 제목</label>
                <input type="text" className="fi-title" value={reportTitle} onChange={e => { setReportTitle(e.target.value); reportTitleEdited.current = true; }} placeholder="인프라 활동 보고서" />
              </div>
              <div className="fg">
                <label className="fg-label">수집 기간</label>
                <div className="cal-row" ref={triggerRef}>
                  {/* 시작 입력 */}
                  <div className={`cal-input-box${picking === 'start' && calOpen ? ' active' : ''}`} onClick={() => { setPicking('start'); if (!calOpen) setCalOpen(true); }}>
                    <svg className="cal-input-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1v3M11 1v3"/></svg>
                    <span className="cal-input-date">{rangeStart ? dayStr(rangeStart) : '시작일'}</span>
                    <span className="cal-input-time-text">{startTime}</span>
                  </div>
                  <span className="cal-sep">~</span>
                  {/* 종료 입력 */}
                  <div className={`cal-input-box${picking === 'end' && calOpen ? ' active' : ''}`} onClick={() => { setPicking('end'); if (!calOpen) setCalOpen(true); }}>
                    <svg className="cal-input-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1v3M11 1v3"/></svg>
                    <span className="cal-input-date">{rangeEnd ? dayStr(rangeEnd) : '종료일'}</span>
                    <span className="cal-input-time-text">{endTime}</span>
                  </div>
                  {/* 프리셋 */}
                  <div className="cal-presets">
                    {PERIOD_PRESETS.map(p => (
                      <button key={p.key} className="cal-preset-chip" onClick={() => handlePresetClick(p.days)}>{p.label}</button>
                    ))}
                  </div>
                </div>
                {/* 캘린더 드롭다운 — Portal */}
                {calOpen && createPortal(
                  <div className="cal-dropdown" ref={calRef} style={{ top: calPos.top, left: calPos.left }}>
                    <div className="cal-body">
                      <div className="cal-nav">
                        <button className="cal-nav-btn" onClick={prevMonth}>
                          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 3L5 8l5 5"/></svg>
                        </button>
                        <span className="cal-nav-title">{calMonth.getFullYear()}년 {calMonth.getMonth() + 1}월</span>
                        <button className="cal-nav-btn" onClick={nextMonth}>
                          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 3l5 5-5 5"/></svg>
                        </button>
                      </div>
                      <div className="cal-grid">
                        {['일','월','화','수','목','금','토'].map(d => <div key={d} className="cal-dow">{d}</div>)}
                        {buildCalDays(calMonth).map((d, i) => {
                          if (!d) return <div key={`e${i}`} className="cal-cell empty" />;
                          const today = new Date(); today.setHours(0,0,0,0);
                          const isToday = isSameDay(d, today);
                          const isStart = rangeStart && isSameDay(d, rangeStart);
                          const isEnd = rangeEnd && isSameDay(d, rangeEnd);
                          const inRange = rangeStart && rangeEnd && d > rangeStart && d < rangeEnd;
                          const cls = ['cal-cell',
                            isStart && 'start',
                            isEnd && 'end',
                            inRange && 'in-range',
                            isToday && !isStart && !isEnd && 'today',
                            d > today && 'future',
                          ].filter(Boolean).join(' ');
                          return (
                            <div key={d.getTime()} className={cls} onClick={() => d <= today && handleCalDayClick(d)}>
                              {d.getDate()}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="cal-time-row">
                      <TimePicker label="시작" value={startTime} onChange={setStartTime} />
                      <TimePicker label="종료" value={endTime} onChange={setEndTime} />
                    </div>
                  </div>
                , document.body)}
              </div>
              <button className="btn-gen" onClick={generateNow} disabled={!rangeStart || !rangeEnd}>
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 8h10M8 3v10" /></svg>
                보고서 생성
              </button>
            </div>
          </div>

          <div className="rpt-card" style={{ marginTop: 20 }}>
            <div className="rpt-card-header">
              <div className="rpt-card-header-row">
                <div>
                  <span className="rpt-card-title">스케줄 관리</span>
                  <p className="rpt-card-desc">주기적으로 자동 생성할 보고서 스케줄을 등록합니다</p>
                </div>
                {isLeader && <button className="btn-add" onClick={() => openSchModal()}>+ 추가</button>}
              </div>
            </div>

            <div className="sch-list">
              {schedules.length === 0 ? (
                <div className="sch-empty">저장된 스케줄이 없습니다</div>
              ) : schedules.map(s => {
                const stv: TimingValues = { time: s.time, dayOfWeek: s.dayOfWeek, dayOfMonth: s.dayOfMonth };
                const sNext = calcNextRun(s.preset, stv);
                return (
                  <div className="sch-row" key={s.id}>
                    <span className="sch-dot" />
                    <span className="sch-name">
                      {s.title} <span className="sch-interval">{PRESETS[s.preset]}</span>
                    </span>
                    <span className="sch-meta">다음: {sNext ? fmtDate(sNext) : '—'}</span>
                    {isLeader && (
                      <div className="sch-actions">
                        <button className="sch-btn edit" title="편집" onClick={() => openSchModal(s.id)}>
                          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M11.5 2.5l2 2L5 13H3v-2z" /><path d="M9.5 4.5l2 2" /></svg>
                        </button>
                        <button className="sch-btn del" title="삭제" onClick={() => delSchedule(s.id)}>
                          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 4h10M6 4V3h4v1M5 4v9h6V4" /></svg>
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* ═══ 섹션 2: 이벤트 보고서 ═══ */}
        <div className={`rpt-section${section === 'events' ? ' active' : ''}`}>
          <div className="rpt-card">
            <div className="rpt-card-header">
              <div className="rpt-card-header-row">
                <div>
                  <span className="rpt-card-title">이벤트 보고서</span>
                  <p className="rpt-card-desc">AWS 이벤트 발생 시 자동으로 보고서를 생성합니다</p>
                </div>
                <button className="btn-save" onClick={async () => {
                  if (!isLeader) { showToast('권한이 없습니다.'); return; }
                  if (!workspaceId) return;
                  try {
                    await updateEventSettings(workspaceId, evtSettings);
                    showToast('이벤트 보고서 설정이 저장되었습니다.');
                  } catch {
                    showToast('설정 저장 중 오류가 발생했습니다.');
                  }
                }} disabled={settingsLoading || settingsError}>설정 저장</button>
              </div>
            </div>

            {EVENT_DEFS.map(g => (
              <div className="eg" key={g.category}>
                <div className="eg-head">
                  <svg className={`eg-ico ${g.ico}`} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" dangerouslySetInnerHTML={{ __html: g.icoSvg }} />
                  <div>
                    <div className="eg-name">{g.category}</div>
                    <div className="eg-desc">{g.desc}</div>
                  </div>
                </div>
                <div className="eg-body">
                  {g.groups.map(sg => (
                    <div key={sg.sub}>
                      <div className="ei-sub">{sg.sub}</div>
                      {sg.items.map(item => (
                        <div className={`ei${openDescs.has(item.key) ? ' open' : ''}`} key={item.key}>
                          <div className="ei-head" onClick={() => toggleDesc(item.key)}>
                            <span className="ei-label">{item.label}<span className="ei-svc">{item.svc}</span></span>
                            <div className="ei-right" onClick={e => e.stopPropagation()}>
                              <label className="rpt-sw" onClick={() => { if (!isLeader) showToast('권한이 없습니다.'); }}>
                                <input type="checkbox" checked={evtSettings[item.key] !== false} onChange={() => toggleEvt(item.key)} disabled={!isLeader || settingsLoading || settingsError} />
                                <div className="tr" /><div className="kn" />
                              </label>
                            </div>
                          </div>
                          <div className="ei-desc" dangerouslySetInnerHTML={{ __html: item.desc }} />
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 스케줄 모달 ── */}
      <div className={`rpt-modal-dim${modalOpen ? ' show' : ''}`} onClick={e => { if (e.target === e.currentTarget) closeSchModal(); }}>
        <div className="rpt-modal">
          <div className="rpt-modal-head">
            <span className="rpt-modal-title">{editId ? '스케줄 편집' : '스케줄 추가'}</span>
            <button className="rpt-modal-close" onClick={closeSchModal}>
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4l8 8M12 4l-8 8" /></svg>
            </button>
          </div>
          <div className="modal-form">
            <div className="mf-group">
              <label className="mf-label">보고서 제목</label>
              <input type="text" className="fi" value={schTitle} onChange={e => { setSchTitle(e.target.value); autoFilled.current = false; }} placeholder="주간 인프라 활동 보고서" style={{ width: '100%', boxSizing: 'border-box' }} />
            </div>
            <div className="mf-group">
              <label className="mf-label">반복 주기</label>
              <div className="preset-group">
                {(['daily', 'weekly', 'monthly', 'quarterly'] as const).map(p => (
                  <button key={p} className={`preset-btn${selectedPreset === p ? ' active' : ''}`} onClick={() => handlePreset(p)}>
                    {PRESETS[p]}
                  </button>
                ))}
              </div>
            </div>
            <div className="mf-group">
              <label className="mf-label">실행 시점</label>
              <div className="mf-timing">
                {selectedPreset === 'weekly' && (
                  <select className="fi" value={schDayOfWeek} onChange={e => setSchDayOfWeek(Number(e.target.value))}>
                    {[1, 2, 3, 4, 5, 6, 0].map(i => (
                      <option key={i} value={i}>{DAY_NAMES[i]}요일</option>
                    ))}
                  </select>
                )}
                {(selectedPreset === 'monthly' || selectedPreset === 'quarterly') && (
                  <>
                    <input type="number" className="fi fi-day" min={1} max={28} value={schDayOfMonth} onChange={e => setSchDayOfMonth(Number(e.target.value))} />
                    <span className="mf-timing-text">일</span>
                  </>
                )}
                <input type="time" className="fi" value={schTime} onChange={e => setSchTime(e.target.value)} />
              </div>
            </div>
            <div className="mf-group">
              <div className="mf-row">
                <span className="mf-label" style={{ marginBottom: 0 }}>다음 발행일</span>
                <span className="mf-next">{nextRunStr}</span>
              </div>
            </div>
            <div className="mf-group mf-last">
              <div className="mf-preview">
                <div className="mf-preview-label">제목 미리보기</div>
                <div className="mf-preview-title">{getPreviewTitle()}</div>
              </div>
              <label className="mf-opt">
                <input type="checkbox" checked={schIncludeRange} onChange={e => setSchIncludeRange(e.target.checked)} />
                <span>수집기간 포함</span>
              </label>
            </div>
          </div>
          <div className="modal-foot">
            <button className="btn-cancel" onClick={closeSchModal}>취소</button>
            <button className="btn-save" onClick={saveSch}>저장</button>
          </div>
        </div>
      </div>
    </div>
  );
}
