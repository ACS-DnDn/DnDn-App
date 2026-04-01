import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  apiFetch: apiFetchMock,
}));

import { checkReportReady, getReportSettings } from '@/services/report.service';

describe('report.service', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('encodes workspace id when loading report settings', async () => {
    const payload = {
      schedules: [{ id: 'sch-1', title: '주간보고서', preset: 'weekly', time: '09:00', includeRange: true }],
      eventSettings: { guardduty: true },
    };
    apiFetchMock.mockResolvedValue({ success: true, data: payload });

    await expect(getReportSettings('workspace with space')).resolves.toEqual(payload);
    expect(apiFetchMock).toHaveBeenCalledWith('/report-settings?workspaceId=workspace%20with%20space');
  });

  it('returns false when report readiness check fails', async () => {
    apiFetchMock.mockRejectedValue(new Error('network error'));

    await expect(checkReportReady('run-1', 'ws-1')).resolves.toBe(false);
    expect(apiFetchMock).toHaveBeenCalledWith('/reports/status/run-1?workspaceId=ws-1');
  });
});
