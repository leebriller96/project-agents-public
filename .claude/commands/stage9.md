---
description: 9단계 납품 패키징 — 검증을 끝낸 고정 커밋에서 고객사 납품용 소스 패키지를 만듭니다(주석·문서 정리, AI 산출물 제거, 코드 불변 증명). 저장소 원본은 바꾸지 않습니다.
argument-hint: "[check|<고정 커밋|태그>] (check 는 리허설 - 상태를 바꾸지 않음)"
---

# /stage9 — 납품 패키징

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md`(핵심)과 `.claude/skills/stage9-packaging/SKILL.md`. 선행: `stage7_qa: done`(최종). 리허설(`check`)은 선행 조건 없이 돌린다.
   open RR·`blocker`/`high` 확인 필요 항목이 남아 있으면 최종 패키징 전에 사용자에게 알린다.
2. 기준 커밋을 사용자에게 확인한다(검증을 돌린 고정 커밋·태그). 브랜치 이름만 받으면 그 시점 커밋을 적어 둔다.
3. 검사: `python tools/package_delivery.py --target <target_dir> --ref <기준> --check --rules workspace/<project>/delivery.yaml --cache workspace/<project>/delivery/comment-cache.jsonl --polish-out <폴더>/polish.jsonl`.
   - 코드 불변 검증 실패(종료 코드 4): 규칙이 주석 밖을 건드린 것이다 - 규칙을 좁힌다.
   - 금지어 남음(종료 코드 2): 목록을 보고 소스(로그·예외 문구 등)를 RR 로 고치거나 프로젝트 규칙을 더한 뒤 다시 검사한다.
4. 다듬기 대상이 남으면 `comment-polisher` 를 대상 목록·캐시 경로와 함께 부른다(대상이 많으면 경로 묶음으로 나눠 하나씩). 끝나면 3 을 다시 돌려 미처리 0 을 확인한다.
   인자가 `check` 면 여기서 멈추고 금지어·다듬기 대상 수·AI 산출물 제외 수를 보고한다(상태 변경 없음).
5. `--out <빈 폴더> --require-polish`(납품 브랜치면 `--branch <이름> --worktree <폴더>` 를 더한다)로 만들고, 패키지 폴더에서 빌드(시험 제외)를 돌린다.
   `<out>.changes.txt` 와 남은 문서를 표본 검토한다.
6. 레포트(`<ts>_stage9_package.md`)를 남기고 사용자에게 패키지 위치·파일 수·제외 수(AI 산출물 따로)·정리 주석 수·다듬기 수·바뀐 Flyway 목록(이미 마이그레이션한 DB 의 repair 안내)·빌드 결과·브랜치 커밋을 보고한다.
   사용자가 결과를 보고 준 정리 지시는 규칙(delivery.yaml 또는 rules.yaml)으로 옮기고 다시 만든다. 저장소 원본은 바꾸지 않는다. 납품 브랜치 push 는 사용자 확인 뒤에만 한다.

## 완료 처리 (공통 · pipeline-core §9·§11·§12·§26)

1. 서브에이전트 결과 블록은 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_9_<slice>.json` 에 저장해 둔다 — 값을 손으로 옮겨 적지 않는다.
2. `python tools/ingest_result.py --json <그 파일> --stage 9 --name <설명> [--body <본문.md>]` — 확인 필요 항목 채번(OI) → 레포트(`pa-meta`) → 판단 채번(JD).
3. `python tools/gate.py finalize --stage 9` — 게이트 검사(문제만 출력). 패키지 생성(`package_delivery.py --out`)과 패키지 빌드 게이트가 없으면 FAIL 이다.
   **FAIL 이면 `done` 으로 기록하지 않는다.** 검사 결과 한 줄을 사용자 보고에 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·다듬은 글 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
