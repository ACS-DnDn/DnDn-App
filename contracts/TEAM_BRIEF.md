# 팀 공유용 30초 설명 (복붙)

`contracts/`는 DnDn 내부의 **데이터 계약서(Contract)** 입니다.

- **A(Collector/Normalizer)** 가 만들어서 내보내는 결과물:
  - `canonical.json` (WEEKLY/주간)
  - `event.json` (EVENT/이벤트)
- **B(Report Builder)** 는 결과 JSON을 **스키마(JSON Schema)로 먼저 검증**하고(통과한 것만 신뢰),
  `resources[]` 중심으로 보고서(docx/html)를 생성합니다.
- **C/D** 는 Worker 실행 요청을 보낼 때 `payload/job_payload.schema.json` 형식(payload)을 따라 호출합니다.

핵심 규칙
- `collection_status`에 **OK / NA / FAILED**를 표준화해서 남깁니다.
  - **NA**: 정상인데 “원천적으로 수집 불가/데이터 없음” (예: 서비스 꺼짐, 기간 내 데이터 없음)
  - **FAILED**: 원래 돼야 하는데 “에러로 실패” (예: AssumeRole 실패, API 호출 실패)
- EVENT는 `meta.trigger`가 **필수**입니다(왜 실행됐는지 “접수증” 역할).
- 신규 기능(Trusted Advisor 벤치마킹/추가 체크)은 가능한 한 `extensions.*` 아래로 추가해서
  스키마 변경을 최소화합니다.
