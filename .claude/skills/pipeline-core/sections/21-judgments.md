<!-- pipeline-core §21 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 21. 판단 기록 — 판단으로 정한 것은 검증 단계에서 다시 확인한다

실측된 한계: 2·3·4단계 게이트는 "만든 것이 빌드·테스트를 통과하는가" 만 본다. 그런데 사람이나 에이전트가 **판단**으로 정한 것
(대체 매핑, `불필요:` 판정, 폐기·범위 제외, AS-IS 결함 값을 유지할지, 근거가 모호한 곳의 해석, 지시와 다른 결정)은
그 판단 위에서 쓴 테스트도 같은 판단을 전제하므로, 판단이 틀렸으면 테스트까지 함께 틀리고 게이트는 통과한다.
판단은 레포트 산문(`deviations`·"결정" 절)에만 남아 다음 단계로 넘어가면서 사라진다. 그래서 판단은 채번해 두고, 검증 단계가 다시 확인한다.

**무엇이 판단인가**

`kind` 는 **아래 7개 값만** 쓴다. 다른 이름을 쓰면 `judgment.py` 가 거부한다
(실측: 오케스트레이터와 서브에이전트가 각각 `alternative-mapping`·`semantic_diff`·`design_choice` 를 써서 채번이 막혔다 —
표에 뜻만 있고 **값이 없었던 것이 원인**이다).

| `kind` | 판단 (기록한다) | 자동 변환 (기록하지 않는다) |
|---|---|---|
| `decision` | 사람 결정 — decision open item 의 해소, 위임 판단, 승인 시 조건 | 카탈로그(`migration-sql`)의 등가 구문 치환 |
| `substitution` | 대체 매핑 — AS-IS 기능을 2차·공통·프레임워크의 다른 구현으로 대신함, `불필요:` 판정 | 공통 계약대로의 계승(패키지·시그니처 정리만) |
| `semantic` | 의미 차이 — 차이를 수용하거나 보정함(AS-IS 결함 값 유지·정상화, 절단·정렬·타입) | 프로필·`CONVENTIONS.md` 규칙을 그대로 적용한 것 |
| `scope` | 범위 — 폐기(discard)·보류(hold)·이관 안 함·범위 제외 | 근거 문서에 명시된 동작을 그대로 구현한 것 |
| `interpretation` | 해석 — 근거가 모호·부족한 곳에서 한쪽을 골라 구현함 | |
| `design` | 설계 선택 — 대안이 있는 배치·이름·설정 방식 | |
| `deviation` | 지시·계약·규약과 다르게 정한 것(`deviations`) | |

판단인지 애매하면 기록한다. 같은 근거로 같은 결정을 여러 항목에 적용했으면 한 건에 `affects` 로 묶는다.

**흐름**

1. **판단한 단계(0~4)가 기록한다.** 서브에이전트는 `pa-agent-result.judgments[]` 로 보고하고(§12), 오케스트레이터는 레포트 `pa-meta.judgments` 로 옮겨
   `python tools/judgment.py import --report <레포트> --write` 로 채번한다. 사람 결정은 오케스트레이터가 `judgment.py new … --by "사람:<이름>" --oi <OI>` 로
   채번하고 해당 decision open item 을 `oi set <id> resolved --jd <JD>` 로 닫는다.
   - 필수: 누가(`--by`), 무엇을(`summary`), 왜(`rationale`), 어디 적혔나(`source`), **어떻게 다시 확인하나**(`check` — 시나리오 수준으로 구체적으로).
   - `verify_slices`: 판단의 영향을 받는 slice. 공통(common-port)의 판단은 그것을 소비하는 업무 slice 를 적는다 — 소비하는 곳에서 확인해야 한다.
   - `verify_stage`: 기본 5. 단일 slice 의 통합 테스트로 확인할 수 없는 것(여러 slice 를 가로지르는 흐름·운영 설정·외부 연동)은 7.
2. **검증 단계(5·7)가 slice 마다 다시 확인한다.** 착수 시 `python tools/judgment.py list --verify-stage <N> --slice <id>` 로 받아
   판단마다 시나리오를 하나 이상 둔다(5단계 `ITS-<slice>-j<3자리>`). 판단을 믿고 쓴 2단계 spec 을 다시 돌리는 것은 확인이 아니다 —
   **AS-IS 원본과 요구사항을 기준으로** 새로 본다.
3. **기준**(판단 기록의 `criterion` 에 자동으로 적힌다):
   - migration(차세대): AS-IS 기능이 손실 없이 동작하고, 요구사항에 맞게 온전히 개발돼 있다. 증거 2개 — `--asis-evidence`(AS-IS 대조: 같은 입력에 같은 결과·같은 부수효과, 의도된 차이는 brief §12 근거)와 `--req-evidence`(요구사항 충족).
   - 신규 개발: 요구사항에 맞게 온전히 개발돼 있다. 증거 `--req-evidence`.
4. **기록**: `judgment.py verify <JD> --slice <id> --result verified --req-evidence … [--asis-evidence …]`.
   판단이 틀렸거나 기능이 빠졌으면 RR 을 만들고 `--result failed --rr RR-xxxx`. 판단을 고칠 결정이 필요하면 decision open item 도 함께 연다.
5. **면제**는 사람만 한다: `judgment.py set <JD> --waive --approved-by <이름> --note "<사유>"`. 검증 단계를 옮길 때는 `--verify-stage`.

강제: gate `judgments` — 레포트 `judgments[]` 의 id 가 `judgments.yaml` 에 없으면 FAIL, 2·3·4단계에서 `deviations` 가 있는데 `judgments` 가 비었으면 WARN,
**5·6·7·9단계에서 그 단계·그 slice 가 확인하기로 한 판단에 결과가 없으면 FAIL**(9 는 패키지 범위·제외 같은 납품 판단, slice 없이 전체), 8단계에서 미검증 판단(9단계 몫 제외)이 남았으면 WARN.
`status.py` 가 미검증 판단 수를 보여 준다.
