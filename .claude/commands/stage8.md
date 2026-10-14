---
description: 8단계 산출물 — 파이프라인 결과물을 재가공해 config 에 지정된 SI 산출물(요구사항 추적표, 아키텍처·테이블·API·화면 정의서, 테스트/보안/QA 결과서 등)을 생성합니다.
argument-hint: "[all|<산출물 키>[,<키>...]|package] (기본 all)"
---

# /stage8 — 산출물 작성

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1. 선행: `stage5_integration: done`. 6·7 미완료면 경고만 하고 진행(해당 결과서는 "미수행" 표시).
2. `config/project.yaml → deliverables` 에서 대상 목록 결정 (인자로 키를 주면 그것만).
3. `stages.stage8_deliverables: in_progress` → `deliverable-writer` 호출. 전달: target_dir 절대경로, 대상 목록, 형식, iteration.
4. 보고를 받아 `state.yaml` 갱신 (`done`).
5. 사용자에게: 생성 산출물 표(번호·이름·경로), 원천 없음 목록(어느 단계를 돌려야 하는지), 끊긴 추적 항목 수, open RR 수.
6. 안내: open RR 이 남아 있으면 `/refactor` 후 `/stage8` 재생성 권장.

## package - 납품 소스 패키지

인자가 `package` 이면 산출물 대신 `stage8-deliverables §4` 대로 납품 패키지를 만든다:
1. 납품 기준(브랜치·태그)을 사용자에게 확인한다. `python tools/package_delivery.py --target <target_dir> --ref <기준> --check --rules workspace/<project>/delivery.yaml --cache workspace/<project>/delivery/comment-cache.jsonl --polish-out <폴더>/polish.jsonl`.
2. 코드 불변 검증이 실패하면(종료 코드 4) 규칙이 주석 밖을 건드린 것이다 - 규칙을 좁힌다. 금지어가 남으면(종료 코드 2) 목록을 보고 소스(로그·예외 문구 등)를 RR 로 고치거나 프로젝트 규칙을 더한 뒤 다시 검사한다.
3. 다듬기 대상이 남으면 `comment-polisher` 를 대상 목록·캐시 경로와 함께 부른다(대상이 많으면 경로 묶음으로 나눠 하나씩). 끝나면 1 을 다시 돌려 미처리 0 을 확인한다.
4. 통과하면 `--out <빈 폴더> --require-polish`(납품 브랜치면 `--branch <이름> --worktree <폴더>` 를 더한다)로 만들고, 패키지 폴더에서 빌드(시험 제외)를 돌린다. `<out>.changes.txt` 를 표본 검토한다.
5. 레포트를 남기고 사용자에게 패키지 위치·파일 수·정리 주석 수·다듬기 수·바뀐 Flyway 목록(이미 마이그레이션한 DB 의 repair 안내)·빌드 결과·브랜치 커밋을 보고한다. 저장소 원본은 바꾸지 않는다. 납품 브랜치 push 는 사용자 확인 뒤에만 한다.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 8 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 8 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
3-1. **추적 체인 전수 대조**: `python tools/gate.py trace --strict` 를 실행한다. 끊긴 연결(요구사항 ID 를 인용한 테스트 부재, 계약 파일 부재)이 있으면
   산출물에 "끊긴 추적" 으로 싣고, 8단계에서 메울 수 있는 것(문서 인용 누락)은 메운다. 코드·테스트가 없어서 끊긴 것은 확인 필요 항목으로 남긴다.
4. `python tools/gate.py check --stage 8 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
