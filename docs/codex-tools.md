# Codex 개선 도구 적용 기록

2026-11-08. 사용자는 대화 압축 후에도 의도가 유지되도록 세 접근법을 Codex에 적용해 달라고 요청했다. 목적은 지시를 더 많이 따르게 만드는 것이 아니라, 실패에서 배우고 독자에게 자연스럽고 유용한 결과를 만드는 판단을 개선하는 것이다.

## 설치한 것과 쓰임

| 도구 | 설치 방식 | 필요할 때 쓰는 역할 |
|---|---|---|
| Compound Engineering 3.36.1 | 공식 Codex 플러그인, 활성화 | 과거 경험을 참고하고 재사용할 교훈을 남기기 |
| skill-improvement-lab | Anthropic skill-creator를 Codex용으로 조정한 사용자 스킬 | 실제 실패를 분석하고 고정 기준으로 결과 비교하기 |
| gepa-optimize-anything | Codex용 사용자 스킬 + 별도 Python 환경 | 평가 기준이 준비된 뒤 제한된 실험으로 작성 지시 등 개선하기 |

세 도구를 항상 순서대로 실행할 필요는 없다. 간단한 수정에는 간단한 검증이면 충분하다. 이미 정한 방향을 다시 묻거나 모든 작업에 계획·리뷰·기록을 붙이는 용도가 아니다. 기존 Superpowers와 내장 skill-creator는 제거하거나 덮어쓰지 않았다. 프로젝트와 사용자의 구체적인 의도가 일반적인 워크플로보다 우선한다.

설치는 사용자 범위이므로 다른 프로젝트에서도 도구를 사용할 수 있다. 클리닉 브리프의 목적과 교훈은 이 저장소의 AGENTS.md와 learning-notes.md에 둔다. 설치만으로 앱의 생성 프롬프트가 바뀌거나 기본 모델이 재학습되는 것은 아니다.

## 실제 위치와 호출 예

- 공식 플러그인: `~/.codex/plugins/cache/compound-engineering-plugin/compound-engineering/3.36.1/`
- 사용자 스킬: `~/.codex/skills/skill-improvement-lab/`, `~/.codex/skills/gepa-optimize-anything/`
- GEPA 전용 Python: `~/.codex/tools/gepa/.venv/bin/python` (Python 3.12, 앱 환경과 분리)
- 수정·재설치용 스킬 소스: [tools/codex/skills](../tools/codex/skills/)
- GEPA 고정 의존성: [gepa-requirements.lock.txt](../tools/codex/gepa-requirements.lock.txt)

Codex에 자연어로 요청하거나 다음 이름을 사용할 수 있다.

```text
$ce-compound 이번에 확인한 교훈 중 다음 작업에 쓸 내용만 기존 기록에 짧게 반영해줘. mode:non-interactive depth:lightweight
$skill-improvement-lab 합의한 기준으로 기존 결과와 변경 결과를 비교해줘.
$gepa-optimize-anything 평가 자료와 실행 예산을 바탕으로 개선 실험을 준비해줘.
```

실제 스킬 목록에서 플러그인 이름은 `compound-engineering:ce-compound`로 표시된다. 새 스킬은 다음 턴부터 사용 가능하며, 목록에 나타나지 않으면 Codex를 재시작한다.

## 호환 처리와 확인 범위

- Anthropic 스킬은 Claude 전용 실행·설명 최적화 스크립트를 제외하고, 비교 지침과 정적 HTML 리뷰 도구를 유지했다. 동점·둘 다 부적합·근거 부족을 허용하고 실제 사람 피드백을 대신 만들어 넣지 않는다. 포트를 쓰는 기존 프로세스를 종료하던 뷰어 동작도 제거했다.
- GEPA는 Claude subprocess가 필요 없는 `gepa` 엔진으로 연결했다. 전체 부가 패키지 대신 기본 엔진에 필요한 의존성만 설치했다. 실제 모델을 쓰는 실험에는 별도 API 인증과 비용이 필요하며, 이번 설치에서는 시작하지 않았다.
- 두 사용자 스킬의 형식 검증 통과. 리뷰 도구의 익명 A/B 파일 → 정적 HTML 생성과 한국어 보존 확인.
- GEPA는 외부 연결을 차단한 모의 제안자로 후보 생성·평가·선택·최종 확인 자료 채점까지 실행했다. 이 결과는 설치 연결 검증이며 콘텐츠 품질 개선의 증거가 아니다.
- Codex `skills/list`에서 두 사용자 스킬과 `compound-engineering:ce-compound`의 enabled 상태를 확인했다. 검색 오류 0건. 플러그인 목록에서도 installed/enabled 확인.

실제 편집 평가 체계와 서비스 문체 변경은 다음 개발 작업이다. API 키·사용자 DB·실제 비공개 출력은 스킬에 포함하지 않았다.

## 원본과 버전

- [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin): `2921168fc84b4070308a9ef6d115063cf62198cf`, 버전 3.36.1.
- [Anthropic skill-creator](https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator): `2c5958ecac7cee2b583967a2c4981d0f4a75c579`. 조정 내용과 라이선스는 해당 스킬의 references/origin.md와 LICENSE.txt에 보존했다.
- [GEPA](https://github.com/gepa-ai/gepa/tree/cb7674c8b231270134b8e5ea8b9db1a62ed8d081): `cb7674c8b231270134b8e5ea8b9db1a62ed8d081`, 패키지 0.1.4. 스킬과 엔진은 같은 소스 버전에 맞췄다.

재설치 시 공식 플러그인은 Codex의 `plugin marketplace add`와 `plugin add`로 등록한다. 두 사용자 스킬은 저장소의 tools/codex/skills 아래 각 폴더를 사용자 스킬 폴더로 복사한다. 기존 설치가 있다면 내용을 먼저 비교한다. GEPA는 별도 가상환경을 만든 뒤 위 잠금 파일로 설치한다. 버전을 올릴 때는 현재 설치를 무조건 덮어쓰기보다 호환성과 간단한 연결 검증을 먼저 확인한다.
