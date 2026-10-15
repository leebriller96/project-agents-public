<!-- pipeline-core §18 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 18. 기대 동작 테스트 — 코드 작성자와 다른 에이전트가 먼저 쓰고 잠근다

실측된 한계: 특성화 테스트를 코드를 만든 developer 가 직접 썼다. 자기가 이해한 대로 코드를 만들고 같은 이해로 테스트를 쓰면
이해가 틀려도 테스트가 통과한다(자기 확인 편향). 5단계 통합 테스트는 사후라 되돌리는 비용이 크다.

slice(및 common-port) 흐름 — `verification.locked_spec` 이 `required`(migration 권장) 또는 `optional` 일 때:

| 순서 | 무엇 | 누가 |
|---|---|---|
| 1 | **계약 선행**: OpenAPI 계약 + 컨트롤러·서비스·DTO 시그니처 + 본문 없는 스텁 (common-port 는 계약 항목의 `tobe_signature` 스텁) | backend-developer `contract <slice>` (common-porter `signatures`) |
| 2 | **기대 동작 테스트 작성**: 기대 동작의 정본과 인터페이스만 보고. 스텁 대상 실행 시 실패해야 한다(판별력) | behavior-spec-writer |

**기대 동작의 정본은 mode 가 정한다** — `migration` 은 AS-IS 동작 계약(`ASIS_FUNCTION_CONTRACTS.md`) + 요구사항 + AS-IS 원본 소스,
`greenfield` 는 **brief §8-1 업무 규칙·공통코드 + 요구사항 + brief §12 결정 사항**이다. 신규 개발에는 관찰할 AS-IS 가 없으므로
"합리적인 동작" 을 추론해 잠그지 않는다 — 추측을 잠그면 그 추측이 정본이 되어 뒤 단계가 요구사항 대신 테스트를 따른다.
근거 없는 경계·오류 동작은 테스트를 만들지 말고 확인 필요 항목으로 올린다. 오케스트레이터는 호출 프롬프트에 mode 와 그 정본의 경로·행을 함께 싣는다.
| 3 | **잠금**: `python tools/spec_lock.py lock --slice <id>` | 오케스트레이터 |
| 4 | **구현**: 잠긴 spec + 자기 단위테스트 통과까지 | backend-developer `implement <slice>` (common-porter `port`) |
| 5 | 검토 | backend-reviewer |
| 6 | **동등성 검증**: spec 독립 재실행 + 별도 작업 트리에서 결함 주입 표본(판별력) → 불일치는 RR | equivalence-verifier |

규칙:
- spec 위치: backend `…/src/test/java/**/spec/<slice 패키지명>/`, frontend `**/__spec__/<slice>/` (config `verification.spec_globs` 로 변경).
- 잠긴 spec 은 누구도 도구로 고칠 수 없다(훅: 편집·Bash 수정·매니페스트 직접 편집 차단). 테스트가 틀렸다고 판단되면 근거를 RR·deviations 로 남기고,
  잠금 해제는 **사람만**: `! python tools/spec_lock.py unlock --slice <id> --by <이름> --reason "…"` → behavior-spec-writer 수정 → 다시 lock.
- **위임(선택)**: 사용자가 프로젝트 설정 `approvals.delegate_to_agent: true`(`delegated_by: <이름>`)로 위임하면 사람 전용 명령 셋
  (공통 계약 승인·spec 잠금 해제·기준 이미지 승인)을 오케스트레이터가 실행한다. 이때도 규칙은 같다:
  (1) 해제·승인 사유는 AS-IS 원본 근거(파일:라인)로 적는다, (2) `--by <위임자>(위임)` 으로 기록한다,
  (3) 실행할 때마다 사용자에게 한 줄로 보고하고 최종 보고서에 목록으로 남긴다, (4) 서브에이전트는 실행하지 않는다(오케스트레이터만).
  배경(실측): 사용자가 모바일 원격제어로 진행하면 `!` 셸 명령을 칠 수 없어 진행이 멈췄다. 기본값은 위임 없음(사람만).
- 레포트 `pa-meta.gates[]` 에 `suite: "spec"` 인 test 게이트(결과 파일 포함)를 적는다. gate `spec-lock` 이 해시 대조·전체 실행(잠긴 테스트 수 이상)·실패 0 을 검사한다.
- 비용: slice 당 에이전트 호출 +2(spec-writer·verifier). 표본 결함 주입은 기본 3개로 제한한다. 5단계에서 같은 동작을 다시 사후 검증하는 비용과 재작업이 줄어드는 것으로 상쇄한다.
