<!-- pipeline-core §3 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 3. 파일 형식

| 파일 | 형식 | 템플릿 |
|---|---|---|
| `workspace/<project>/state.yaml` | 파이프라인 상태 | `templates/state.yaml` |
| `workspace/<project>/knowledge/PROJECT_BRIEF.md` | 프로젝트 요약 지식 | `templates/PROJECT_BRIEF.md` |
| `workspace/<project>/slices/slices.yaml` | 업무 분류 | `templates/slices.yaml` |
| `workspace/<project>/refactor-requests/RR-NNNN.yaml` | 리팩토링 요구서 | `templates/refactor-request.yaml` |
| `workspace/<project>/open-items.yaml` | 확인 필요 항목(§11) | `templates/open-items.yaml` |
| `workspace/<project>/knowledge/DATASOURCES.yaml` | (migration) 데이터소스 지도(§22) | `templates/DATASOURCES.yaml` |
| `workspace/<project>/reports/*.md` 끝의 `pa-meta` 블록 | 레포트 게이트 메타(§9) | `templates/report-meta.md` |
| `<target_dir>/docs/test/<slice>-scenario.md` | 통합 테스트 시나리오 | `templates/test-scenario.md` |

템플릿의 키를 빼거나 이름을 바꾸지 않는다. 값이 없으면 빈 값으로 둔다.
