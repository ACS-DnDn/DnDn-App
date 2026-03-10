import type { Document, RefDocMeta, DocDataItem, MockDocContent } from '@/mocks';
import { ALL_DOCS, REF_DOCS, docData, MOCK_DOC_CONTENT } from '@/mocks';


export function getDocuments(): Document[] {
  return ALL_DOCS.map((d) => ({ ...d }));
}

export function getDocumentById(id: number): Document | undefined {
  const doc = ALL_DOCS.find((d) => d.id === id);
  return doc ? { ...doc } : undefined;
}

export function getRefDocs(): Record<string, RefDocMeta> {
  return Object.fromEntries(
    Object.entries(REF_DOCS).map(([k, v]) => [k, { ...v, meta: v.meta.map(m => [...m]) }])
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
