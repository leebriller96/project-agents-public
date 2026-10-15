<!-- pipeline-core §8 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 8. 리팩토링 요구서 (RR)

- 5·6·7단계와 reviewer 가 다음 단계로 넘길 결함은 **반드시** RR 파일로 남긴다.
- ID 채번: `python tools/rr.py new --title … --slice … --layer … --source N --target N --severity … --evidence "파일:라인" [--evidence …] --description "…" --fix "…"` (기존 최대 번호 +1, 본문까지 한 번에 — 생성 후 YAML 을 정규식·문자열 치환으로 고치지 말 것: 백틱·콜론이 YAML 을 깨뜨림. 고쳐야 하면 yaml 로드→수정→dump). 목록: `python tools/rr.py list [--status open]`.
- `evidence` 는 필수. 근거 없는 요구서는 만들지 않는다.
- 한 요구서에는 한 가지 결함만 담는다. `target_stage`·`target_layer`·`slice` 를 반드시 채운다.
- 상태 전이: `open → in_progress → done | rejected`. `rejected` 는 사람만 지정한다.
