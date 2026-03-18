import { apiFetch } from '@/services/api';
import type { ReportSettings, Schedule, EventSettings } from '@/mocks';
import { reportSettings as mockSettings } from '@/mocks';

interface ApiReportSettingsResponse {
  success: boolean;
  data: { schedules: Schedule[]; eventSettings: EventSettings };
}

export async function getReportSettings(): Promise<ReportSettings> {
  const res = await apiFetch<ApiReportSettingsResponse>('/report-settings');
  // summary, opa는 API 미제공 — mock 기본값 유지
  return {
    ...mockSettings,
    schedules: res.data.schedules,
    eventSettings: res.data.eventSettings,
  };
}
