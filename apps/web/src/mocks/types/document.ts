export type DocType = '계획서' | '이벤트보고서' | '주간보고서';
export type DocStatus = 'progress' | 'done' | 'rejected' | 'failed';
export type DocAction = 'approve' | 'rejected' | null;

export interface Document {
  id: number;
  docNum?: string;
  name: string;
  author: string;
  date: string;
  type: DocType;
  status: DocStatus;
  action: DocAction;
  icon: string;
  workspace: string;
}

export interface RefDocMeta {
  icon: string;
  title: string;
  meta: [string, string][];
  body: string;
}

export interface DocDataItem {
  no: string;
  name: string;
  author: string;
  date: string;
}

export interface DocContentType {
  hasTerraform: boolean;
  render: (doc: Document) => string;
}

export type MockDocContent = Record<string, DocContentType>;
