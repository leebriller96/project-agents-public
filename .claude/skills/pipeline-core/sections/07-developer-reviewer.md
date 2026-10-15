<!-- pipeline-core §7 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 7. developer → reviewer

2·3·4단계는 developer 서브에이전트가 만든 뒤 reviewer 서브에이전트가 검토한다.
- reviewer 는 코드를 고치지 않고 지적 목록을 돌려준다. 지적 한 건의 고정 형식:

  | 필드 | 규칙 |
  |---|---|
  | `id` | `<축약어>-<번호>` (예: `BR-03`) |
  | `severity` | `blocker` \| `high` \| `medium` \| `low` |
  | `confidence` | `confirmed`(실행·대조로 증명) \| `high` \| `medium` \| `low`(정황) — **근거 없이 severity 만 높이지 않는다** |
  | `evidence` | `파일:라인` 또는 실행한 명령·출력. 없으면 지적으로 만들지 않는다 |
  | `impact` | 사용자·데이터·운영에 실제로 무엇이 잘못되는가 |
  | `fix` | 구체적 수정안 |
  | `test_hint` | 이 지적을 닫으려면 **5단계가 무엇을 실측해야 하는가**. `medium`·`low` 로 넘기는 지적에는 필수 |

  `confidence: low` 인데 `severity: blocker` 면 오케스트레이터는 재작업 대신 확인 필요 항목(§11)으로 돌린다.
  `test_hint` 는 5단계 시나리오·7단계 인벤토리의 입력이다 — 여기서 끊기면 "확인 필요" 가 증발한다(실측: notice-admin §8 미인계).
- 오케스트레이터는 `blocker`·`high` 지적을 developer 에게 다시 넘겨 같은 단계 안에서 고친다 (최대 2회).
- 2회 후에도 남으면 `blocked` 로 기록하고 사람에게 보고한다.
- `medium`·`low` 지적 처리: 코드 수정이 필요한 것은 RR(`source_stage` = 현재 단계)로 남기고, 공용 파일·컨벤션 문서 변경은 `common-candidates.md` 로 넘긴다. 같은 단계에서 바로 고치지 않는다 (병렬 slice 와의 충돌·회귀 방지).
- 뒤따르는 slice 에 적용할 교훈(예: `@Pattern` 앵커)은 오케스트레이터가 다음 developer 호출 프롬프트에 명시한다.
- 우선순위: **brief §12 결정 > 골격 `CONVENTIONS.md` > 프로필 > 오케스트레이터 프롬프트의 구현 세부**. 프롬프트가 규약과 충돌하면 developer 는 규약을 따르고 보고에 "지시와 다른 결정" 으로 명시한다.
