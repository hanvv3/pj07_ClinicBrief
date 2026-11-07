# LangSmith SmithDB 조회 API 전환 — 2026-11-08

사용자가 승인한 범위는 공식 동기 조회 클라이언트 사용, 기존 실행만 읽는 검증 도구, 기존 개발분과 마이그레이션 커밋의 분리다. 원격 push·PR 생성·LangSmith 데이터 쓰기는 이번 검증에 포함하지 않았다.

## 변경

- `brochure/langsmith_reads.py`: 공식 `Langsmith` 클라이언트와 기존 프로젝트/Agent 목적지의 UUID 확인. 명시적 지역 endpoint, 2초 timeout, SDK 자동 재시도 0회.
- `brochure/tracing.py`: v2 단건 조회의 필드 선택과 식별자 확인, URL 응답의 `.url` 처리, 새 NotFound 예외에 대한 기존 제한 재조회, 조회 클라이언트 종료. 기존 정제 기록 전송과 LangGraph 흐름은 유지했다.
- `scripts/verify_langsmith.py`: 기존 실행 ID를 받아 단건·URL·trace 목록을 읽는다. 마지막 조상 ID로 직접 자식 수를 계산해 전체 후손 수와 구분한다. 외부 오류 원문이나 키를 출력하지 않는다.
- `tests/test_tracing.py`, `tests/test_langsmith_verify.py`: 실제 SDK의 오프라인 HTTP transport로 v2 경로·파라미터·예외·리소스 종료를 확인한다. 추적 쓰기는 모의 처리하며 검증 CLI의 요청은 GET만 허용한다.
- 로컬 `.local-data/langgraph-qa/check_cloud.py`: 새 조회 도구를 호출하는 진입점으로 교체했다. 이 파일과 기존 검증 데이터는 계속 Git 제외다.
- 사용 문서와 승인 계획을 보완했다.

## 버전과 검증

조사일 공식 레지스트리 최신 안정판은 LangSmith 0.14.17, LangGraph 1.2.20이며 설치·고정 버전과 같다. 불필요한 버전 변경이나 그래프 재설계는 하지 않았다. 앱은 `requirements.txt`를 사용하고 앱용 의존성 잠금 파일은 없다. GEPA용 별도 잠금 파일은 이번 변경과 무관하다.

- 기준 상태: Python 테스트 222개와 UI 검사 통과 후 `b9eeb3b`로 보존했다.
- 변경 후: 전체 Python 테스트 **228개 통과**. 추적 테스트 32개와 조회 CLI 테스트 3개를 포함한다.
- UI 회귀 검사, JavaScript 구문 검사, 변경 Python 파일의 구문 검사 및 Ruff `F` 검사, `git diff --check` 통과.
- `uv build`로 sdist·wheel 생성 성공. 현재 패키지 설정은 `src/brochure_lander`를 포함하므로, 별도 `brochure` 앱의 실행 검증은 전체 테스트가 담당한다.
- 기존 LangSmith 검증 실행을 새 API로 실제 조회했다. 직접 자식 7개·전체 후손 7개, 검증된 링크를 확인했다. 이 확인은 GET 요청만 사용하며 새 기록을 만들지 않았다.
- 독립 검토에서 추가 문제 없음. 실서버 프로세스를 재시작하거나 새 조사를 실행하지 않았다.

## 재검색 결과

추적·미추적·Git 제외 파일의 실행 코드까지 확인했다. 폐기 SDK 호출은 3곳에서 0곳, 기존 모의 메서드 참조는 6곳에서 0곳이 됐다. 해당 경로를 직접 호출하는 HTTP 코드는 처음부터 없었다. 다른 언어의 SDK 호출이나 폐기된 피드백 수식 호출도 없었다.

남아 있는 `reader.traces.list_runs`는 새 trace 조회 API다. 기존 프로젝트 확인의 예외를 처리하는 `LangSmithError`도 유효하다. 설치된 SDK 안의 구 API 호환 구현과 문서의 과거 설명은 애플리케이션 호출이 아니다.

## 참고 문서와 문서 피드백

- [실행 조회 전환](https://docs.langchain.com/langsmith/smithdb-sdk-migration-runs.md), [검색 전환](https://docs.langchain.com/langsmith/smithdb-sdk-migration-query-runs.md), [예외 전환](https://docs.langchain.com/langsmith/smithdb-sdk-migration.md#exceptions).
- [공식 동기 클라이언트](https://reference.langchain.com/python/langsmith#generated-rest-client), [조회](https://reference.langchain.com/python/langsmith/resources/runs/runs/RunsResource/retrieve_v2), [URL](https://reference.langchain.com/python/langsmith/resources/runs/runs/RunsResource/get_url), [trace 목록](https://reference.langchain.com/python/langsmith/resources/traces/traces/TracesResource/list_runs).
- LangChain 전달용 메모: 조회 전환 가이드의 Python `get_url` 참조 링크(`_openapi_client/resources/runs/RunsResource/get_url`)를 Markdown으로 읽으면 새 리소스 대신 `RunTree.get_url(self) -> str` 문서가 반환된다. 위의 `resources/runs/runs/RunsResource/get_url` 문서는 필요한 `RunGetURLResponse`를 설명한다. 링크 정정을 제안하며 이 피드백을 외부에 게시하지 않았다.
