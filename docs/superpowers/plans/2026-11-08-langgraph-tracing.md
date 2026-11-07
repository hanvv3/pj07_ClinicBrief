# LangGraph 실행과 조사 기록 구현 계획

**Goal:** 사용자가 선택한 LangGraph로 조사 실행을 이전하고, 병렬 조사 에이전트와 조회 가능한 실행 기록으로 진단 시간을 줄인다.

**Architecture:** LangGraph StateGraph가 독립적인 의원 현장 조사·기술/기관 조사 에이전트를 병렬 실행한다. 합류 후 선정 → 답변 조사 → 작성 → 문장 편집 → 최종 검수를 실행한다. 실제 기록은 시스템이 자동 저장하며 LangSmith와 연결할 수 있고, 사용자 화면과 읽기 전용 MCP 도구가 같은 기록을 조회한다.

**Tech Stack:** Python, LangGraph, LangSmith SDK, SQLite, MCP Python SDK, 기존 웹 화면.

**Spec:** 이번 사용자 요청: 임의 실행 프레임워크를 만들지 않고 LangGraph로 리팩터링; orchestrator와 병렬 subagent로 최적화. 앞선 요청의 tracing과 사용자 로그 조회도 함께 구현.

## 범위와 판단

- 실행은 실제 LangGraph 노드·분기·합류로 구현한다. 기존 순차 함수를 단일 노드로 감싸지 않는다. 노드의 업무 함수는 LangGraph가 호출한다.
- 우선 두 독립 조사만 병렬화한다. 선정·근거·작성·검수 간 의존성은 지킨다. 최대 모델 요청 7회·웹 도구 24회·최대 주제 3개·자동 유료 재시도 없음 유지.
- 병렬 완료 순서에 관계없이 출처 ID와 결과 병합은 안정적이어야 한다. 하나가 실패하면 불완전 결과를 게시하지 않는다.
- 기존 JobRunner는 계정별 요청 중복 방지·작업 admission을 담당한다. 조사 내부 실행은 LangGraph가 담당한다. 실패 후 자동 재개·유료 재실행은 이번에 추가하지 않는다.
- 기록 대상은 공개 조사(research/briefing)다. 회사 자료·비공개 작성/수정 입력은 기록하지 않는다. API 키·인증 헤더·HTTP 오류 본문·모델 내부 reasoning은 저장/전송하지 않는다.
- LangSmith 키가 있으면 설정에 따라 연결하고, 없으면 로컬 기록·화면·도구는 정상 작동한다. 추적 전송 오류 때문에 생성 결과가 사라지지 않게 한다.
- 기존 계정 경계를 유지한다. 개인 조사 기록은 본인만, 공유 브리핑은 로그인한 사용자에게 공개 조사 기록만 제공한다. MCP는 로컬 운영자용 stdio이며 쓰기/재실행 도구를 제공하지 않는다.
- 기존 저장 데이터와 진행 중 작업을 보존하며, 최종 적용 전 활성 작업을 확인한다. 커밋·배포는 범위 밖이다.

## 병렬 작업과 인터페이스

- [x] 그래프: `brochure/insights.py`(필요시 `insight_graph.py`), `tests/test_insights.py`. 기존 `discover(provider, category, history=None, progress=None)` 계약 보존. 실제 StateGraph와 독립 조사 fan-out/fan-in; 병렬성·안정적 출처 연결·실패·상한 검증.
- [x] 추적: `brochure/tracing.py`, `brochure/provider.py`, `tests/test_tracing.py`. `TraceStore(path)`, `research_trace(store, run_id, owner, kind)` context manager 제공. `TraceStore.get(owner,id)`, `.list(owner,limit=20)`, `.delete(owner,id)` 제공. 공급자 경계에서 파싱 전 응답 및 오류를 캡처한다. ContextVar로 요청을 구분하고 병렬 전파를 검증한다.
- [x] 화면: `web/app.js`, `web/style.css`, `tests/test_ui.cjs`. 개인 작업 및 공유 수집의 ‘조사 과정 보기’에서 성공·실패·진행 중 기록을 표시. `GET /api/jobs/{id}/trace`, `GET /api/briefing/trace/{id}` 사용. 저장된 기록 조회는 유료 작업을 시작하지 않는다.
- [x] 통합(root): 의존성 고정, JobRunner context 연결과 삭제 연동, 서버 조회 API/권한, stdio MCP 조회 도구, 문서, 실제 브라우저 확인.

### 기록 응답 계약

`{id, kind, status, started_at, finished_at, duration_ms, error, usage, langsmith_url, calls}`.
`usage`는 `requests,input_tokens,output_tokens,total_tokens`.
각 call은 `{id,name,label,status,started_at,finished_at,duration_ms,model,input_tokens,output_tokens,total_tokens,error,tools,request,response,response_id}`. `request`는 정제된 실제 지시·입력·출력형식 객체, `response`는 실제 응답 객체(비공개 reasoning 제외). `tools`는 API가 제공한 search/open/find 기록이며 `{type,query,url}`. 없는 값은 null/빈 목록. 노출한 길이를 제한했다면 명시한다. API가 제공하지 않는 도구별 시간이나 생각을 만들어 보여주지 않는다.

## 검증과 완료 기준

- [x] 테스트 barrier로 두 조사 노드가 실제 중첩 실행되고 후속 선정은 둘 다 완료된 뒤 시작함을 증명한다. 고정 지연 비교는 순차 합계보다 병렬 최대 지연에 가까운지 확인하되 실서비스 속도 수치로 주장하지 않는다.
- [x] 기존 출처·검수·중복·요청 상한·비공개 입력 분리 회귀 검사, 전체 테스트와 UI 검사.
- [x] 병렬 작업의 로그 혼선·오류 응답 보존·원문 HTML 주입·계정 간 조회·삭제 연동·LangSmith 전송 실패 검사.
- [x] 실패와 성공 기록을 실제 화면에서 확인하고 MCP 도구를 프로토콜로 호출한다. 독립 코드 검토를 거쳐 수정한다.
- [x] LangSmith 연결은 실제 설정 여부와 실제 전송 성공 여부를 분리해서 보고한다. 모의 테스트를 실서비스 전송으로 표현하지 않는다.

## 작업 기록

- 사용자 지시에 따라 LangGraph 채택. 추가 승인 절차 없이 위 범위로 진행.
- 기존 작업 트리에 이전 개선이 있으므로 해당 변경을 보존하며 파일별 소유권을 나눠 작업한다.

- 최종 검증: Python 222개·UI 검사 통과. 실제 LangGraph와 모의 모델의 7단계 기록이 LangSmith에도 7개 하위 실행으로 저장된 것을 재조회했다. [검증 결과](../../verification/langgraph-tracing-2026-11-08.md).
