<!-- pipeline-core §3 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 3. 파일 형식

| 파일 | 형식 | 템플릿 |
|---|---|---|
| `workspace/<project>/state.yaml` | 파이프라인 상태 — 값은 `python tools/state.py set` 으로만 바꾼다(§1) | `templates/state.yaml` |
| `state.yaml` 의 `slices.<id>.blocked_reason` | `[<라벨>] <사유>` 조각을 ` \| ` 로 잇는다. 라벨은 slice 단계면 단계 키(`stage5_integration`), unit 이면 `unit <id>.<단계 키>`. `state.py` 가 blocked 에서 자기 조각을 쓰고 풀 때 지운다. 라벨 없는 글(사람이 적은 hold 사유)은 도구가 건드리지 않는다 — 손으로 고칠 때 라벨 조각 형식을 지킨다 | (`state.py` 가 쓴다) |
| `workspace/<project>/state-history.jsonl` | 상태 변경 이력(시각 KST·키·이전값·새값·사유·게이트) — `state.py` 가 덧붙인다 | (도구가 만든다) |
| `workspace/<project>/knowledge/PROJECT_BRIEF.md` | 프로젝트 요약 지식 | `templates/PROJECT_BRIEF.md` |
| `workspace/<project>/slices/slices.yaml` | 업무 분류 | `templates/slices.yaml` |
| `workspace/<project>/refactor-requests/RR-NNNN.yaml` | 리팩토링 요구서 | `templates/refactor-request.yaml` |
| `workspace/<project>/open-items.yaml` | 확인 필요 항목(§11) | `templates/open-items.yaml` |
| `workspace/<project>/knowledge/DATASOURCES.yaml` | (migration) 데이터소스 지도(§22) | `templates/DATASOURCES.yaml` |
| `workspace/<project>/reports/*.md` 끝의 `pa-meta` 블록 | 레포트 게이트 메타(§9) | `templates/report-meta.md` |
| `<target_dir>/docs/test/<slice>-scenario.md` | 통합 테스트 시나리오 | `templates/test-scenario.md` |

템플릿의 키를 빼거나 이름을 바꾸지 않는다. 값이 없으면 빈 값으로 둔다.
