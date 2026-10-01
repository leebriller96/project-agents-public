---
description: 파이프라인 진행 상태를 보여줍니다 — 단계별·slice별 상태, 열린 리팩토링 요구서, 다음에 실행할 명령.
argument-hint: "(인자 없음)"
---

# /status — 진행 상태

## 절차
1. `config/project.yaml` 과 `workspace/<project>/state.yaml` 을 읽는다. 없으면 무엇을 먼저 해야 하는지 안내(`config` 복사 → `/stage0`).
2. `python tools/status.py` 를 실행해 요약 표를 얻는다 (실패하면 state.yaml 을 직접 읽어 같은 내용을 만든다).
3. `python tools/rr.py list --status open` 으로 열린 RR 을 가져온다.
3-1. `python tools/gate.py oi list --status open` 으로 열린 확인 필요 항목을 가져온다 (pipeline-core §11).
4. 사용자에게 보여준다:
   - 프로젝트명 / 모드 / iteration / 마지막 갱신
   - 공통 단계 표 (stage0·1·2_scaffold·3·5·6·7·8)
   - slice × 단계 매트릭스 (stage2 / stage4 / stage5), blocked 사유
   - 열린 RR 표 (severity 순)
   - **열린 확인 필요 항목 표** (severity·kind·닫을 단계 순). `blocker`·`high` 가 열려 있으면 어느 단계가 닫아야 하는지 명시
   - `slices.yaml` 승인 여부
4-1. `python tools/gate.py trace` 로 추적 체인 끊김 수를 확인해 한 줄로 보여준다.
5. **다음 명령 추천**: `.claude/skills/pipeline-core/SKILL.md` §4 게이트를 기준으로 지금 실행 가능한 명령을 1~3개 제시한다 (예: "order slice 의 stage2 가 done 이므로 `/stage4 order` 가능", "open RR 3건 → `/refactor`").
   여러 단계를 이어서 돌릴 수 있는 상태면 `/run --to <stage> --dry` 를 함께 제안한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
