import { apiFetch } from '@/services/api';
import type { Workspace, OpaCategory } from '@/mocks';

interface ApiOpaPolicyItem {
  key: string;
  label: string;
  on: boolean;
  severity: 'block' | 'warn';
  params: unknown;
}
interface ApiOpaCategoryItem {
  category: string;
  items: ApiOpaPolicyItem[];
}

export async function getWorkspaces(): Promise<Workspace[]> {
  const res = await apiFetch<{ success: boolean; data: { items: Workspace[] } }>('/workspaces');
  return res.data.items;
}

export async function getWorkspaceById(id: string): Promise<Workspace | undefined> {
  const workspaces = await getWorkspaces();
  return workspaces.find((ws) => ws.id === id);
}

export async function getOpaSettings(workspaceId: string): Promise<OpaCategory[]> {
  const res = await apiFetch<{ success: boolean; data: { policies: ApiOpaCategoryItem[] } }>(
    `/workspaces/${workspaceId}/opa-settings`
  );
  return res.data.policies.map((cat) => ({
    category: cat.category,
    items: cat.items.map((item) => ({
      key: item.key,
      label: item.label,
      on: item.on,
      severity: item.severity,
      params: item.params ?? null,
      exceptions: [],
    })),
  })) as OpaCategory[];
}

export async function saveOpaSettings(workspaceId: string, policies: OpaCategory[]): Promise<void> {
  await apiFetch<{ success: boolean; data: { savedAt: string } }>(
    `/workspaces/${workspaceId}/opa-settings`,
    {
      method: 'PUT',
      body: JSON.stringify({
        policies: policies.map((cat) => ({
          category: cat.category,
          items: cat.items.map(({ exceptions: _exc, ...item }) => item),
        })),
      }),
    }
  );
}

