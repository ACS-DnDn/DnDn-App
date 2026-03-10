import { useState, useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { TopNav } from './TopNav';
import { Sidebar } from './Sidebar';
import './Layout.css';

function CrumbLink({ to, children }: { to: string; children: React.ReactNode }) {
  const navigate = useNavigate();
  return <a className="crumb-link" href={to} onClick={(e) => { e.preventDefault(); navigate(to); }}>{children}</a>;
}

function buildBreadcrumb(pathname: string, search: string): React.ReactNode {
  const sp = new URLSearchParams(search);
  const home = <CrumbLink to="/dashboard">홈</CrumbLink>;
  const sep = <span className="sep">›</span>;

  if (pathname === '/dashboard' || pathname === '/') return home;

  if (pathname.startsWith('/viewer')) {
    return <>{home}{sep}<CrumbLink to="/documents">문서 보관함</CrumbLink>{sep}<span className="crumb-cur">문서 열람</span></>;
  }
  if (pathname === '/workspace') {
    const sub = sp.get('section') === 'opa' ? '인프라 정책' : '일반';
    return <>{home}{sep}<CrumbLink to="/workspace">워크스페이스</CrumbLink>{sep}<span className="crumb-cur">{sub}</span></>;
  }
  if (pathname === '/workspace/create') {
    return <>{home}{sep}<CrumbLink to="/workspace">워크스페이스</CrumbLink>{sep}<span className="crumb-cur">워크스페이스 생성</span></>;
  }
  if (pathname === '/report-settings') {
    const sub = sp.get('section') === 'events' ? '이벤트 보고서' : '현황 보고서';
    return <>{home}{sep}<CrumbLink to="/report-settings">보고서 생성</CrumbLink>{sep}<span className="crumb-cur">{sub}</span></>;
  }

  const labels: Record<string, string> = {
    '/pending': '미결재', '/documents': '문서 보관함', '/mypage': '마이페이지',
  };
  const label = labels[pathname];
  if (label) return <>{home}{sep}<span className="crumb-cur">{label}</span></>;

  return home;
}

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const toggleSidebar = useCallback(() => setSidebarOpen((prev) => !prev), []);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  const breadcrumb = buildBreadcrumb(location.pathname, location.search);

  return (
    <>
      <TopNav onMenuClick={toggleSidebar} breadcrumb={breadcrumb} />
      <Sidebar open={sidebarOpen} onClose={closeSidebar} />
      <main className="main">
        <div className="main-inner">
          <Outlet />
        </div>
      </main>
    </>
  );
}
