import type { Document, RefDocMeta, DocDataItem, MockDocContent } from '@/mocks';
import { ALL_DOCS, REF_DOCS, docData, MOCK_DOC_CONTENT } from '@/mocks';


export function getDocuments(): Document[] {
  return ALL_DOCS;
}

export function getDocumentById(id: number): Document | undefined {
  return ALL_DOCS.find((d) => d.id === id);
}

export function getRefDocs(): Record<string, RefDocMeta> {
  return REF_DOCS;
}

export function getDocData(): DocDataItem[] {
  return docData;
}

export function getDocContent(): MockDocContent {
  return MOCK_DOC_CONTENT;
}
