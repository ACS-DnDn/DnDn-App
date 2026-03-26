import { apiFetch } from '@/services/api';
import type { Document } from '@/mocks';

interface ApiDocItem {
  id: string;
  docNum: string;
  name: string;
  author: string;
  date: string;
  type: string;
  status: string;
  action: string | null;
  isRead: boolean;
  workspace?: string;
  prStatus?: string;
}

function mapDoc(item: ApiDocItem): Document {
  return {
    id: item.id,
    docNum: item.docNum,
    name: item.name,
    author: item.author,
    date: item.date,
    type: item.type as Document['type'],
    status: item.status as Document['status'],
    action: item.action as Document['action'],
    isRead: item.isRead,
    icon: '📄',
    workspace: item.workspace ?? '',
    prStatus: item.prStatus,
  };
}

export async function getDocuments(params?: {
  tab?: string;
  keyword?: string;
  searchField?: string;
  type?: string;
  status?: string;
  page?: number;
  pageSize?: number;
  archived?: boolean;
}): Promise<{ total: number; items: Document[] }> {
  const query = new URLSearchParams();
  if (params?.tab) query.set('tab', params.tab);
  if (params?.keyword) query.set('keyword', params.keyword);
  if (params?.searchField) query.set('searchField', params.searchField);
  if (params?.type) query.set('type', params.type);
  if (params?.status) query.set('status', params.status);
  if (params?.page) query.set('page', String(params.page));
  if (params?.pageSize) query.set('pageSize', String(params.pageSize));
  if (params?.archived != null) query.set('archived', String(params.archived));

  const qs = query.toString();
  const res = await apiFetch<{ success: boolean; data: { total: number; page: number; pageSize: number; items: ApiDocItem[] } }>(
    `/documents${qs ? `?${qs}` : ''}`
  );
  return { total: res.data.total, items: res.data.items.map(mapDoc) };
}

export async function getAllDocuments(
  params?: Omit<Parameters<typeof getDocuments>[0], 'page' | 'pageSize'>,
): Promise<Document[]> {
  const PAGE_SIZE = 100;
  let page = 1;
  const all: Document[] = [];
  while (true) {
    const res = await getDocuments({ ...params, page, pageSize: PAGE_SIZE });
    all.push(...res.items);
    if (all.length >= res.total || res.items.length < PAGE_SIZE) break;
    page++;
  }
  return all;
}

export async function markDocumentsAsRead(ids: string[]): Promise<void> {
  if (ids.length === 0) return;
  await apiFetch<{ success: boolean }>('/documents/read', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
}

// ── 첨부파일 ──────────────────────────────────────────────

export async function getAttachmentUploadUrl(
  documentId: string,
  fileName: string,
  fileSizeKb: number,
): Promise<{ attachmentId: string; uploadUrl: string }> {
  const qs = new URLSearchParams({ fileName, fileSizeKb: String(fileSizeKb) });
  const res = await apiFetch<{ success: boolean; data: { attachmentId: string; uploadUrl: string } }>(
    `/documents/${documentId}/attachments/presign?${qs}`,
    { method: 'POST' },
  );
  return res.data;
}

export async function uploadAttachment(uploadUrl: string, file: File): Promise<void> {
  const res = await fetch(uploadUrl, { method: 'PUT', body: file });
  if (!res.ok) {
    throw new Error(`업로드 실패: ${res.status} ${res.statusText}`);
  }
}

export async function getAttachmentDownloadUrl(
  documentId: string,
  fileId: string,
): Promise<string> {
  const res = await apiFetch<{ success: boolean; data: { downloadUrl: string } }>(
    `/documents/${documentId}/attachments/${fileId}/download`,
  );
  return res.data.downloadUrl;
}

export async function deleteAttachment(documentId: string, fileId: string): Promise<void> {
  await apiFetch<{ success: boolean }>(`/documents/${documentId}/attachments/${fileId}`, {
    method: 'DELETE',
  });
}

// ── 문서 삭제 ─────────────────────────────────────────────

export async function deleteDocument(documentId: string): Promise<void> {
  await apiFetch<{ success: boolean }>(`/documents/${documentId}`, {
    method: 'DELETE',
  });
}

// ── 문서 상세 ─────────────────────────────────────────────

export async function getDocumentById(id: string): Promise<Document | undefined> {
  try {
    const raw = await apiFetch<{ success: boolean; data: {
      id: string; title: string; type: string; status: string; action?: string | null;
      authorId?: string | null; author?: { name: string }; createdAt?: string; workspace?: string;
      content?: string; terraform?: Record<string, string>;
      refDocs?: { id: string; title: string; type: string }[];
      attachments?: { id: string; name: string; sizeKb?: number }[];
      approvalLine?: import('@/mocks/types/document').ApprovalLineItem[];
      prNumber?: number; prUrl?: string; prStatus?: string;
      autoMerge?: boolean;
      deployLog?: import('@/mocks/types/document').DeployLogEntry[];
    } }>(`/documents/${id}`);
    const res = raw.data;
    return {
      id: res.id,
      name: res.title,
      author: res.author?.name ?? '',
      date: res.createdAt ?? '',
      type: res.type as Document['type'],
      status: res.status as Document['status'],
      action: (res.action ?? null) as Document['action'],
      authorId: res.authorId ?? undefined,
      icon: '📄',
      workspace: res.workspace ?? '',
      content: res.content,
      terraform: res.terraform,
      refDocs: res.refDocs,
      refDocIds: res.refDocs?.map(d => d.id),
      attachments: res.attachments,
      approvalLine: res.approvalLine,
      prNumber: res.prNumber,
      prUrl: res.prUrl,
      prStatus: res.prStatus,
      autoMerge: res.autoMerge,
      deployLog: res.deployLog,
    };
  } catch (err) {
    if (err instanceof Error && err.message.startsWith('API 404')) return undefined;
    throw err;
  }
}
