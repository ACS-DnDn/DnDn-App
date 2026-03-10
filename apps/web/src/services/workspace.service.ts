import type { Workspace, GitHubMock } from '@/mocks';
import { wsAccounts, MOCK_GH } from '@/mocks';


export function getWorkspaces(): Workspace[] {
  return wsAccounts.map((ws) => ({ ...ws }));
}

export function getWorkspaceById(id: string): Workspace | undefined {
  const ws = wsAccounts.find((ws) => ws.id === id);
  return ws ? { ...ws } : undefined;
}

export function getGitHubData(): GitHubMock {
  return structuredClone(MOCK_GH);
}
