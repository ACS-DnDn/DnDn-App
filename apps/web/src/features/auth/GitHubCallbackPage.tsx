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

    // GitHub COOP 헤더로 인해 window.opener가 null이 될 수 있어 BroadcastChannel 사용
    const bc = new BroadcastChannel('github-oauth');
    if (error) {
      bc.postMessage({ type: 'github-oauth', error, errorDescription: errorDesc });
    } else if (code && state) {
      bc.postMessage({ type: 'github-oauth', code, state });
    } else {
      // 직접 접근 — 메인 페이지로 이동
      bc.close();
      window.location.href = '/';
      return;
    }
    // 메시지 전달 완료 후 닫기
    setTimeout(() => {
      bc.close();
      window.close();
    }, 500);
  }, []);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <p>GitHub 인증 처리 중...</p>
    </div>
  );
}
