import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  apiFetch: apiFetchMock,
}));

import { getDashboard } from '@/services/dashboard.service';

describe('getDashboard', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('returns dashboard data when API responds successfully', async () => {
    const dashboard = {
      stats: { total: 5, pending: 2, completed: 3 },
      notices: [],
      pendingDocs: [],
      completedDocs: [],
    };
    apiFetchMock.mockResolvedValue({ success: true, data: dashboard });

    await expect(getDashboard()).resolves.toEqual(dashboard);
    expect(apiFetchMock).toHaveBeenCalledWith('/dashboard');
  });

  it('throws when API response is missing data', async () => {
    apiFetchMock.mockResolvedValue({ success: true, data: null });

    await expect(getDashboard()).rejects.toThrow('getDashboard: invalid response');
  });
});
