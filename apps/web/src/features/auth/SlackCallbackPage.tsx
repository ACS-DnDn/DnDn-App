import { useEffect, useState } from 'react';
import { apiFetch } from '@/services/api';

/**
 * Slack OAuth 콜백 페이지.
 * 팝업에서 직접 code→token 교환 API를 호출하고,
 * localStorage 이벤트로 부모 창에 결과를 전달한다.
 */
export function SlackCallbackPage() {
  const [msg, setMsg] = useState('Slack 인증 처리 중...');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    const error = params.get('error');

    if (error) {
      setMsg('Slack 인증이 거부되었습니다.');
      localStorage.setItem('slack-oauth-result', JSON.stringify({ error }));
      setTimeout(() => window.close(), 1500);
      return;
    }

    if (!code || !state) {
      window.location.href = '/';
      return;
    }

    (async () => {
      try {
        await apiFetch<{ success: boolean }>(
          `/slack/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
        );
        setMsg('연동 완료! 창을 닫는 중...');
        localStorage.setItem('slack-oauth-result', JSON.stringify({ success: true }));
      } catch {
        setMsg('토큰 교환 실패');
        localStorage.setItem('slack-oauth-result', JSON.stringify({ error: 'exchange_failed' }));
      }
      setTimeout(() => window.close(), 1000);
    })();
  }, []);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <p>{msg}</p>
    </div>
  );
}
