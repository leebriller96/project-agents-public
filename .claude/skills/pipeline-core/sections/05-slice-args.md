<!-- pipeline-core §5 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 5. slice 인자 해석

- `/stage2 order` → 해당 slice 하나.
- `/stage2 order,member` → 나열된 slice.
- `/stage2 all` 또는 인자 없음 → `slices.yaml` 의 모든 slice 중 아직 `done` 이 아닌 것.
- 존재하지 않는 id 면 slices.yaml 의 id 목록을 보여주고 중단.
- `/stage2 claim:review` → slice `claim` 의 unit `review` 하나 (§20). `claim` 처럼 unit 을 지정하지 않으면 그 slice 의 남은 unit 을
  `python tools/slice_units.py order --slice claim` 순서대로 전부 돈 뒤 slice 통합(흐름 테스트·전수 대조)까지 한다.
