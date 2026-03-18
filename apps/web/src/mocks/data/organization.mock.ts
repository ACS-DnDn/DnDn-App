import type { OrgDept } from '../types/organization';

export const orgData: OrgDept[] = [
  { dept: '인프라팀',   members: [{ id: 'm1', name: '김민준', rank: '시니어 엔지니어' }, { id: 'm2', name: '한동훈', rank: '부팀장' }] },
  { dept: 'DevOps팀',   members: [{ id: 'm3', name: '이서연', rank: '엔지니어' }] },
  { dept: '클라우드팀', members: [{ id: 'm4', name: '최현우', rank: '매니저' }] },
  { dept: 'SRE팀',      members: [{ id: 'm5', name: '정수빈', rank: '엔지니어' }] },
  { dept: '보안팀',     members: [{ id: 'm6', name: '오지민', rank: '팀장' }] },
];
