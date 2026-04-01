import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  apiFetch: apiFetchMock,
}));

import { getOpaSettings, saveOpaSettings } from '@/services/workspace.service';

describe('workspace.service', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('maps OPA settings into UI-friendly shape', async () => {
    apiFetchMock.mockResolvedValue({
      success: true,
      data: {
        policies: [
          {
            category: '네트워크 보안',
            items: [
              {
                key: 'net-sg-open',
                label: '보안그룹 과다 개방',
                on: true,
                severity: 'block',
                params: null,
              },
            ],
          },
        ],
      },
    });

    await expect(getOpaSettings('ws-1')).resolves.toEqual([
      {
        category: '네트워크 보안',
        items: [
          {
            key: 'net-sg-open',
            label: '보안그룹 과다 개방',
            on: true,
            severity: 'block',
            params: null,
            exceptions: [],
          },
        ],
      },
    ]);
  });

  it('strips UI-only exceptions before saving policies', async () => {
    apiFetchMock.mockResolvedValue({ success: true, data: { savedAt: '2026-04-01T00:00:00Z' } });

    await saveOpaSettings('ws-1', [
      {
        category: '네트워크 보안',
        items: [
          {
            key: 'net-sg-open',
            label: '보안그룹 과다 개방',
            on: true,
            severity: 'warn',
            params: { type: 'list', label: '허용 CIDR', values: ['10.0.0.0/8'] },
            exceptions: ['trusted'],
          },
        ],
      },
    ]);

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/workspaces/ws-1/opa-settings',
      expect.objectContaining({
        method: 'PUT',
        body: expect.any(String),
      }),
    );

    const [, options] = apiFetchMock.mock.calls[0] ?? [];
    expect(JSON.parse((options as { body: string }).body)).toEqual({
      policies: [
        {
          category: '네트워크 보안',
          items: [
            {
              key: 'net-sg-open',
              label: '보안그룹 과다 개방',
              on: true,
              severity: 'warn',
              params: { type: 'list', label: '허용 CIDR', values: ['10.0.0.0/8'] },
            },
          ],
        },
      ],
    });
  });
});
