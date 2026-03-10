import type { Workspace, GitHubMock } from '@/mocks';
import { wsAccounts, MOCK_GH } from '@/mocks';


export function getWorkspaces(): Workspace[] {
  return wsAccounts;
}

export function getWorkspaceById(id: string): Workspace | undefined {
  return wsAccounts.find((ws) => ws.id === id);
}

export function getGitHubData(): GitHubMock {
  return MOCK_GH;
}
