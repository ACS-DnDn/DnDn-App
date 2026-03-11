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
    const error = params.get('error');
    const errorDesc = params.get('error_description');

    if (window.opener) {
      if (error) {
        window.opener.postMessage(
          { type: 'github-oauth', error, errorDescription: errorDesc },
          window.location.origin,
        );
      } else {
        window.opener.postMessage(
          { type: 'github-oauth', code, state },
          window.location.origin,
        );
      }
      window.close();
    } else {
      // 팝업이 아닌 직접 접근 — 메인 페이지로 이동
      window.location.href = '/';
    }
  }, []);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <p>GitHub 인증 처리 중...</p>
    </div>
  );
}
