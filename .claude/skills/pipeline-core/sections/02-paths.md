<!-- pipeline-core §2 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 2. 경로

- `target_dir`: `config/project.yaml → project.target_dir`. 이 repo 기준 상대경로면 절대경로로 바꿔 쓴다.
  없으면 만든다. **생성되는 서비스 소스는 반드시 target_dir 안에만 쓴다.** 이 repo 안에는 소스를 두지 않는다.
- target_dir 안의 표준 배치:
  ```
  <target_dir>/
  ├── backend/            # 2·3단계
  ├── frontend/           # 4단계
  ├── db/migration/       # Flyway 등 마이그레이션 (2단계)
  ├── docs/api/<slice>.yaml   # OpenAPI 계약 (2단계 산출, 4단계 소비)
  ├── docs/test/<slice>-scenario.md   # 통합 테스트 시나리오 (5단계)
  └── docs/deliverables/  # 8단계 산출물
  ```
- 파이프라인 메타(brief, slices, 요구서, 레포트, 상태)는 항상 이 repo 의 **`workspace/<project>/`** 에 둔다 (`<project>` = `config/project.yaml → project.name`). 프로젝트가 바뀌면 config 만 바꾸면 되고 이전 프로젝트의 workspace 는 그대로 남는다. `tools/rr.py`·`status.py` 는 config 에서 프로젝트명을 읽어 경로를 정한다. 에이전트에게는 항상 **절대경로**로 전달한다.
