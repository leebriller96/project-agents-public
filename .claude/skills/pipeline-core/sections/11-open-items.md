<!-- pipeline-core §11 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 11. 확인 필요 항목 (open item)

RR 은 "고쳐야 할 결함"이고, open item 은 **"아직 확인·결정되지 않은 것"** 이다.
레포트 산문에만 적힌 "확인 필요" 는 다음 단계로 넘어가면서 사라진다(실측: notice-admin §8, F-306).
그래서 다음 여섯 가지는 반드시 `workspace/<project>/open-items.yaml` 에 채번해 남긴다.

| kind | 예 |
|---|---|
| `evidence_gap` | 받은 문서에 **그 내용이 없는** 것 (미수령·미작성) — brief §11 근거 부족이 그 단계에서 결정을 막은 것 |
| `contradiction` | 받은 문서 **둘 이상이 서로 다른 것** (어느 쪽이 정본인지 정해야 진행된다) |
| `decision` | 문서는 멀쩡한데 **사람이 골라야** 하는 것 — 차수 포함 여부·설계 선택 (brief §12 후보) |
| `unverified` | 구현은 했으나 그 단계의 테스트로는 도달·증명 불가 (MockMvc 로는 못 보는 서블릿 경로 등) |
| `risk` | 지금은 괜찮지만 조건이 바뀌면 깨지는 것 |
| `deferred` | 뒤 단계로 의도적으로 미룬 것 |

- 채번: `python tools/gate.py oi new --stage <N> --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "파일:라인" --target <닫을 단계> [--axis <축>] [--owner <에이전트>]`
- **항목이 여러 건이면** 서브에이전트 보고를 레포트 `pa-meta.open_items` 에 그대로 옮긴 뒤
  `python tools/gate.py oi import --report <레포트> --write` 로 **일괄 채번**한다 (레포트의 id 까지 도구가 채운다).
  `ingest_result.py` 와 `gate.py finalize` 가 id 없는 항목이 있으면 이것을 먼저 한다.
  0단계에서 51건이 나온 실측 — 한 건씩 부르는 것은 규모에서 불가능하다.
- 레포트 `pa-meta.open_items[]` 에 같은 id 로 싣는다. 도구가 파일과 대조한다.
- **RR 전환을 요구하는 것은 `unverified`·`risk` 이고 단계가 2 이상일 때뿐이다.** RR 은 "이미 있는 코드의 결함" 을 고치라는 요구이므로
  0·1단계에는 만들 대상이 없다. `blocker`·`high` 라도 `decision`·`evidence_gap`·`deferred` 는
  **`target_stage` 로 예약**되어 있으면 열린 채 넘어갈 수 있다(도구가 WARN 으로 추적한다).
- **`evidence_gap` 과 `contradiction` 을 섞지 않는다.** 둘은 해소 경로가 다르다 — 없는 것은 **발주처에 받아야** 하고(기다림),
  다른 것은 **어느 쪽이 정본인지 정하면** 바로 진행된다(결정). 섞어 두면 "지금 결정하면 풀리는 것" 이 "기다려야 하는 것" 사이에 묻혀
  사람에게 올릴 목록을 만들 때마다 손으로 골라내야 한다(실측: 0단계가 낸 60건에서 상충 3건을 `decision` 으로 올려 그 일이 생겼다).
  0단계는 상충을 발견해도 **어느 쪽이 맞는지 정하지 않는다** — 양쪽 근거와 각각을 택했을 때의 영향을 적고 `contradiction` 으로 올린다.
  `resolved` 로 닫을 때는 `decision` 과 같이 판단 기록(JD) 연결이 필요하다 — 문서 둘이 다를 때 어느 쪽을 택했는지가 가장 되돌아보기 쉬운 판단이다.
  2단계 이후의 `unverified`·`risk` 가 `blocker`·`high` 면 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는
  사람 승인(`accepted`) 없이 그 단계를 `done` 으로 끝낼 수 없다.
  게이트는 통과했지만 미확인이 남았으면 레포트 `result` 는 `done_with_gaps` 다.
- `target_stage` 가 자기 단계인 항목은 착수 시 `oi list --target <N>` 으로 확인하고, 처리하면 `resolved`,
  못 했으면 레포트에 다시 싣는다 (도구가 누락을 WARN 으로 알린다).
- **이미 채번된 항목을 레포트에 다시 싣는 것은 중복 채번이 아니다.** 레포트 `pa-meta.open_items` 는 "이번 단계가 책임지는 항목 목록" 이고,
  id 가 있는 항목은 도구가 채번하지 않고 **대조만** 한다(`oi import`·`ingest_result` 가 id 있는 항목을 건너뛴다). 정본은 `open-items.yaml` 이다.
  오케스트레이터가 서브에이전트에게 "앞 단계가 채번한 것은 다시 올리지 마라" 고 지시하면 추적이 끊기고 게이트가 WARN 을 낸다
  (실측: 1단계에서 그 지시를 해 9건이 레포트에서 빠졌고, 게이트가 맞았다 — 지시를 되돌려 열린 채로 실어 넣었다).
- **그 단계가 닫을 수 없고 사람 결정을 받아야 하는 항목은 `--target 0`(사람 결정 대기)으로 재예약한다.**
  `oi set <id> open --target 0` 으로 바꾸고 승인 게이트에 한 묶음으로 올린다. 자기 단계 번호를 그대로 두면 "그 단계가 처리하지 못한 것" 으로만 보인다.
- `accepted` 는 사람만 지정하고 `approved_by`·`expiry`(YYYY-MM-DD)가 필요하다. 만료된 승인은 FAIL 이다.
- `decision` 항목을 `resolved` 로 닫을 때는 그 결정을 판단 기록으로 남기고 연결한다: `oi set <id> resolved --jd JD-xxxx` (§21). 연결 없이는 도구가 거부한다.
