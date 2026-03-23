export interface DocStats {
  pending: number;
  ongoing: number;
  newDoc: number;
}

export type NoticeType = 'notice' | 'update';

export interface Notice {
  id: number;
  type: NoticeType;
  title: string;
  author: string;
  date: string;
}

export type PendingDocStatus = 'waiting' | 'rejected';
export type PendingDocType = '이벤트' | '계획서';

export interface PendingDoc {
  id: string;
  docNum: string;
  title: string;
  status: PendingDocStatus;
  type: PendingDocType;
  author: string;
  date: string;
  workspace: string;
}

export type CompletedDocType = '이벤트' | '계획서' | '주간';

export interface CompletedDoc {
  id: string;
  docNum: string;
  title: string;
  type: CompletedDocType;
  author: string;
  date: string;
  workspace: string;
}

export interface DashboardData {
  docStats: DocStats;
  notices: Notice[];
  pendingDocs: PendingDoc[];
  completedDocs: CompletedDoc[];
  tasks: string[];
}
