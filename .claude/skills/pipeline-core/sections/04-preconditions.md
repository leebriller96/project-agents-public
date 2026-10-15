<!-- pipeline-core §4 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 4. 선행 조건 (게이트)

| 명령 | 선행 조건 |
|---|---|
| /stage0 | `workspace/<project>/00_inputs/` 에 파일이 1개 이상 |
| /stage1 | stage0 `done` |
| /stage2 `<slice>` | stage1 `done` **and** `slices.yaml → approved: true`; 골격(stage2_scaffold) 미완료면 먼저 골격 수행; `depends_on` slice 의 stage2 가 `done`; **(migration) 공통 계약 승인 + `stage2_common_port: done`** (§17) |
| /stage2 common-port | (migration) 골격 `done` **and** 공통 계약 `approved: true` |
| /stage2 `<slice>:<unit>` | 위 slice 조건 **and** 그 unit 의 `depends_on` unit 이 `done` (§20). slice 에 `units` 가 있으면 slice 는 unit 순서대로만 진행한다 |
| /stage3 | stage2 가 `done` 인 slice 가 1개 이상 |
| /stage4 `<slice>` | 해당 slice 의 stage2 `done` (OpenAPI 계약 존재); `depends_on` slice 의 stage4 `done` |
| /stage5 | 해당 slice 의 stage2·stage4 `done` |
| /stage6, /stage7 | stage5 가 `done` 인 slice 가 1개 이상 (전체 완료 권장) |
| /stage8 | stage5 `done`; 6·7은 권장 |
| /refactor | open 요구서 1개 이상 |

**착수 보류(hold)**: slices.yaml 에서 `hold: true`(사유는 `hold_reason`)인 slice 는 근거가 모자라 착수를 미룬 것이다.
slices 승인과 공통 사용 행렬·공통 계약 계산에는 포함되지만(그 slice 가 쓸 공통도 미리 확정한다), /stage2·/stage4·/run 의 착수 대상에서는 빠진다.
그 slice 에 `depends_on` 으로 (전이적으로) 걸린 slice 도 함께 빠진다. `gate.py plan` 은 이들을 "근거 대기 hold" 로 따로 보여 주고
멈춤 사유로 세지 않는다(나머지는 진행). hold slice 의 2·4단계 완료 기록은 gate `slice-scope` 가 차단한다. hold 해제는 근거를 확보한 뒤 사람이 slices.yaml 을 고쳐 승인한다.

**완료 조건 (2·3·4단계)**: `pipeline.gate` 설정에 따라 빌드·단위테스트가 통과해야 `done`. 실패하면 `blocked` + `blocked_reason` 기록.
게이트 통과 여부는 **말이 아니라 증거로 남긴다** — 레포트 `pa-meta` 의 `gates[]` 에 명령·종료 코드·테스트 개수를 적고
`python tools/gate.py check --stage <N> [--slice <id>]` 가 통과해야 단계를 `done` 으로 기록한다 (§9).
테스트 개수 0 은 통과가 아니다 — 필터가 아무것도 매칭하지 않아도 종료 코드는 0 이 나온다(실측 2회).
통과시키려고 테스트를 지우거나 `@Disabled`/`skip` 하지 않는다.
예외: 환경 조건부 실행(예: Docker 필요한 동시성 테스트 `@EnabledIfSystemProperty`)은 조건·사유가 어노테이션에 있고, 해당 환경(`-Pmysql` 등)에서 실제 실행·통과한 기록이 레포트에 있으면 허용한다.
이런 테스트가 어떤 RR 의 유일한 회귀 근거라면 **그 환경에서의 1회 실행이 게이트에 포함**된다 — 오케스트레이터가 웨이브 종료 시 `-Pmysql` 등으로 실행하고 state log 에 남긴다. 5단계 시나리오에도 같은 조건을 적는다.
