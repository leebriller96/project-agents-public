---
description: 2단계 Backend 개발 — (최초 1회 골격 생성 후) slice 별로 Migration→Mapper→Service→API→OpenAPI 계약→단위테스트를 개발합니다. 의존 없는 slice 는 병렬 실행.
argument-hint: "<slice-id>[,<slice-id>...] | <slice-id>:<unit> | all | scaffold | common-port [cr]"
---

# /stage2 — Backend 개발

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1·§4·§5·§6·§7 을 읽고 따른다.
   선행: stage1 `done`, `slices.yaml → approved: true`. 미승인이면 승인 요청 후 종료.
2. **골격**: `stages.stage2_scaffold` 가 `done` 이 아니거나 인자가 `scaffold` 면, 먼저 오케스트레이터가 환경(JDK·빌드 도구·Docker·Node)을 확인해 config 와 불일치를 사용자에게 알리고 (필요 시 config 갱신), 확인된 환경 정보를 에이전트에 전달한다.
   `backend-developer` 를 `scaffold` 작업으로 호출 → 보고 → 빌드·샘플 테스트 통과 시 `stage2_scaffold: done`.
   사용자에게 골격 구조·`CONVENTIONS.md` 요약을 보여준다. 인자가 `scaffold` 였으면 여기서 종료.
2-1. **공통 선행 변환 (mode: migration, pipeline-core §17)**: 골격 다음, 업무 slice 전에 한 번.
   a. 공통 계약(`workspace/<project>/contracts/common-contract.yaml`)이 없으면 `python tools/common_usage.py` → `python tools/common_contract.py init` 을 실행하고,
      `review` 항목·업무 간 교차·단일 업무 공통을 표로 보여 준 뒤 **사람의 검토와 승인**을 요청하고 종료한다(승인은 사람이 직접 실행).
   b. 승인됐고 `stages.stage2_common_port` 가 `done` 이 아니거나 인자가 `common-port` 면: owner=common 인 statement·fragment 가 있으면
      `sql-migrator` 를 `convert common-port` 로 먼저 호출 → `common-porter` 를 `signatures` 로 호출(TO-BE 시그니처·스텁) →
      `behavior-spec-writer` 를 `common-port` 로 호출 → `python tools/spec_lock.py lock --slice common-port` →
      `common-porter` 를 `port` 로 호출 → `backend-reviewer` 로 검토(공통화 관점 §5 체크리스트 병용) → `equivalence-verifier` 를 `common-port` 로 호출.
   c. 게이트: `python tools/gate.py check --stage 2 --slice common-port` (계약 이행 검사 포함) 통과 시 `stage2_common_port: done`, target repo 커밋.
   d. 인자가 `common-port cr` 이면 열린 공통 요청(`common-requests/CR-*.yaml`)만 `common-porter cr` 로 처리한다.
   인자가 `common-port` 였으면 여기서 종료.
3. **대상 slice 결정** (§5): 인자 해석 → 대상 목록. 각 slice 의 `depends_on` 이 모두 `stage2_backend: done` 인지 확인. 아니면 그 slice 는 대상에서 빼고 사유를 알린다.
   `hold: true` 인 slice 와 그것에 (전이적으로) 의존하는 slice 는 대상에서 빼고 "근거 대기 hold — <hold_reason>" 으로 알린다(pipeline-core §4). 인자로 직접 지정해도 착수하지 않는다.
   slice 에 `module`·`existing_code` 가 있으면 developer 프롬프트에 모듈 경로(`project.module_paths`)와 수정할 기존 TO-BE 경로를 전달하고 "다른 모듈 코드는 고치지 않는다" 를 명시한다.
4. **웨이브 구성** (§6): `pipeline.parallel` 이 true 면 depends_on 위상 정렬로 웨이브를 만들고, 웨이브 안에서 `max_parallel` 개까지 동시에 실행한다. false 면 priority 순 순차.
5. 웨이브마다:
   a. 대상 slice 들의 `stage2_backend: in_progress` 기록.
   a-1. `mode: migration` 이면 slice 마다 `sql-migrator` 를 `convert <slice>` 로 먼저 호출(병렬 가능) → Mapper·XML·DTO·`<slice>-sql-mapping.md`·Mapper 테스트 → 그 시그니처를 developer 프롬프트에 전달.
        변환 대상은 공통 계약에서 owner=`slice:<id>` 인 statement 뿐이다. owner=common 인 statement 는 공유 Mapper 에 이미 있으므로 호출만 한다.
   a-2. `mode: migration` 이면 developer 프롬프트에 **이 slice 가 쓰는 공통 계약 항목 표**(AS-IS → TO-BE `tobe`, 호출 방식)를 붙이고
        "공통은 호출만, 복제·수정 금지, 계약에 없으면 공통 요청(CR)" 을 명시한다 (`COMMON_USAGE.yaml` 의 used_by 로 추린다).
   b. `backend-developer` 를 slice 마다 호출 (병렬이면 한 메시지에서 여러 Agent 호출). 전달: `slice <id>`, target_dir 절대경로, 프로필 이름, depends_on slice 의 계약 경로.
      **`verification.locked_spec` 이 `off` 가 아니면 b 를 셋으로 나눈다 (pipeline-core §18)**:
      b-1. `backend-developer` 를 `contract <slice>` 로 호출 — OpenAPI 계약·시그니처·스텁까지만.
      b-2. `behavior-spec-writer` 를 `slice <id>` 로 호출 — 전달: 계약 경로, 시그니처 파일, AS-IS 동작 계약 행, 요구사항 ID. (TO-BE 구현 본문 전달 금지)
      b-3. 오케스트레이터가 `python tools/spec_lock.py lock --slice <id>` 로 잠근다.
      b-4. `backend-developer` 를 `implement <slice>` 로 호출 — 잠긴 spec 경로와 테스트 수를 전달하고 "spec 은 고치지 않는다" 를 명시.
   c. 각 보고를 받은 뒤 `backend-reviewer` 를 slice 마다 호출 (병렬 가능). 전달: `slice <id>`, target_dir, 프로필, developer 보고 전문.
   c-1. reviewer PASS 후 `equivalence-verifier` 를 slice 마다 호출(병렬 가능) — spec 독립 재실행·결함 주입 표본. 만든 RR 은 같은 웨이브 안에서 developer 가 반영한다.
   d. reviewer 가 FAIL 이면 지적 목록을 붙여 `backend-developer` 를 다시 호출 (최대 2회). 여전히 FAIL 이면 `blocked` + `blocked_reason` 에 잔여 지적.
   e. `state.yaml` 갱신 (`done`|`blocked`, log). reviewer 의 medium/low 지적은 RR 로 남길지 판단: 다음 단계에 영향 주는 것만 `python tools/rr.py new` 로 생성(`source_stage: 2`). 단, **웨이브 게이트에 걸리는 것**(예: `-Pmysql` 에서만 깨지는 테스트 이식성, 원자성 미증명)은 severity 와 무관하게 같은 단계에서 developer 가 수정한다.
5-U. **unit 으로 나눈 slice** (slices.yaml 에 `units` 가 있는 slice · pipeline-core §20): 그 slice 는 5 의 a~e 를 **unit 마다** 순서대로 돈다.
   a. 순서: `python tools/slice_units.py order --slice <id>` (core 먼저). (migration) 배정 행렬이 없거나 AS-IS·slices.yaml 이 바뀌었으면 `python tools/slice_units.py matrix --slice <id>` 를 먼저 돈다.
   b. unit 마다: `slices.<id>.units.<unit>.stage2_backend: in_progress` → sql-migrator `convert <id> unit <unit>` → developer `contract <id> unit <unit>` →
      behavior-spec-writer `slice <id> unit <unit>` → `spec_lock.py lock --slice <id>` → developer `implement <id> unit <unit>` → reviewer → equivalence-verifier.
      전달: unit 배정(`knowledge/units/<id>.yaml` 의 `assignment.<unit>`), unit 의 API·화면·상태 전이, 앞 unit 들의 계약 경로, "core 는 호출만".
   c. unit 레포트 `<ts>_stage2_<id>_unit-<unit>_backend.md` (pa-meta `unit`·`asis_covered`) → `python tools/gate.py check --stage 2 --slice <id> --unit <unit>` 통과 시 그 unit 만 `done`.
      unit 이 "core 보강 필요" 로 멈추면 core unit 을 다시 돌리고(끝난 unit 의 테스트 재실행) 이어 간다.
   d. **slice 통합**: 모든 unit `done` 후 behavior-spec-writer 로 흐름 테스트(flows, flow id 인용) → 잠금 → 전체 테스트 1회 → reviewer(통합 관점) →
      slice 레포트(`gate.py template --stage 2 --slice <id>` 에 `suite: flow` 게이트가 들어 있다) → `gate.py check --stage 2 --slice <id>` 가 모든 unit 완료·흐름 테스트·AS-IS 전수 대조를
      통과해야 `stage2_backend: done`.
   e. 같은 slice 의 unit 은 병렬로 돌리지 않는다(`slicing.unit_parallel`). 다른 slice 와는 웨이브 규칙대로 병렬 가능하다. 인자 `<slice>:<unit>` 이면 그 unit 하나만(선행 unit `done` 필요).
5-0. 웨이브 종료 후 열린 공통 요청(CR)이 있으면 다음 웨이브 전에 `common-porter cr` 로 처리하고, CR 때문에 `blocked` 된 기능을 가진 slice 를 다시 돌린다.
5-1. 웨이브 종료 후 reviewer 지적 중 "규칙 부재·규칙 신설로 인한 것"(예: URL 파라미터 정규화, 검증 규칙 테스트 누락)은 같은 웨이브의 **다른 slice 에도 해당하는지** 오케스트레이터가 grep 으로 확인하고, 해당하면 slice 별 RR 을 함께 만든다. 프로필 규칙을 갱신했다면 다음 웨이브 developer 프롬프트에 명시한다.
6. 사용자에게 보여준다: slice 별 결과 표(상태·테이블 수·API 수·테스트 수·reviewer 결과), blocked 사유, 근거 부족 항목, 공통 후보 수, 레포트 경로.
7. 안내: 남은 slice 가 있으면 `/stage2 <다음>`, 모두 끝났으면 `/stage3` (공통화) 또는 `/stage4 <slice>`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 2 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 2 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
4. `python tools/gate.py check --stage 2 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
