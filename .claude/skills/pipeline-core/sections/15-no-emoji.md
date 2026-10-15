<!-- pipeline-core §15 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 15. 이모지 금지 (전역 · 예외 없음)

- 대상: 생성 소스 전부(코드 주석·Javadoc·로그 문구·예외 메시지·Mapper XML 쿼리 주석·yml/properties 주석·DDL `COMMENT`·
  Flyway 스크립트 주석·테스트 코드와 `@DisplayName`·화면 문구·i18n 리소스), target repo 커밋 메시지, 레포트·산출물·매핑표,
  에이전트 보고(`pa-agent-result` 포함), 이 저장소의 지침·템플릿·도구 출력.
- 대체 표기: 완료/통과 → `완료`, 실패 → `실패`, 주의 → `주의`, 의미 차이 → `[의미차이:태그명]`, 진행 상태 → `[v] [>] [x] [ ]`.
  화살표(→)·가운뎃점(·)·수학 기호(≥ ≠)·괘선은 이모지가 아니므로 쓸 수 있다. 판정 기준은 `tools/_emoji.py` 하나다.
- 테스트에서 이모지 입력 처리를 검증해야 하면 문자를 직접 쓰지 않고 escape(`"\uD83D\uDE00"`, `"\U0001F600"`)로 만든다.
- 외부 도구(external/) 템플릿이나 AS-IS 소스에서 가져온 문구에 이모지가 있으면 텍스트로 바꿔 옮긴다.
  AS-IS 원문 인용이 꼭 필요하면 코드포인트(`U+2705`)로 적는다.
- 강제 장치(어느 한 곳이 뚫려도 다음 단계가 잡는다):
  1. `tools/hooks/guard.py`(PreToolUse) — Write·Edit·MultiEdit·NotebookEdit·Bash 의 새 내용에 이모지가 있으면 **쓰기 자체를 차단**.
     SubagentStop 에서 에이전트 보고의 이모지도 차단.
  2. `tools/quality.py` `NO-EMOJI`(critical) — target 의 코드·설정·SQL·문서 전부. 테스트·리소스도 예외 없고 `quality:ignore` 로도 끌 수 없다.
  3. `gate.py check` `no-emoji` — 모든 단계 레포트. FAIL 이면 단계 완료 불가.
  4. `tools/selfcheck.py`·CI — 이 저장소의 모든 파일, 그리고 모든 에이전트·스킬·명령 파일에 이 조항이 들어 있는지.
