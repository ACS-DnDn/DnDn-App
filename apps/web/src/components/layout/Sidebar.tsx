import { useState, useEffect, useContext } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';
import { apiFetch } from '@/services/api';
import { AuthContext } from '@/contexts/AuthContext';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

interface NavSubItem {
  label: string;
  href: string;
}

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  badge?: number;
  children?: NavSubItem[];
}

const NAV_ITEMS: { section: string; items: NavItem[] }[] = [
  {
    section: '업무 관리',
    items: [
      {
        label: '홈', href: '/dashboard',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2 10l8-6 8 6"/><path d="M4.5 9v7a1 1 0 001 1h3.5v-4h2v4h3.5a1 1 0 001-1V9"/></svg>,
      },
      {
        label: '보고서 생성', href: '/report-settings',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="3" width="14" height="14" rx="2"/><path d="M7 13V9"/><path d="M10 13V7"/><path d="M13 13v-3"/></svg>,
        children: [
          { label: '인프라 활동 보고서', href: '/report-settings?section=summary' },
          { label: '이벤트 보고서', href: '/report-settings?section=events' },
        ],
      },
      {
        label: '작업계획서 작성', href: '/plan',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3H5a1 1 0 00-1 1v12a1 1 0 001 1h10a1 1 0 001-1V8l-4-5z"/><path d="M12 3v5h5"/></svg>,
      },
      {
        label: '처리할 문서', href: '/pending',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 4h12v12H4z" rx="1"/><path d="M7 10l2 2 4-4"/></svg>,
      },
      {
        label: '문서 보관함', href: '/documents',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="2" width="14" height="5" rx="1"/><path d="M8 4.5h4"/><rect x="3" y="8" width="14" height="5" rx="1"/><path d="M8 10.5h4"/><rect x="3" y="14" width="14" height="5" rx="1"/><path d="M8 16.5h4"/></svg>,
      },
    ],
  },
  {
    section: '설정',
    items: [
      {
        label: '워크스페이스', href: '/workspace',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 10h14M10 3c-3 3-3 11 0 14M10 3c3 3 3 11 0 14"/><circle cx="10" cy="10" r="7"/></svg>,
        children: [
          { label: '일반', href: '/workspace?section=general' },
          { label: '인프라 정책', href: '/workspace?section=opa' },
        ],
      },
      {
        label: '마이페이지', href: '/mypage',
        icon: <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="10" cy="7" r="3"/><path d="M3 17c0-3.3 3.1-6 7-6s7 2.7 7 6"/></svg>,
      },
    ],
  },
];

export function Sidebar({ open, onClose }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const { isDark, toggle } = useTheme();
  const { logout } = useContext(AuthContext);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    apiFetch<{ success: boolean; data: { docStats: { pending: number } } }>('/dashboard')
      .then(res => setPendingCount(res.data.docStats.pending))
      .catch(() => {});
  }, []);

  const logoSrc = isDark && session.company.logoDarkUrl
    ? session.company.logoDarkUrl
    : session.company.logoUrl;

  return (
    <>
      <div
        className={`overlay${open ? ' visible' : ''}`}
        onClick={onClose}
      />
      <aside className={`sidebar${open ? ' open' : ''}`}>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((group, gi) => (
            <div key={gi}>
              <span className="nav-section-label" style={gi > 0 ? { marginTop: 8 } : undefined}>
                {group.section}
              </span>
              {group.items.map((item) => {
                const currentFull = location.pathname + location.search;
                const isActive = location.pathname === item.href
                  || (item.href === '/dashboard' && location.pathname === '/')
                  || (item.children?.some(c => location.pathname === c.href.split('?')[0]));
                return (
                  <div key={item.href} className="nav-group">
                    <a
                      className={`nav-item${isActive ? ' active' : ''}`}
                      href={item.children?.[0]?.href ?? item.href}
                      onClick={(e) => {
                        e.preventDefault();
                        onClose();
                        navigate(item.children?.[0]?.href ?? item.href);
                      }}
                    >
                      {item.icon}
                      {item.label}
                      {(() => { const b = item.href === '/pending' ? pendingCount : (item.badge ?? 0); return b > 0 ? <span className="nav-badge">{b}</span> : null; })()}
                    </a>
                    {item.children && (
                      <div className={`nav-sub${isActive ? ' stay-open' : ''}`}>
                        {item.children.map((sub) => {
                          const defaultHref = item.children![0]!.href;
                          const subActive = currentFull === sub.href
                            || (sub.href === defaultHref && currentFull === item.href);
                          return (
                            <a
                              key={sub.href}
                              className={`nav-sub-item${subActive ? ' active' : ''}`}
                              href={sub.href}
                              onClick={(e) => {
                                e.preventDefault();
                                onClose();
                                navigate(sub.href);
                              }}
                            >
                              {sub.label}
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="nav-item" style={{ gap: 10, cursor: 'default', pointerEvents: 'none' }}>
            {logoSrc && (
              <img className="sidebar-company-logo" src={logoSrc} alt="" />
            )}
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{session.name}</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{session.position ?? session.role}</div>
            </div>
            <button
              className="sidebar-toggle"
              onClick={(e) => { e.stopPropagation(); toggle(); }}
              style={{ pointerEvents: 'all' }}
              aria-label="테마 전환"
            >
              <div className="toggle-track"><div className="toggle-thumb" /></div>
            </button>
          </div>
          <button
            className="sidebar-logout"
            onClick={() => { onClose(); logout(); }}
          >
            <svg className="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M7 17H4a1 1 0 01-1-1V4a1 1 0 011-1h3" />
              <path d="M14 14l3-4-3-4" />
              <path d="M17 10H8" />
            </svg>
            로그아웃
          </button>
        </div>
      </aside>
    </>
  );
}
