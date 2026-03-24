import { useState, useRef, useEffect, useCallback } from 'react';
import { useSession } from '@/hooks/useSession';
import { apiFetch } from '@/services/api';
import './MyPage.css';

const AUTH_LABELS: Record<string, string> = { leader: '리더', user: '사용자', auditor: '감사자' };
const AUTH_CLASS: Record<string, string> = { leader: 'auth-badge-leader', user: 'auth-badge-user', auditor: 'auth-badge-auditor' };
const AUTH_DESC: Record<string, string> = { leader: 'Leader (관리자)', user: 'User (일반 사용자)', auditor: 'Auditor (감사자)' };

interface SlackChannel {
  id: string;
  name: string;
  topic: string;
}

interface SlackStatus {
  connected: boolean;
  workspace: string | null;
  channel: string | null;       // 채널 ID
  channelName: string | null;   // 채널 표시명
  notifyEnabled: boolean;
}

function getSessionExpiry(): string {
  const token = localStorage.getItem('dndn-access-token');
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1] ?? ''));
      if (payload.exp) {
        const d = new Date(payload.exp * 1000);
        return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      }
    } catch { /* invalid token */ }
  }
  return '-';
}

export function MyPage() {
  const session = useSession();
  const [slack, setSlack] = useState<SlackStatus | null>(null);
  const [channels, setChannels] = useState<SlackChannel[]>([]);
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (avatarUrl) URL.revokeObjectURL(avatarUrl);
    setAvatarUrl(URL.createObjectURL(file));
  };

  useEffect(() => {
    return () => { if (avatarUrl) URL.revokeObjectURL(avatarUrl); };
  }, [avatarUrl]);

  // Slack 연동 상태 로드
  useEffect(() => {
    apiFetch<{ success: boolean; data: SlackStatus }>('/slack/status')
      .then((res) => setSlack(res.data))
      .catch(() => setSlack({ connected: false, workspace: null, channel: null, channelName: null, notifyEnabled: true }));
  }, []);

  // Slack OAuth 팝업 + localStorage 이벤트 처리
  const handleSlackConnect = useCallback(async () => {
    if (saving) return;
    setSaving(true);
    try {
      const res = await apiFetch<{ success: boolean; data: { authorizeUrl: string; state: string } }>('/slack/auth');
      localStorage.removeItem('slack-oauth-result');
      const popup = window.open(res.data.authorizeUrl, 'slack-oauth', 'width=600,height=700');
      if (!popup) { setSaving(false); return; }

      const onStorage = async (e: StorageEvent) => {
        if (e.key !== 'slack-oauth-result' || !e.newValue) return;
        window.removeEventListener('storage', onStorage);
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        localStorage.removeItem('slack-oauth-result');

        try {
          const result = JSON.parse(e.newValue);
          if (!result.error) {
            const status = await apiFetch<{ success: boolean; data: SlackStatus }>('/slack/status');
            setSlack(status.data);
          }
        } catch { /* ignore */ } finally {
          setSaving(false);
        }
      };
      window.addEventListener('storage', onStorage);

      let pollTimer: ReturnType<typeof setInterval> | null = setInterval(() => {
        if (popup?.closed) {
          if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
          setTimeout(async () => {
            window.removeEventListener('storage', onStorage);
            const stored = localStorage.getItem('slack-oauth-result');
            if (stored) {
              localStorage.removeItem('slack-oauth-result');
            }
            try {
              const status = await apiFetch<{ success: boolean; data: SlackStatus }>('/slack/status');
              setSlack(status.data);
            } catch { /* ignore */ }
            setSaving(false);
          }, 1500);
        }
      }, 1000);
    } catch {
      setSaving(false);
    }
  }, [saving]);

  const handleDisconnect = useCallback(async () => {
    if (saving) return;
    setSaving(true);
    try {
      await apiFetch('/slack/disconnect', { method: 'DELETE' });
      setSlack({ connected: false, workspace: null, channel: null, channelName: null, notifyEnabled: true });
    } catch { /* ignore */ } finally {
      setSaving(false);
    }
  }, [saving]);

  const handleNotifyToggle = useCallback(async () => {
    if (!slack || saving) return;
    setSaving(true);
    try {
      const res = await apiFetch<{ success: boolean; data: SlackStatus }>(
        '/slack/settings',
        { method: 'PATCH', body: JSON.stringify({ notifyEnabled: !slack.notifyEnabled }) },
      );
      setSlack(res.data);
    } catch { /* ignore */ } finally {
      setSaving(false);
    }
  }, [slack, saving]);

  const handleChannelChange = useCallback(async (channelId: string, channelName: string) => {
    if (!slack || saving) return;
    setSaving(true);
    setPickerOpen(false);
    try {
      const res = await apiFetch<{ success: boolean; data: SlackStatus }>(
        '/slack/settings',
        { method: 'PATCH', body: JSON.stringify({ channel: channelId, channelName }) },
      );
      setSlack(res.data);
    } catch { /* ignore */ } finally {
      setSaving(false);
    }
  }, [slack, saving]);

  return (
    <div className="mypage-page">
    <div className="page-content">

      {/* 프로필 + 계정 정보 */}
      <div className="info-card profile-card">
        <div className="profile-section">
          <div className="avatar-wrap">
            <div className="avatar" style={avatarUrl ? {} : session.company.logoUrl ? { background: 'var(--bg-alt)', border: '1px solid var(--border)' } : undefined}>
              {avatarUrl ? (
                <img src={avatarUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }} />
              ) : session.company.logoUrl ? (
                <img src={session.company.logoUrl} alt="" style={{ width: 52, height: 52, objectFit: 'contain' }} />
              ) : (
                <span>{session.name.charAt(0)}</span>
              )}
            </div>
            <button className="avatar-edit-btn" onClick={() => fileInputRef.current?.click()} title="프로필 이미지 변경">
              <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 2.5l2 2L5 11H3V9l6.5-6.5z"/></svg>
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleAvatarChange} />
          </div>
          <div className="banner-info">
            <div className="banner-name-row">
              <span>{session.name}</span>
              <span className={`auth-badge ${AUTH_CLASS[session.auth] || 'auth-badge-user'}`}>
                {AUTH_LABELS[session.auth] || session.auth}
              </span>
            </div>
            <div className="banner-role">{session.position || session.role}</div>
            <div className="banner-company">{session.company.name}</div>
          </div>
        </div>
        <InfoRow label="계정 ID" value={session.id} />
        <InfoRow label="이메일" value={session.email} />
        <InfoRow label="권한 그룹" value={AUTH_DESC[session.auth] || session.auth} />
        <InfoRow label="가입일" value={session.createdAt ?? '-'} />
      </div>

      {/* 보안 및 세션 */}
      <div className="info-card security-section">
        <div className="info-card-header">보안 및 세션</div>
        <div className="security-grid">
          <div className="security-item">
            <span className="security-label">세션 만료</span>
            <span className="security-value">{getSessionExpiry()}</span>
          </div>
          <div className="security-item">
            <span className="security-label">인증 방식</span>
            <span className="security-value">Amazon Cognito</span>
          </div>
        </div>
      </div>

      {/* 연동 설정 */}
      <div className="info-card integration-section">
        <div className="info-card-header">연동 설정</div>

        <div className="integration-item">
          <div className="integration-left">
            <div className="integration-logo">
              <svg viewBox="0 0 24 24" width="30" height="30">
                <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52z" fill="#E01E5A"/>
                <path d="M6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z" fill="#E01E5A"/>
                <path d="M8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834z" fill="#36C5F0"/>
                <path d="M8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312z" fill="#36C5F0"/>
                <path d="M18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834z" fill="#2EB67D"/>
                <path d="M17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312z" fill="#2EB67D"/>
                <path d="M15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52z" fill="#ECB22E"/>
                <path d="M15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z" fill="#ECB22E"/>
              </svg>
            </div>
            <div>
              <div className="integration-name">Slack</div>
              <div className={`integration-sub${slack?.connected ? ' connected' : ''}`}>
                {slack?.connected ? `${slack.workspace} 워크스페이스 연동됨` : '미연동'}
              </div>
            </div>
          </div>
          <div className="integration-right">
            {slack?.connected ? (
              <>
                <div className="notif-toggle-wrap">
                  <span className="notif-toggle-label">알림</span>
                  <button
                    className={`notif-toggle-track${slack.notifyEnabled ? ' on' : ''}`}
                    onClick={handleNotifyToggle}
                    disabled={saving}
                    role="switch"
                    aria-checked={slack.notifyEnabled}
                    aria-label="Slack 알림 토글"
                  >
                    <div className="notif-toggle-thumb" />
                  </button>
                </div>
                <button className="btn-slack-disconnect" onClick={handleDisconnect} disabled={saving}>연동 해제</button>
              </>
            ) : (
              <button className="btn-slack-connect" onClick={handleSlackConnect} disabled={saving}>
                <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
                Slack 연동
              </button>
            )}
          </div>
        </div>

        {/* 채널 영역 */}
        {slack?.connected && (
          <>
            <div className="integration-channel-row">
              <span className="info-label" style={{ color: 'var(--text-muted)' }}>알림 채널</span>
              <span className="channel-tag">
                <span className="channel-tag-hash">#</span>{slack.channelName ?? slack.channel ?? '채널 미선택'}
              </span>
              <button className="btn-channel-change" onClick={async () => {
                if (!pickerOpen && channels.length === 0) {
                  setChannelsLoading(true);
                  try {
                    const res = await apiFetch<{ success: boolean; data: SlackChannel[] }>('/slack/channels');
                    setChannels(res.data);
                  } catch { /* ignore */ }
                  setChannelsLoading(false);
                }
                setPickerOpen(!pickerOpen);
              }}>변경</button>
            </div>
            {pickerOpen && (
              <div className="channel-picker">
                <div className="channel-picker-title">알림을 받을 채널을 선택하세요</div>
                {channelsLoading ? (
                  <div className="channel-loading">채널 목록 불러오는 중...</div>
                ) : channels.length === 0 ? (
                  <div className="channel-loading">채널을 찾을 수 없습니다</div>
                ) : (
                  channels.map((ch) => (
                    <button
                      type="button"
                      key={ch.id}
                      className={`channel-option${slack.channel === ch.id ? ' selected' : ''}`}
                      onClick={() => handleChannelChange(ch.id, ch.name)}
                      disabled={saving}
                    >
                      <div className="channel-radio"><div className="channel-radio-dot" /></div>
                      <div className="channel-option-name">#{ch.name} {ch.topic && <span>{ch.topic}</span>}</div>
                    </button>
                  ))
                )}
                <div className="channel-picker-actions">
                  <button className="btn-outline" style={{ fontSize: 12, padding: '6px 14px' }} onClick={() => setPickerOpen(false)}>취소</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

    </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </div>
  );
}
