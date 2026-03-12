import { apiFetch } from '@/services/api';
import type { Workspace, GitHubMock } from '@/mocks';
import { MOCK_GH } from '@/mocks';

export async function getWorkspaces(): Promise<Workspace[]> {
  const res = await apiFetch<{ success: boolean; data: { items: Workspace[] } }>('/workspaces');
  return res.data.items;
}

export async function getWorkspaceById(id: string): Promise<Workspace | undefined> {
  const workspaces = await getWorkspaces();
  return workspaces.find((ws) => ws.id === id);
}

// GitHub 데이터는 OAuth 흐름에서 동적으로 조회 — mock 유지
export function getGitHubData(): GitHubMock {
  return structuredClone(MOCK_GH);
}
