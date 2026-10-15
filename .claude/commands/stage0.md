---
description: 0단계 준비 — workspace/<project>/00_inputs/ 의 문서·AS-IS 소스를 읽어 PROJECT_BRIEF.md 등 요약 지식을 만듭니다.
argument-hint: "(인자 없음)"
---

# /stage0 — 준비 (Ingest)

## 절차
1. `.claude/skills/pipeline-core/SKILL.md`(핵심)과 절 파일 §1 시작 절차를 수행한다 (config·state 확인, 선행 조건: `workspace/<project>/00_inputs/` 에 파일 1개 이상).
2. `state.yaml → stages.stage0_ingest: in_progress` 기록.
3. `ingest-analyst` 서브에이전트를 호출한다. 전달: `config/project.yaml` 요약(mode, stack, asis 경로), 이미 brief 가 있으면 "갱신 모드" 임을 알린다.
   갱신 모드면 `.claude/skills/stage0-ingest/SKILL.md` §6 을 따르라고 명시하고, 새 입력의 위치(`00_inputs/<차수>/` 또는 개정판 파일명)와 현재 slice 별 stage2·stage4 상태를 함께 전달한다.
   보고에서 `SCOPE_DELTA.md` 의 `done` slice 영향 항목을 확인 필요 항목(`deferred`, target 2)으로 채번한다.
3-1. `mode: migration` 이면 `ingest-analyst` 완료 후 `sql-migrator` 를 `inventory` 작업으로 호출(asis 경로 전달) → `ASIS_SQL_INVENTORY.md`. B 분류(호출·미정의) 는 RR(high, `source_stage: 0`, `target_stage: 2`) 로 만든다.
   데이터소스가 둘 이상이면 `knowledge/DATASOURCES.yaml`(`templates/DATASOURCES.yaml`)도 받고 `python tools/datasources.py validate` 를 통과시킨다(pipeline-core §22). role(main·external·out_of_scope)은 사용자 확인 항목이다.
4. 보고를 받아 `state.yaml` 갱신: `stage0_ingest: done`, `updated_at`, `log` 추가.
4-1. **주소·경로·이름 규칙 결정**(stage0-ingest §3-1, pipeline-core §25): ingest-analyst 가 올린 결정 항목(brownfield 면 `knowledge/TOBE_CONVENTIONS.md` 근거)을
   추천안·대안과 함께 사용자에게 보이고 결정을 받는다. 정해지면 brief §3-1·§12 에 적고 JD 로 남겨 `oi set <id> resolved --jd JD-xxxx`.
   결정이 나기 전에 `/stage1` 승인 요청을 하지 않는다(1단계가 이 규칙으로 slice 마다 `routes` 를 정한다).
5. 사용자에게 보여준다: 입력 인벤토리 요약, 엔티티/화면/API/요구사항 수, (migration) AS-IS 프로그램·테이블·SQL 4분류·공통 클래스 수와 B 목록, **§11 근거 부족·모순 표 전체**, **주소·경로·이름 규칙 결정 항목(추천안·대안)**, brief 경로.
6. 안내: "brief 를 확인·수정한 뒤 `/stage1` 을 실행하세요."

## 완료 처리 (공통 · pipeline-core §9·§11·§12·§26·§26)

1. 서브에이전트 결과 블록은 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_0_<slice>.json` 에 저장해 둔다 — 에이전트에게 JSON 을 따로 저장시키지 않고, 값을 손으로 옮겨 적지 않는다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. `python tools/ingest_result.py --json <그 파일> --stage 0 --slice <id> --name <설명> [--body <본문.md>]` — 확인 필요 항목 채번(OI) → 레포트(`pa-meta`, repo 는 git 실측) → 판단 채번(JD).
   본문에는 판단·미완료·다음 단계만 쓰고, 상세는 에이전트 `report_file` 경로로 대신한다.
3. `python tools/gate.py finalize --stage 0 [--slice <id>]` — 게이트 검사(문제만 출력). **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   `blocker`·`high` 확인 필요 항목은 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
   검사 결과 한 줄을 사용자 보고에 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
