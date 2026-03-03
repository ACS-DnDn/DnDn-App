/**
 * DnDn Theme Manager
 * - localStorage 키: 'dndn-theme' ('light' | 'dark')
 * - <html class="dark"> 로 다크모드 적용
 * - 모든 페이지에서 공유
 */

// ── 즉시 실행: FOUC 방지 (CSS 로드 전에 클래스 적용)
(function () {
  var t = localStorage.getItem('dndn-theme');
  if (t === 'dark') document.documentElement.classList.add('dark');
})();

// ── 네비 로고 <object> 배경색 동기화
// CSS는 <object> 내부 SVG 브라우징 컨텍스트에 전달되지 않으므로
// contentDocument에 직접 접근해 SVG 루트 배경색을 주입
function syncLogoBackground() {
  var bg = getComputedStyle(document.documentElement).getPropertyValue('--bg-nav').trim();
  document.querySelectorAll('.nav-logo-obj').forEach(function(el) {
    el.style.backgroundColor = bg;
    try {
      if (el.contentDocument && el.contentDocument.documentElement) {
        el.contentDocument.documentElement.style.backgroundColor = bg;
      }
    } catch(e) {}
  });
}

// window load: 모든 리소스(<object> SVG 포함) 로드 완료 후 실행
window.addEventListener('load', syncLogoBackground);

// 각 <object>의 load 이벤트에도 개별 등록 (캐시 환경 대응)
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.nav-logo-obj').forEach(function(el) {
    el.addEventListener('load', syncLogoBackground);
  });
});

// ── 회사 로고 양쪽 테마 이미지 프리로드 (첫 전환 시 깜빡임 방지)
document.addEventListener('DOMContentLoaded', function() {
  if (typeof session !== 'undefined' && session.company) {
    [session.company.logoUrl, session.company.logoDarkUrl].forEach(function(url) {
      if (url) { var img = new Image(); img.src = url; }
    });
  }
});

// ── 회사 로고 이미지 테마 동기화
function syncCompanyLogo() {
  if (typeof session === 'undefined' || !session.company) return;
  var isDark = document.documentElement.classList.contains('dark');
  var src = (isDark && session.company.logoDarkUrl)
    ? session.company.logoDarkUrl
    : session.company.logoUrl;
  if (!src) return;
  document.querySelectorAll('.company-logo, .sidebar-company-logo').forEach(function(el) {
    if (el.src) el.src = src;
  });
}

// ── 테마 토글
function toggleTheme() {
  var isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('dndn-theme', isDark ? 'dark' : 'light');
  syncLogoBackground();
  syncCompanyLogo();
  // 페이지별 추가 업데이트를 위한 이벤트
  document.dispatchEvent(new CustomEvent('themechange', { detail: { dark: isDark } }));
}
