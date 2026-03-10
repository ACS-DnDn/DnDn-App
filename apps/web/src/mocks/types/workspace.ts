export type IconKey = 'server' | 'cloud' | 'shield' | 'code' | 'database' | 'flask' | 'rocket' | 'lock';

export interface Workspace {
  id: string;
  alias: string;
  acctId: string;
  owner: string;
  githubOrg: string;
  repo: string;
  path: string;
  branch: string;
  icon: IconKey;
  memo: string;
}

export interface GitHubMock {
  orgs: string[];
  repos: Record<string, string[]>;
  branches: Record<string, string[]>;
}
