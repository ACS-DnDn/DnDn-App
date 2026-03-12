import { apiFetch } from '@/services/api';
import type { DashboardData } from '@/mocks';

export async function getDashboard(): Promise<DashboardData> {
  const res = await apiFetch<{ success: boolean; data: DashboardData }>('/dashboard');
  if (!res.success || !res.data) throw new Error('getDashboard: invalid response');
  return res.data;
}
