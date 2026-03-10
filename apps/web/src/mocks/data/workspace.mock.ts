import type { Workspace, GitHubMock } from '../types/workspace';

export const wsAccounts: Workspace[] = [
  { id: 'ws-001', alias: 'Production',  acctId: '451017115109', owner: '송창하', githubOrg: 'ACS-DnDn', repo: 'dndn-infra', path: 'envs/prd', branch: 'main',    icon: 'rocket', memo: '운영 환경 — 변경 시 RFC 필수' },
  { id: 'ws-002', alias: 'Staging',     acctId: '123456789012', owner: '송창하', githubOrg: 'ACS-DnDn', repo: 'dndn-infra', path: 'envs/stg', branch: 'main',    icon: 'flask',  memo: '스테이징 테스트용' },
  { id: 'ws-003', alias: 'Development', acctId: '987654321098', owner: '송창하', githubOrg: 'ACS-DnDn', repo: 'dndn-infra', path: 'envs/dev', branch: 'develop', icon: 'code',   memo: '' },
];

export const MOCK_GH: GitHubMock = {
  orgs: ['ACS-DnDn', 'my-personal'],
  repos: {
    'ACS-DnDn':    ['dndn-infra', 'dndn-app', 'dndn-docs'],
    'my-personal': ['side-project', 'dotfiles'],
  },
  branches: {
    'dndn-infra':    ['main', 'develop', 'feature/vpc'],
    'dndn-app':      ['main', 'develop'],
    'dndn-docs':     ['main'],
    'side-project':  ['main', 'dev'],
    'dotfiles':      ['main'],
  },
};
