---
description: 4단계 Frontend 개발 — (최초 1회 골격 생성 후) slice 별로 디자인 근거와 OpenAPI 계약만으로 화면·컴포넌트·단위테스트를 개발합니다. 의존 없는 slice 는 병렬 실행.
argument-hint: "<slice-id>[,<slice-id>...] | <slice-id>:<unit> | all | scaffold"
---

# /stage4 — Frontend 개발

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md`(핵심)과 절 파일 §1·§4·§5·§6·§7.
   선행: 대상 slice 의 `stage2_backend: done` 이고 `<target_dir>/docs/api/<slice>.yaml` 존재.
2. **골격**: `stages.stage4_scaffold` 가 없거나 `done` 이 아니거나 인자가 `scaffold` 면
   `frontend-developer` 를 `scaffold` 작업으로 호출 → 빌드·린트·샘플 테스트 통과 시 `stage4_scaffold: done` (state.yaml 에 키 추가). 인자가 `scaffold` 였으면 종료.
3. **대상 slice 결정** (§5): 선행 조건 미충족 slice 는 제외하고 사유 안내. `depends_on` slice 의 `stage4_frontend` 가 `done` 이어야 한다.
4. **웨이브 구성** (§6): stage2 와 동일.
5. 웨이브마다:
   a. `stage4_frontend: in_progress`.
   b. `frontend-developer` 를 slice 마다 호출 (병렬 가능). 전달: `slice <id>`, target_dir 절대경로, 프로필, 계약 경로, 화면 근거 파일 경로(brief §6 에서 추출, migration 이면 레거시 화면 템플릿 경로와 화면 ↔ 템플릿 대응 - stage4-frontend §B-0).
   c. `frontend-reviewer` 호출 (병렬 가능). FAIL 이면 지적 목록·대상 파일·앞 `report_file` 을 주고 developer 를 새로 호출(최대 2회, pipeline-core §26) → 잔여 시 `blocked`. reviewer 에게는 developer 보고 전문 대신 `report_file` 경로를 준다.
   c-1. `verification.visual.enabled` 면 reviewer PASS 후 `ui-verifier` 를 slice 마다 호출 — Playwright 실행, `tools/visual.py pending` 이 고른 이미지만 검토·승인,
        결함은 RR. 병렬 실행 시 slice 마다 BE·FE 포트를 다르게 준다. 보고의 추정 토큰을 레포트 cost 에 옮긴다.
   d. `state.yaml` 갱신. developer 가 만든 RR(계약 부족)은 그대로 두고 사용자에게 알린다.
5-U. **unit 으로 나눈 slice** (pipeline-core §20): stage2 와 같은 순서로 unit 마다 developer → reviewer → (ui-verifier) 를 돌린다(화면이 없는 core 는
   slice 공용 레이아웃·라우트·타입만 만든다). unit 레포트 `<ts>_stage4_<id>_unit-<unit>_frontend.md` → `gate.py check --stage 4 --slice <id> --unit <unit>` 통과 시
   `slices.<id>.units.<unit>.stage4_frontend: done`. 모든 unit 이 끝나면 slice 레포트로 `stage4_frontend: done`.
5-1. 웨이브 종료 후 reviewer 지적 중 "규칙 부재·규칙 신설로 인한 것"(예: URL 파라미터 정규화, 검증 규칙 테스트 누락)은 같은 웨이브의 **다른 slice 에도 해당하는지** 오케스트레이터가 grep 으로 확인하고, 해당하면 slice 별 RR 을 함께 만든다. 프로필 규칙을 갱신했다면 다음 웨이브 developer 프롬프트에 명시한다.
6. 사용자에게: slice 별 결과 표(상태·화면 수·테스트 수·reviewer 결과), 계약 부족 RR 목록, blocked 사유, 레포트 경로.
7. 안내: 계약 부족 RR 이 있으면 `/refactor` 로 BE 보강 후 재실행, 없으면 `/stage5 <slice>`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12·§26·§26)

1. 서브에이전트 결과 블록은 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_4_<slice>.json` 에 저장해 둔다 — 에이전트에게 JSON 을 따로 저장시키지 않고, 값을 손으로 옮겨 적지 않는다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. `python tools/ingest_result.py --json <그 파일> --stage 4 --slice <id> --name <설명> [--body <본문.md>]` — 확인 필요 항목 채번(OI) → 레포트(`pa-meta`, repo 는 git 실측) → 판단 채번(JD).
   본문에는 판단·미완료·다음 단계만 쓰고, 상세는 에이전트 `report_file` 경로로 대신한다.
3. `python tools/gate.py finalize --stage 4 [--slice <id>]` — 게이트 검사(문제만 출력). **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   `blocker`·`high` 확인 필요 항목은 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
   검사 결과 한 줄을 사용자 보고에 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
