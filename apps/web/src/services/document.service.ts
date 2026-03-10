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
  return structuredClone(REF_DOCS);
}

export function getDocData(): DocDataItem[] {
  return docData.map((d) => ({ ...d }));
}

export function getDocContent(): MockDocContent {
  return structuredClone(MOCK_DOC_CONTENT);
}
