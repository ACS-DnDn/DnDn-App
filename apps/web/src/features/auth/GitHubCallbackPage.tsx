import { useEffect, useState } from 'react';
import { apiFetch } from '@/services/api';

/**
 * GitHub OAuth 콜백 페이지.
 * 팝업에서 직접 code→token 교환 API를 호출하고,
 * localStorage 이벤트로 부모 창에 결과를 전달한다.
 */
export function GitHubCallbackPage() {
  const [msg, setMsg] = useState('GitHub 인증 처리 중...');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    const error = params.get('error');

    if (error) {
      setMsg('GitHub 인증이 거부되었습니다.');
      localStorage.setItem('github-oauth-result', JSON.stringify({ error }));
      setTimeout(() => window.close(), 1500);
      return;
    }

    if (!code || !state) {
      window.location.href = '/';
      return;
    }

    // 콜백 페이지에서 직접 token 교환
    (async () => {
      try {
        const res = await apiFetch<{ success: boolean; data: { username: string; connected: boolean } }>(
          `/github/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
        );
        setMsg('연동 완료! 창을 닫는 중...');
        localStorage.setItem('github-oauth-result', JSON.stringify({
          success: true,
          username: res.data.username,
        }));
      } catch {
        setMsg('토큰 교환 실패');
        localStorage.setItem('github-oauth-result', JSON.stringify({ error: 'exchange_failed' }));
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
