import { apiFetch } from '@/services/api';
import type { DashboardData } from '@/mocks';

export async function getDashboard(): Promise<DashboardData> {
  const res = await apiFetch<{ success: boolean; data: DashboardData }>('/dashboard');
  return res.data;
}
