export type DocType = '계획서' | '작업계획서' | '이벤트보고서' | '주간보고서' | '헬스이벤트보고서';
export type DocStatus = 'progress' | 'done' | 'rejected' | 'failed';
export type DocAction = 'approve' | 'rejected' | null;

export interface ApprovalLineItem {
  seq: number;
  type: string;       // "작성자" | "결재" | "협조" | "참조"
  name: string;
  role: string;
  status: string;     // "author" | "current" | "wait" | "approved" | "rejected"
  date?: string;
  comment?: string;
}

export interface RefDocItem {
  id: string;
  title: string;
  type: string;
  docNum?: string;
}

export interface AttachmentItem {
  id: string;
  name: string;
  sizeKb?: number;
}

export interface Document {
  id: string;
  docNum?: string;
  name: string;
  author: string;
  date: string;
  type: DocType;
  status: DocStatus;
  action: DocAction;
  authorId?: string;
  icon: string;
  workspace: string;
  content?: string;
  terraform?: Record<string, string>;
  refDocIds?: string[];
  refDocs?: RefDocItem[];
  attachments?: AttachmentItem[];
  approvalLine?: ApprovalLineItem[];
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
