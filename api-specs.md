# API 명세서

이 문서는 DnDn 프로젝트의 API 명세서를 정의합니다.

## 작업계획서 API

### 1. 작업계획서 자동 생성

- **Endpoint:** `POST /api/documents/generate`
- **설명:** 사용자가 입력한 정보를 바탕으로 작업계획서 문서 생성을 요청합니다. 실제 문서 생성은 비동기적으로 처리되며, 생성된 문서의 ID와 초기 상태를 반환합니다.

#### 요청 (Request)

**Headers**
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer <user-auth-token>"
}
```

**Body**
```json
{
  "approvers": [
    { "name": "김민준", "rank": "시니어 엔지니어", "type": "결재" },
    { "name": "한동훈", "rank": "부팀장", "type": "협조" }
  ],
  "referenceDocIds": [
    "DOC-2026-001"
  ],
  "target": "EKS production-ng",
  "prompt": "인스턴스 타입을 t3.medium에서 t3.large로 변경하고 싶어. 피크 시간대 CPU 사용률이 너무 높아서 대응해야 해."
}
```

**Body 상세**

| 필드명 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `approvers` | `Array<Object>` | 예 | 결재선에 포함된 사용자 목록 |
| `approvers[].name` | `String` | 예 | 결재자 이름 |
| `approvers[].rank` | `String` | 예 | 결재자 직급 |
| `approvers[].type` | `String` | 예 | 결재 구분 (`결재`, `협조`, `참조`) |
| `referenceDocIds`| `Array<String>` | 아니오 | 선택된 참조 문서들의 ID 목록 |
| `target` | `String` | 예 | 작업 대상 시스템 또는 컴포넌트 |
| `prompt` | `String` | 예 | 작업 내용에 대한 사용자의 자연어 입력 |

#### 응답 (Response)

**성공: `202 Accepted`**
- 문서 생성 요청이 성공적으로 접수되었으며, 백그라운드에서 생성이 시작되었음을 의미합니다.
```json
{
  "documentId": "PLAN-2026-0302-001",
  "status": "GENERATING",
  "message": "문서 생성이 시작되었습니다. 완료되면 알려드립니다."
}
```

**에러: `400 Bad Request`**
- 필수 입력값이 누락되었거나 형식이 잘못된 경우
```json
{
  "errorCode": "INVALID_INPUT",
  "message": "필수 입력 항목(approvers, target, prompt)이 누락되었습니다."
}
```

**에러: `500 Internal Server Error`**
- 서버 내부의 문서 생성 엔진에서 오류가 발생한 경우
```json
{
  "errorCode": "GENERATION_FAILED",
  "message": "문서 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
}
```
