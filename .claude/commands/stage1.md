---
description: 1단계 업무 분류 — PROJECT_BRIEF 를 바탕으로 업무 slice 를 나누어 slices.yaml 을 만들고 사람 승인을 요청합니다.
argument-hint: "[reslice] (재분류 시)"
---

# /stage1 — 업무 분류 (Slicing)

인자: `$ARGUMENTS` (`reslice` 면 기존 slices.yaml 을 재분류)

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1 시작 절차 (선행: stage0 `done`).
2. 기존 `workspace/<project>/slices/slices.yaml` 이 있고 인자가 `reslice` 가 아니면: 현재 slice 목록과 approved 상태를 보여주고 "재분류하려면 `/stage1 reslice`" 안내 후 종료.
3. `state.yaml → stages.stage1_slicing: in_progress`.
4. `slice-planner` 서브에이전트 호출. 전달: mode, 재분류 여부, 이미 `done` 인 slice id 목록(있으면).
5. 보고를 받아 `state.yaml` 갱신: `stage1_slicing: done`, `slices` 에 새 slice 들을 `pending` 으로 추가(기존 항목 유지), log.
6. 사용자에게 보여준다: slice 표(id·이름·priority·depends_on·엔티티/화면/API 수), 의존 그래프(텍스트), unassigned 목록, 애매했던 판단.
6-1. **(mode: migration) 공통 사용 행렬·공통 계약 초안**: `python tools/common_usage.py` → `python tools/common_contract.py init`.
   행렬은 slices.yaml 의 `unassigned.asis`(범위 외)·`pre_pipeline`(이전 차수 이관)을 공통에서 빼고, config `project.modules` 가 있으면 항목마다 사용 모듈을 계산한다.
   먼저 확인한다: 범위 외·이전 차수 코드를 slices.yaml 에 적었는가(안 적으면 그 코드와 그것만 쓰는 공통이 공통 선행 변환 대상으로 잡힌다), modules 가 있으면 모든 slice 에 module 이 있는가.
   사용자에게 보여 준다: 공통 메서드 공유/단일 업무/진입점/미사용 수, statement 공유/단일/미사용 수, **범위 제외 건수**(out_of_scope·pre_pipeline, 그중 slice 가 호출한 것),
   **업무 간 교차 사용**(slice 경계 재검토 대상), 해석 불가(동적 SQL id) 목록,
   **review 건수와 일괄 규칙 전 기준 건수**, 이관 안 함(owner: none) 일괄 건수와 목록 파일 경로, (모듈이 있으면) 여러 모듈이 쓰는 항목 — 기본 copy, 전 모듈 공통으로 올릴 후보(인증·권한).
   review 는 slice 소유 namespace 의 미사용 statement 와 slice 소유 클래스의 미사용 public 메서드만 남는다(pipeline-core §17). 업무 간 교차가 많으면 slice 경계를 다시 제안한다(교차는 공통 승격 또는 경계 조정).
6-2. **크기와 unit 분할** (pipeline-core §20): `python tools/slice_units.py measure` 표를 보여 주고, 분할한 slice 는 `python tools/slice_units.py validate` 결과와
   `order` 순서, unit 표(id·kind·상태 전이·API·배정 프로그램 수), flows 를 보여 준다. 분할 후보인데 나누지 않은 slice 와 묶기 후보는 근거와 함께 알린다.
   validate 가 FAIL 이면 승인 요청 전에 slice-planner 로 고친다.
7. **승인 요청**: "`workspace/<project>/slices/slices.yaml` 을 검토하고 `approved: true` 로 바꿔 주세요. 승인 전에는 `/stage2` 가 진행되지 않습니다."
   (migration) 공통 계약도 함께 검토를 요청한다: `review` 항목과 업무로 내릴 항목, (모듈이 있으면) 여러 모듈 항목의 module 을 결정하고 이관 안 함 목록에서 살릴 항목이 있으면 owner 를 바꾼 뒤 **사용자가 직접** `! python tools/common_contract.py approve --by <이름>` 을 실행한다.
8. brief §11 중 **골격·마이그레이션·인증에 영향을 주는 항목**(인증 토큰 전달 방식, 공통코드 seed, 초기 계정, 삭제 방식, FK 정의 등)과 **보안 사양 항목**(초기 비밀번호 정책·변경 기능, 토큰 폐기·세션 무효화, TLS/쿠키 Secure, 레이트 리밋)을 골라 "2단계 전 결정 필요" 로 함께 제시하고, 기본값 제안을 붙인다.
   사용자가 결정(또는 "기본값")하면 `PROJECT_BRIEF.md` **§12 결정 사항** 표에 기록한 뒤 `/stage2` 로 넘어간다.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 1 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 1 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
4. `python tools/gate.py check --stage 1 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
