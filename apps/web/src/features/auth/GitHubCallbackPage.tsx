import { useEffect } from 'react';

/**
 * GitHub OAuth 콜백 페이지.
 * GitHub이 ?code=...&state=... 로 리다이렉트하면
 * opener(팝업을 연 부모 창)에 메시지를 전달하고 닫힌다.
 */
export function GitHubCallbackPage() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (window.opener) {
      window.opener.postMessage({ type: 'github-oauth', code, state }, window.location.origin);
      window.close();
    }
  }, []);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <p>GitHub 인증 처리 중...</p>
    </div>
  );
}
