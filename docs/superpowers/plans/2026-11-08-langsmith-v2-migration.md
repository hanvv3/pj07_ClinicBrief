# LangSmith 조회 API 전환

사용자는 1·2단계 조사 후 다음 세 결정을 승인했다: 공식 동기 Langsmith로 조회 전환, 기존 기록만 읽는 검증 도구, 기존 개발분과 마이그레이션을 별도 로컬 커밋으로 분리. push·PR 생성은 승인하지 않았다.

- 기준 커밋: `b9eeb3b`. 기존 222개 테스트와 UI 검사 통과 후 기록했다. API 키·DB·로컬 설정은 Git 제외.
- 버전: LangSmith 0.14.17, LangGraph 1.2.20은 조사일의 최신 안정 버전. 의존성 핀·그래프 구조는 유지한다. 앱의 uv 프로젝트 전환은 이번 승인 범위가 아니다.
- 읽기: 공식 `Langsmith` 동기 클라이언트, `max_retries=0`, 2초 통신 제한, 명시적 종료. 단건 조회와 URL 생성에 프로젝트/trace ID·반환 필드를 명시한다.
- 목적지: 프로젝트명은 기존 `Client.read_project`, Agent는 새 `sessions.resolve`로 프로젝트 UUID를 확인한다. 기존 기록 전송·정제 방식은 유지한다.
- 오류: 새 예외로 변경하되 NotFound만 기존 횟수로 재조회한다. 조회 실패는 로컬 생성 결과를 바꾸지 않는다.
- 검증 스크립트: 기존 실행 ID를 받아 새 API로 조회한다. 평면 목록에서 마지막 조상 ID를 비교해 직접 자식 수를 센다. 모델 호출·원격 쓰기·DB 쓰기는 하지 않는다.
- 검사: SDK 쓰기를 가로챈 회귀 테스트, 새 HTTP 경로·응답·예외 검사, 전체 테스트/UI/구문/린트/빌드, 기존 원격 실행의 읽기 전용 검증, 폐기 API 재검색.
- 역할: 구현 에이전트는 조회 모듈·추적 연결·추적 테스트, root는 CLI·검증·문서·커밋. 공용 계약은 `create_reader(config)`와 `resolve_project_id(config, reader, client)`다.

진행 기록:
- [x] 승인·기준 커밋
- [x] 앱 조회 경로 전환
- [x] 조회 전용 검증 CLI
- [x] 자동 검사·실제 기존 기록 조회·독립 검토
- [x] 마이그레이션 로컬 커밋 후 3단계 종료

공식 가이드: [조회](https://docs.langchain.com/langsmith/smithdb-sdk-migration-runs.md), [검색](https://docs.langchain.com/langsmith/smithdb-sdk-migration-query-runs.md), [동기 클라이언트](https://reference.langchain.com/python/langsmith#generated-rest-client).

결과: 전체 228개 테스트·UI·Ruff F·구문·패키지 빌드 통과. 실제 기존 원격 기록은 GET으로만 확인했다. 독립 검토와 재검색 통과. 자세한 결과는 [검증 기록](../../verification/langsmith-v2-migration-2026-11-08.md)에 있다.
