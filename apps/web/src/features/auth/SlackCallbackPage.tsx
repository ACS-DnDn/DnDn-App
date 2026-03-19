import { useEffect } from 'react';

/**
 * Slack OAuth 콜백 페이지.
 * Slack이 ?code=...&state=... 로 리다이렉트하면
 * opener(팝업을 연 부모 창)에 메시지를 전달하고 닫힌다.
 */
export function SlackCallbackPage() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    const error = params.get('error');

    const bc = new BroadcastChannel('slack-oauth');
    if (error) {
      bc.postMessage({ type: 'slack-oauth', error });
    } else if (code && state) {
      bc.postMessage({ type: 'slack-oauth', code, state });
    } else {
      bc.close();
      window.location.href = '/';
      return;
    }
    setTimeout(() => {
      bc.close();
      window.close();
    }, 500);
  }, []);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <p>Slack 인증 처리 중...</p>
    </div>
  );
}
