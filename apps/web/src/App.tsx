import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { Layout } from '@/components/layout/Layout';
import { LoginPage } from '@/features/login/LoginPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { MyPage } from '@/features/mypage/MyPage';
import { DocumentsPage } from '@/features/documents/DocumentsPage';
import { PendingPage } from '@/features/pending/PendingPage';
import { WorkspacePage } from '@/features/workspace/WorkspacePage';
import { WorkspaceCreatePage } from '@/features/workspace-create/WorkspaceCreatePage';
import { ReportSettingsPage } from '@/features/report-settings/ReportSettingsPage';
import { ViewerPage } from '@/features/viewer/ViewerPage';
import { PlanPage } from '@/features/plan/PlanPage';

export function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/plan" element={<PlanPage />} />
            <Route element={<Layout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/report-settings" element={<ReportSettingsPage />} />
              <Route path="/pending" element={<PendingPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/viewer/:id" element={<ViewerPage />} />
              <Route path="/workspace" element={<WorkspacePage />} />
              <Route path="/workspace/create" element={<WorkspaceCreatePage />} />
              <Route path="/mypage" element={<MyPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
