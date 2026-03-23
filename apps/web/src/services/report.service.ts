import { apiFetch } from '@/services/api';
import type { Schedule, EventSettings, SchedulePreset } from '@/mocks';

interface ReportSettingsData {
  schedules: Schedule[];
  eventSettings: EventSettings;
}

interface ApiReportSettingsResponse {
  success: boolean;
  data: { schedules: Schedule[]; eventSettings: EventSettings };
}

export async function getReportSettings(workspaceId: string): Promise<ReportSettingsData> {
  const res = await apiFetch<ApiReportSettingsResponse>(
    `/report-settings?workspaceId=${encodeURIComponent(workspaceId)}`,
  );
  return {
    schedules: res.data.schedules,
    eventSettings: res.data.eventSettings,
  };
}

interface ScheduleRequest {
  title: string;
  preset: SchedulePreset;
  time: string;
  includeRange: boolean;
  dayOfWeek?: number;
  dayOfMonth?: number;
}

export async function createSchedule(
  workspaceId: string,
  req: ScheduleRequest,
): Promise<{ id: string }> {
  const res = await apiFetch<{ success: boolean; data: { id: string } }>(
    `/report-settings/schedules?workspaceId=${encodeURIComponent(workspaceId)}`,
    { method: 'POST', body: JSON.stringify(req) },
  );
  return { id: res.data.id };
}

export async function updateSchedule(
  workspaceId: string,
  scheduleId: string,
  req: ScheduleRequest,
): Promise<void> {
  await apiFetch<{ success: boolean; data: { id: string } }>(
    `/report-settings/schedules/${encodeURIComponent(scheduleId)}?workspaceId=${encodeURIComponent(workspaceId)}`,
    { method: 'PATCH', body: JSON.stringify(req) },
  );
}

export async function deleteSchedule(
  workspaceId: string,
  scheduleId: string,
): Promise<void> {
  await apiFetch<void>(
    `/report-settings/schedules/${encodeURIComponent(scheduleId)}?workspaceId=${encodeURIComponent(workspaceId)}`,
    { method: 'DELETE' },
  );
}

export async function createSummaryReport(
  workspaceId: string,
  title: string,
  startDate: string,
  endDate: string,
): Promise<{ reportId: number; runId: string }> {
  const res = await apiFetch<{ success: boolean; data: { reportId: number; runId: string } }>(
    `/reports/summary?workspaceId=${encodeURIComponent(workspaceId)}`,
    {
      method: 'POST',
      body: JSON.stringify({ title, startDate, endDate }),
    },
  );
  return res.data;
}

export async function updateEventSettings(
  workspaceId: string,
  settings: Record<string, boolean>,
): Promise<void> {
  await apiFetch<{ success: boolean; data: { eventSettings: Record<string, boolean> } }>(
    `/report-settings/events?workspaceId=${encodeURIComponent(workspaceId)}`,
    { method: 'PATCH', body: JSON.stringify({ settings }) },
  );
}
