# Web

`apps/web`는 DnDn 사용자 웹 프론트엔드입니다. React 19, TypeScript, Vite 기반으로 구성되어 있고, API 서버와 Report 서버를 동시에 사용합니다.

## 실행

```bash
cd apps/web
npm ci
npm run dev
```

- 기본 주소: `http://localhost:3000`
- 프로덕션 빌드:

```bash
npm run build
```

## 백엔드 연결

기본값은 코드에 이미 들어 있습니다.

- `VITE_API_BASE_URL` 기본값: `/api`
- `VITE_REPORT_API_BASE_URL` 기본값: `/report-api`

개발 서버 proxy는 `vite.config.ts` 기준으로 아래처럼 연결됩니다.

- `/api` -> `http://localhost:8000`
- `/report-api` -> `http://localhost:8001`

즉 로컬 개발 시 보통 다음 조합으로 맞추면 됩니다.

- API: `8000`
- Report: `8001`
- Web: `3000`

## 주요 화면

`src/App.tsx` 기준 라우트:

- `/login`
- `/dashboard`
- `/documents`
- `/viewer/:id`
- `/workspace`
- `/workspace/create`
- `/report-settings`
- `/pending`
- `/plan`
- `/mypage`
- `/auth/github/callback`
- `/auth/slack/callback`

## 구조

```text
apps/web/
├── public/
├── src/
│   ├── components/
│   ├── contexts/
│   ├── features/
│   ├── hooks/
│   ├── services/
│   └── styles/
├── package.json
├── vite.config.ts
└── Dockerfile
```

## 참고

- API 호출 공통 유틸: `src/services/api.ts`
- 전역 라우팅: `src/App.tsx`
- 스타일 진입점: `src/styles/index.css`
