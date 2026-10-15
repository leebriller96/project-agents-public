<!-- pipeline-core §16 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 16. 훅에 의한 강제 (`.claude/settings.json`)

지침은 읽히지 않거나 잊힐 수 있으므로 핵심 원칙은 훅이 도구 호출 시점에 막는다. 훅이 막으면 우회하지 말고 원인을 고친다.

| 훅 | 막는 것 | 대응 |
|---|---|---|
| PreToolUse (쓰기·Bash) | 이모지가 든 쓰기 | 텍스트로 바꿔 다시 쓴다 |
| PreToolUse (쓰기) | **공개본 금지어가 든 쓰기** — 이 저장소의 git 에 올라가는 파일에 고객 식별 문자열 (`config/publish-public/rules.yaml` 의 `deny`). gitignore 대상·저장소 밖·규칙 파일 자신은 보지 않는다 | 일반화해서 다시 쓴다(프로젝트명 `demo`·패키지 `com.example`·시스템명은 유형). 실제 이름은 `workspace/` 에만 둔다 |
| PreToolUse (state.yaml) | 게이트를 통과하지 못한 단계·slice 를 `done` 으로 바꾸는 편집 | 레포트·`pa-meta` 를 고쳐 `gate.py check` 통과 후 기록, 아니면 `blocked` |
| PreToolUse (Bash) | Bash 로 state.yaml 에 쓰기(sed·리다이렉션·python 쓰기) | Edit/Write 도구로 고친다 |
| SubagentStop | 파이프라인 에이전트가 `pa-agent-result` 블록 없이·깨진 JSON·필수 키 누락·이모지 포함으로 끝내기, 블록 밖 산문 3000자 초과 | 블록을 보완하거나 상세를 레포트 파일로 옮기고(`report_file`) 다시 끝낸다 |
| SubagentStop (받아들인 뒤) | 막지 않음 — 결과 블록을 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_<단계>_<slice>.json` 에 저장 | 오케스트레이터가 `tools/ingest_result.py --json <파일>` 로 옮긴다 |
| PostToolUse (Bash) | 막지 않음 — 6000자를 넘는 출력을 로그 파일로 빼고 앞부분·오류·실패·결과 요약·끝부분만 보인다(§26) | 더 필요하면 로그를 Grep. 전체가 꼭 필요하면 명령에 `PA_FULL_OUTPUT=1` |

훅은 `python`(또는 `python3`)이 PATH 에 있어야 동작한다. 훅 자체 오류는 작업을 막지 않으며, 게이트·selfcheck·CI 가 2차 방어선이다.
