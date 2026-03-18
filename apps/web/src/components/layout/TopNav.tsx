import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';
import { apiFetch } from '@/services/api';
import { AnimatedLogo } from './AnimatedLogo';

interface TopNavProps {
  breadcrumb?: React.ReactNode;
  onMenuClick: () => void;
}

export function TopNav({ breadcrumb, onMenuClick }: TopNavProps) {
  const navigate = useNavigate();
  const session = useSession();
  const { isDark } = useTheme();

  const companyLogoSrc = session.company.logoUrl;
  const [ws, setWs] = useState<{ alias: string; acctId: string } | null>(null);

  useEffect(() => {
    apiFetch<{ success: boolean; data: { items: { alias: string; acctId: string }[] } }>('/workspaces')
      .then(res => setWs(res.data.items[0] ?? null))
      .catch(() => {});
  }, []);

  return (
    <header className="topnav">
      <button className="menu-btn" onClick={onMenuClick} aria-label="메뉴">
        <svg width="20" height="16" viewBox="0 0 16 13" fill="none">
          <rect x="0" y="0" width="16" height="3" rx="1" fill="currentColor" />
          <rect x="0" y="5" width="16" height="3" rx="1" fill="currentColor" />
          <rect x="0" y="10" width="16" height="3" rx="1" fill="currentColor" />
        </svg>
      </button>

      <a className="nav-logo-link" href="/dashboard" onClick={(e) => { e.preventDefault(); navigate('/dashboard'); }}>
        <AnimatedLogo variant={isDark ? 'dark' : 'light'} className="nav-logo-obj" />
      </a>

      {breadcrumb && (
        <div className="nav-title">
          {breadcrumb}
        </div>
      )}

      <div className="topnav-right">
        {ws && (
          <span className="ws-label">
            {ws.alias} <span className="ws-acct">({ws.acctId})</span>
          </span>
        )}
        <div className="divider-v" />
        <div className="profile-info">
          <span className="profile-name">{session.name}</span>
          <span className="profile-role">{session.role}</span>
        </div>
        <span className="company-name">{session.company.name}</span>
        <div className="divider-v" />
        {companyLogoSrc && (
          <img className="company-logo" src={companyLogoSrc} alt="" />
        )}
      </div>
    </header>
  );
}
