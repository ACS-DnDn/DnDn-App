import { apiFetch } from '@/services/api';
import type { Document, RefDocMeta, DocDataItem, MockDocContent } from '@/mocks';
import { REF_DOCS, docData, MOCK_DOC_CONTENT } from '@/mocks';

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
    icon: '📄',
    workspace: item.workspace ?? '',
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

export async function getDocumentById(id: string): Promise<Document | undefined> {
  try {
    const res = await apiFetch<{
      id: string; title: string; type: string; status: string;
      author?: { name: string }; date?: string; workspace?: string;
    }>(`/documents/${id}`);
    return {
      id: res.id,
      name: res.title,
      author: res.author?.name ?? '',
      date: res.date ?? '',
      type: res.type as Document['type'],
      status: res.status as Document['status'],
      action: null,
      icon: '📄',
      workspace: res.workspace ?? '',
    };
  } catch (err) {
    if (err instanceof Error && err.message.startsWith('API 404')) return undefined;
    throw err;
  }
}

// 아래는 PlanPage 등에서 사용하는 mock 기반 함수 — 해당 페이지 API 연동 시 교체
export function getRefDocs(): Record<string, RefDocMeta> {
  return Object.fromEntries(
    Object.entries(REF_DOCS).map(([k, v]) => [k, { ...v, meta: v.meta.map((m) => [...m]) }])
  ) as Record<string, RefDocMeta>;
}

export function getDocData(): DocDataItem[] {
  return docData.map((d) => ({ ...d }));
}

export function getDocContent(): MockDocContent {
  return Object.fromEntries(
    Object.entries(MOCK_DOC_CONTENT).map(([k, v]) => [k, { ...v }])
  ) as MockDocContent;
}
