---
description: 특정 업무(slice) 또는 특정 계층/공통만 골라 파이프라인 일부를 다시 돌립니다. 전수 재변환이 아니라 지정한 범위만 처리합니다.
argument-hint: "slice:<id>[,<id>] [unit:<unit>] [stages:2,3,4,5] | common | layer:<backend/mapper|backend/service|frontend|...> [slice:<id>] [사유]"
---

# /rerun — 부분 재실행

파이프라인을 한 바퀴 돌렸다고 프로젝트가 끝나지 않는다. 사용자가 "대출 업무만 다시", "공통 쪽만 다시", "Mapper 계층만 다시" 라고 하면 **그 범위만** 다시 돌린다. 다른 slice·계층은 건드리지 않는다.

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1·§4·§6·§7. 대상 범위와 사유(인자 뒤 자유 문장)를 확인한다. 사유가 없으면 한 줄로 묻는다 — 사유는 developer 프롬프트와 state log 에 들어간다.
2. 범위 해석:
   - `slice:<id>` — 그 slice 의 stage2 → (stage3 는 제외) → stage4 → stage5 를 순서대로. `stages:` 로 일부만(예 `stages:2,5`). 같은 웨이브 병렬 규칙 적용. 다른 slice 는 pending 으로 되돌리지 않는다.
   - `slice:<id> unit:<unit>` — unit 으로 나눈 slice 의 그 unit 만(pipeline-core §20). 그 unit 과 **뒤따르는 unit**(depends_on 으로 이어진 것)의 테스트를 다시 돌리고,
     slice 통합(흐름 테스트·전수 대조)을 다시 통과시킨다. `unit:core` 면 core 를 소비하는 모든 unit 의 테스트를 다시 돈다.
   - `common` — stage3(공통화) 만. 끝나면 **전 slice 의 stage5 를 pending** 으로(공용 변경은 전 slice 에 영향).
   - `layer:<layer>` — 그 계층만: `backend/mapper`(migration 이면 `sql-migrator convert` + Mapper 테스트만), `backend/service`, `backend/api`(+계약 재생성 → FE `gen:api`), `frontend/*`, `db/migration`. `slice:` 와 조합하면 그 slice 의 그 계층만. developer 프롬프트에 "이 계층 파일만 수정, 다른 계층은 읽기만" 을 명시한다.
3. 실행 전 해당 범위의 현재 게이트(빌드·테스트)를 1회 돌려 **기준선**을 기록한다(무엇이 바뀌었는지 비교 근거).
4. 각 단계는 해당 `/stageN` 명령의 절차를 그대로 따른다(developer → reviewer → 게이트 → state → target 커밋 `rerun(<범위>): ...`). 재실행 사유를 developer 에게 전달하고, reviewer 에게는 "기준선 대비 변경 범위가 지정 범위를 벗어나지 않았는지" 를 추가 검토 항목으로 준다.
5. 재실행 후 영향받는 후속 단계 상태를 `/refactor` 7항 규칙대로 되돌린다(예: slice 의 stage2 재실행 → 그 slice stage5 pending, stage6·7 pending).
6. **업그레이드 의무**: 재실행 중 드러난 문제(왜 처음에 못 잡았는지)를 `docs/LESSONS.md` 에 적고 해당 stage 의 스킬/프로필/에이전트/체크리스트를 같은 회차에 갱신한다. 재실행은 결과물보다 이 갱신이 목적이다.
7. 사용자에게: 범위·사유, 기준선 대비 변경(파일·테스트 수), reviewer 결과, 되돌린 후속 단계, 갱신한 스킬 목록.
8. **완료 처리**: 각 단계 레포트에 `pa-meta` 블록을 붙이고 `python tools/gate.py check --stage <N> --slice <id>` 를 통과시킨 뒤에만 state 를 `done` 으로 기록한다 (pipeline-core §9).
   재실행 전 기준선의 테스트 개수와 재실행 후 개수를 `gates[].test_count` 로 비교할 수 있게 둘 다 레포트에 남긴다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
