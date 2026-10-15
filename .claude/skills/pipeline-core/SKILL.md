---
name: pipeline-core
description: project-agents 파이프라인의 공통 규칙 — 핵심(모든 명령·에이전트 공통, 결과 블록·토큰 위생)과 절별 상세(sections/ — 설정·상태·slice·RR 형식, 게이트, 병렬, 레포트, 공통 계약, 잠긴 spec, 화면 검증, unit 분할, 판단 기록, 데이터소스, 보고 정직성, brownfield, 화면 주소). 모든 /stageN·/refactor·/status 명령과 에이전트가 가장 먼저 읽는다.
---

# 파이프라인 공통 규칙 (pipeline-core)

이 파일이 **핵심**이다. 모든 명령과 에이전트는 이 파일을 먼저 읽고, 아래 절 목록에서 **자기 작업에 해당하는 절만** `sections/` 에서 읽는다.
"pipeline-core §N" 은 `.claude/skills/pipeline-core/sections/NN-*.md` 를 가리킨다(§12·§26 은 이 파일 안).
전부 읽지 않는 이유는 비용이다 — 읽은 지침은 그 에이전트의 이후 모든 호출에서 다시 읽힌다(§26). 해당 여부가 애매하면 그 절을 읽는다.

## 절 목록

| § | 파일 | 내용 | 읽는 쪽 |
|---|---|---|---|
| 1 | `sections/01-start.md` | 시작 절차 — config·state 읽기, in_progress/done 기록 | 모든 명령(오케스트레이터) |
| 2 | `sections/02-paths.md` | target_dir·workspace 배치 | 명령, 경로가 불분명한 에이전트 |
| 3 | `sections/03-file-formats.md` | state·brief·slices·RR·open-items·pa-meta 템플릿 표 | 해당 파일을 새로 만드는 쪽 |
| 4 | `sections/04-preconditions.md` | 단계별 선행 조건, 완료 조건(게이트·테스트 0건 금지) | 명령 |
| 5 | `sections/05-slice-args.md` | slice·unit 인자 해석 | 명령 |
| 6 | `sections/06-parallel.md` | 웨이브·충돌 방지(소유 파일·포트·마이그레이션 번호)·target repo 커밋 | 명령, 병렬로 도는 developer |
| 7 | `sections/07-developer-reviewer.md` | 지적 고정 형식(id·severity·confidence·evidence·impact·fix·test_hint), 재작업 규칙 | reviewer, 명령 |
| 8 | `sections/08-refactor-request.md` | RR 채번(`rr.py new`)·규칙 | RR 을 만드는 에이전트 |
| 9 | `sections/09-report.md` | 레포트 위치·파일명·pa-meta·gate 검사 항목·비밀 마스킹 | 레포트를 쓰는 쪽 |
| 10 | `sections/10-human-checkpoints.md` | 사람 확인 지점 | 명령 |
| 11 | `sections/11-open-items.md` | 확인 필요 항목(kind·채번·RR 전환 조건) | 명령, 확인 필요 항목을 보고하는 에이전트 |
| 12 | 이 파일 | 에이전트 결과 계약(`pa-agent-result`)·12-1 산출물 먼저 쓰기 | **모두** |
| 13 | `sections/13-model.md` | 모델 배정 기준 | 명령 |
| 14 | `sections/14-axis.md` | 검증 축·판별력 기록(`discrimination`) | 1·5·6·7단계, verifier, 판별력을 기록하는 쪽 |
| 15 | `sections/15-no-emoji.md` | 이모지 금지 전문 (요약은 아래) | 이모지 입력 검증 테스트를 쓰는 쪽 |
| 16 | `sections/16-hooks.md` | 훅이 막는 것과 대응 | 훅에 막혔을 때 |
| 17 | `sections/17-common-contract.md` | (migration) 공통 계약 — 공통은 먼저·한 번에·소비만 | migration 의 명령·developer·reviewer·sql-migrator·common-porter·slice-planner |
| 18 | `sections/18-locked-spec.md` | 잠긴 기대 동작 테스트 흐름 | `contract`·`implement` 작업, spec-writer, reviewer, verifier |
| 19 | `sections/19-visual.md` | 브라우저 화면 검증 역할 분담 | frontend, ui-verifier |
| 20 | `sections/20-units.md` | 큰 slice 의 unit 분할 | unit 작업을 받은 에이전트, slice-planner |
| 21 | `sections/21-judgments.md` | 판단 기록 — `judgments` 의 kind 7종·채번·검증 단계 재확인 | 판단을 기록하는 쪽(판단이 있을 때), 5·6·7단계·verifier, 명령 |
| 22 | `sections/22-datasources.md` | (migration) 여러 데이터소스 — 실행 데이터소스 판정, 외부 테이블 CREATE 금지 | migration 의 ingest·slice-planner·sql-migrator·developer·reviewer·common-porter |
| 23 | `sections/23-honest-report.md` | 보고의 정직성 — 실측으로 걸린 형태와 대응 | 명령, reviewer, RR 을 닫는 쪽 |
| 24 | `sections/24-brownfield.md` | 기존 코드가 많은 저장소에서 검사를 켜는 법 | 명령, 검사 설정을 바꾸는 쪽 |
| 25 | `sections/25-routes.md` | 화면 주소 규칙과 `routes` | ingest(0단계)·slice-planner·frontend·ui-verifier |
| 26 | 이 파일 | 토큰 위생 | **모두** |

## 모두에게 적용되는 핵심 규칙

- 근거(brief·00_inputs·계약) 없는 기능은 만들지 않고 "근거 부족" 으로 남긴다.
- 서비스 소스는 `target_dir` 안에만, 파이프라인 메타는 `workspace/<project>/` 에만 쓴다. 서브에이전트는 `state.yaml` 을 직접 고치지 않는다.
- 빌드·테스트는 실제로 실행하고 결과 파일로 확인한다. 테스트를 지우거나 비활성화해서 통과시키지 않는다. 테스트 0건은 통과가 아니다.
- 실행하지 못한 검증은 `not_executed` 에 이유와 함께 적는다. 통과한 것처럼 쓰지 않는다.
- 훅(§16)이 막으면 우회하지 말고 원인을 고친다.

## 12. 에이전트 결과 계약 (Agent Result)

서브에이전트의 보고가 산문뿐이면 오케스트레이터가 집계·인계에서 항목을 흘린다(실측: RR-0023 admin 몫 증발).
**모든 서브에이전트는 보고의 마지막을 아래 블록으로 끝낸다.** 오케스트레이터는 이 블록만으로
state 갱신·다음 호출 프롬프트·레포트 `pa-meta` 를 만들 수 있어야 한다. 훅이 받아들인 블록을 `reports/agent-results/` 에 저장하고
오케스트레이터는 그 파일을 `tools/ingest_result.py` 로 옮긴다 — 그래서 `stage`·`slice`(unit 작업이면 `unit`)를 반드시 적는다.

````markdown
```json pa-agent-result
{
  "schema": 1,
  "agent": "backend-developer",
  "stage": 2,
  "slice": "notice",
  "attempt": 1,
  "result": "done",
  "gates": [
    {"kind": "build", "command": "…", "exit_code": 0, "executed_at": "2026-09-23 00:20"},
    {"kind": "test", "command": "…", "exit_code": 0, "executed_at": "2026-09-23 00:35",
     "test_count": 226, "failures": 0, "skipped": 0,
     "results": ["server/domain-notice/target/surefire-reports/TEST-*.xml"]}
  ],
  // gates[].kind 는 build·test·lint·typecheck·smoke·scan·other 만 쓴다(그 밖 - static·browser·quality·spec-lock 등 - 은 gate 가 거부).
  //   test·smoke·scan 은 test_count 와 results(JUnit XML 경로)가 있어야 한다. 개수·XML 이 없는 확인(정적 대조·셸 검사·잠금 확인)은 other 로 적고 note 에 결과를 쓴다.
  //   결과 JSON 파일을 따로 저장하면 이 블록과 똑같이 쓴다(open_items·judgments 를 빼지 않는다).
  "changed_files": ["server/domain-notice/src/main/java/…"],
  "open_items": [{"kind": "unverified", "severity": "high", "axis": "real-server",
                  "summary": "…", "evidence": "…", "target_stage": 5}],
  "rr_ids": [],
  "common_candidates": ["C-21"],
  "not_executed": ["…"],
  "risk_surface": [{"what": "이 변경이 깨뜨릴 수 있는 것", "axis": "concurrency",
                    "covered_by": "테스트명 또는 '미검증'"}],
  "cost": {"duration_min": 40, "tool_calls": 96},
  "deviations": ["오케스트레이터 지시와 다르게 결정한 것 + 근거"],
  "judgments": [{"kind": "substitution",                      // decision·substitution·semantic·scope·interpretation·design·deviation 중 하나 (§21)
                 "summary": "무엇을 정했나", "rationale": "왜",
                 "source": "레포트#절", "check": "검증 단계에서 무엇을 어떻게 확인하나",
                 "affects": ["CC-0025"], "verify_slices": ["notice"], "verify_stage": 5}],
  "report_file": "workspace/<project>/reports/<상세 레포트>.md",
  "next_action": "reviewer 검토 요청"
}
```
````

- `result`: `done` | `done_with_gaps` | `blocked` | `failed`.
- `open_items` 는 id 없이 보고해도 된다 — 채번은 오케스트레이터가 `gate.py oi new` 로 한다.
- `changed_files` 는 실제로 고친 파일 전부. 오케스트레이터가 `git status`·`diff` 로 대조하고,
  **자기 소유 밖의 파일(공용 설정·common·다른 slice)** 이 있으면 되돌린 뒤 공통 후보로 돌린다(§6-4).
- 실행하지 못한 검증은 `not_executed` 에 이유와 함께 적는다. 비워 두고 통과로 보고하지 않는다.
- `risk_surface` 는 **이 변경이 무엇을 깨뜨릴 수 있는가**를 스스로 선언하는 칸이다(§14). `covered_by` 가 "미검증" 이면 확인 필요 항목으로 올린다.
  RR 을 반영하는 작업에서는 비워 둘 수 없다 — 리팩토링이 더 큰 결함을 낳은 실측(RR-0041: 락 축소 목적의 `REQUIRES_NEW` 가 커넥션 2중 점유를 만듦) 때문이다.
- **수치를 주장하면 그 수치를 낸 명령을 함께 적는다.** `risk_surface`·`deviations`·`not_executed`·산문 어디에서든
  "N건" · "최댓값 X" · "전부/하나도" 같은 주장을 하면 그것을 낸 명령(또는 파일:라인)을 같은 문장에 둔다.
  실측: 서브에이전트가 `risk_surface` 에 "새 마이그레이션 번호가 **전역 최댓값 1.0.840** 보다 낮다" 고 적고
  그에 맞춰 플래그 추가를 권했는데, **1.0.840 은 존재하지 않았고** 실제 최댓값은 1.0.800 이어서 결론이 거꾸로였다.
  근거 명령을 함께 적게 하면 쓰는 쪽이 한 번 더 돌려 보게 되고, 읽는 쪽이 재현할 수 있다.
  **집계 방식도 적는다** — 예: 테스트 개수는 surefire XML 의 `<testcase>` 개수(`tests` 속성은 `@Nested` 에서 틀린다).
  **변경 전 수치를 주장하면 어떻게 그 상태를 만들었는지도 적는다**(예: `git stash push -u -- <파일>` 후 같은 명령·같은 DB).
- `judgments` 는 **자동 변환이 아니라 판단으로 정한 것**이다(§21). `deviations` 에 적은 것은 전부 판단이므로 `judgments` 에도 싣는다.
  id 없이 보고하면 오케스트레이터가 레포트 `pa-meta.judgments` 로 옮겨 `python tools/judgment.py import --report <레포트> --write` 로 채번한다.

### 12-1. 산출물을 먼저 쓰고 덮어 채운다 (멈춤 내성)

**에이전트 1회 실행은 언제든 중간에 끊긴다.** 실측: 분류 에이전트 1회차가 시작 직후 600초 무진행으로 멈춰(스트림 워치독 미복구)
**산출물 0건**으로 끝났고, 그때까지 읽은 입력·세운 판단이 전부 사라져 다음 회차가 처음부터 다시 읽었다.
세션이 사라지는 경우의 대비(HANDOFF·state.yaml)는 있었지만, **한 번의 에이전트 실행 안쪽**에는 대비가 없었다.

그래서 **모든 서브에이전트는 결과를 마지막에 한 번 쓰지 않는다**:

1. 산출물의 **골격을 먼저 쓴다** — 식별자·목차·필수 키만 채운 상태로 실제 파일에 저장한다.
   (예: 분류는 id·priority·depends_on·traits 만 있는 `slices.yaml`, 개발은 시그니처·스텁, 분석은 절 제목과 빈 표)
2. 그 다음 **같은 파일을 덮어 가며** 내용을 채운다. 임시 파일·다른 이름으로 쓰지 않는다 — 덮어쓰기가 곧 체크포인트다.
3. 큰 산출물은 절·항목 단위로 **쓸 수 있게 되는 즉시** 쓴다. "다 읽고 나서 한 번에 쓴다" 로 계획하지 않는다.
4. 멈춘 뒤 재실행하면 **남아 있는 파일을 먼저 읽고 이어서 채운다**. 처음부터 다시 만들지 않는다.

오케스트레이터는 긴 작업을 맡기는 프롬프트에 이 네 줄을 그대로 싣고, 멈춘 실행은 `state.yaml` 에 `blocked` 로 적은 뒤
(성공으로 넘기지 않는다) 남은 산출물을 알려 주며 재실행한다. 비용 근거: 재실행 비용을 "처음부터" 가 아니라 "남은 만큼" 으로 줄이는 규칙이고
공정을 늘리지 않는다.
- reviewer 는 같은 블록에 `findings[]`(§7 형식)를 함께 싣는다.
- **`report_file`**: 표·목록·파일별 설명 같은 상세는 레포트 파일에 쓰고 그 경로를 적는다. **블록 밖 산문은 3000자 이내**(훅이 막는다, config `pipeline.token.report_prose_chars`).
  보고 전문은 오케스트레이터 문맥에 남아 이후 모든 호출에서 다시 읽히기 때문이다(§26). 다음 에이전트에게는 이 경로가 전달된다.
- **옮기기는 기계로 한다.** 결과 블록은 SubagentStop 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_<단계>_<slice>.json` 에
  자동 저장한다 — 에이전트에게 같은 JSON 을 따로 저장시키지 않는다(같은 내용을 두 번 쓰는 출력·호출이 준다, §26). 오케스트레이터는 받은 뒤 `python tools/ingest_result.py --json <그 파일> --stage <N> --slice <id> [--unit <u>] --name <설명> [--body <본문.md>]` 로
  open_items 채번(OI) → 레포트(`pa-meta` 포함, repo 는 git 실측) → judgments 채번(JD)을 한 번에 한다.
  실측: 손으로 옮기면 judgments·open_items 를 빠뜨리거나 문구를 줄인다. 결과 블록이 정본이고 레포트는 그 사본이다.
  **다음 단계가 쓸 산출(동작 계약 행 FC·시그니처 목록·대조표)은 JSON 필드(`fc_map`·`signatures` 등)로 저장하게 하고**, 산문 보고에만 있으면
  보고 본문을 파일로 떠서 `--body` 로 넘긴다(실측: 계약 단계가 산문으로만 낸 FC 25행이 어디에도 남지 않아 spec 작성자가 다시 매겼다).
- **테스트 실행 명령은 클래스를 나열한다.** Maven `-Dtest='패키지.*'` 패턴은 0건을 실행하고 종료 코드 0 이다 - 지시·게이트 명령에 쓰지 않는다(실측).
- **사람이 만든 자료는 참고이고 정본은 원본 소스다(migration).** 분석 문서·산출물·공유 브랜치에 올라온 계약·spec·소스는 사람(또는 원본 없는 환경의 에이전트)이 만든 것이라
  오류가 섞인다. 동작·규칙·SQL 의 근거는 AS-IS 원본의 파일:라인으로 대고, 참고 자료는 원본과 대조한 뒤에만 쓴다. 어긋나면 원본을 따르고 `deviations` 에 적는다.
  오케스트레이터는 모든 서브에이전트 프롬프트에 이 원칙을 적는다.
- **AS-IS 운영 동작을 그대로 옮긴다 - 개선·정상화하지 않는다(migration).** 의미 없거나 문제가 많아 보이는 코드·쿼리·권한 공백·결함도 에이전트 판단으로 고치지 않고 AS-IS 대로 이관한다.
  개선은 테스트 단계(5·6·7)에서 사람이 요청하면 RR 로 고친다. 예외는 셋뿐이다: 대상 DB 방언 등가 보정(같은 결과를 내기 위한 변환), 사람이 승인한 TO-BE 규약, 사람 결정.
  발견한 결함·위험은 고치는 대신 확인 필요 항목(OI)으로 올리고 해당 검증 단계에 예약한다(실측: 에이전트가 권한 결함을 '정상화' 해 AS-IS 와 다른 동작을 잠갔다가 되돌렸다).
  **이전 차수(이미 만든 TO-BE)에서 사람이 고친 동작도 사람 결정이다** - AS-IS 와 다르다는 이유로 AS-IS 로 되돌리지 않는다. 공통·SQL 을 이전 차수 코드에서
  가져왔으면 그 코드의 주석·커밋·결정 기록에서 "AS-IS 와 다르게 바꾼 이유" 를 먼저 찾고, 있으면 그대로 둔다(실측: 2차가 사람 판단으로 LEFT JOIN 으로 바꾼 코드 목록 SQL 을
  3차 공통 작업이 AS-IS 내부 조인으로 되돌렸다가 사용자 지적으로 취소했다).
- **AS-IS 운영에서 실제로 실행되지 않던 코드는 살리지 않고 주석으로 옮긴다(migration).** 상수·설정으로 꺼진 분기, 실행하면 항상 오류인 SQL·코드와
  그 오류 때문에 매번 뒤가 돌지 않던 줄, 호출 경로가 없는 메서드·statement 는 TO-BE 에서 실행 코드로 옮기면 AS-IS 운영에 없던 동작(특히 외부 시스템 쓰기)을 새로 만든다.
  원문은 TO-BE 파일 안에 전체 주석 블록으로 남기고 머리에 AS-IS 파일:라인·실행되지 않던 이유·판단 JD 를 적는다. "실행됐는가" 는 설정·상수·예외 흐름까지 따라가 판정한다.

## 26. 토큰 위생 — 문맥에 넣는 것은 그 뒤 모든 호출의 비용이다

비용의 대부분은 입력·출력이 아니라 **캐시 읽기**다. 캐시 읽기는 매 호출마다 그때까지 쌓인 문맥 전체를 다시 읽는 양의 합이라,
한 번 문맥에 들어간 빌드 로그·통째 읽은 파일·보고 전문은 **그 뒤 모든 호출에서 다시 비용**이 되고, 에이전트가 길어질수록 비용은 호출 수의 제곱으로 는다.
(실측: 파이프라인을 만든 세션 하나가 호출 277회·최대 문맥 626k·캐시 읽기 8,600만 토큰. `python tools/cost_probe.py <기록 디렉토리>` 로 측정한다.)
품질을 줄이는 규칙이 아니다 — 같은 정보를 **필요한 만큼만, 한 번만** 문맥에 넣는 규칙이다.

1. **도구 호출을 묶는다.** 서로 기다릴 필요가 없는 읽기·검색·실행은 한 메시지에서 함께 부른다. 호출 수가 곧 다시 읽는 횟수다.
2. **필요한 부분만 읽는다.** 큰 파일은 Grep(`-n`) 으로 위치를 찾고 Read 의 `offset`·`limit` 로 그 부분만 본다. AS-IS 원문처럼 근거로 전부 봐야 하는 것은 예외다 — 그때도 한 번만 읽는다.
3. **같은 것을 다시 읽지 않는다.** 방금 쓴·고친 파일을 확인하려고 다시 읽지 않는다(Edit·Write 는 실패하면 오류가 난다). 지침·프로필은 시작할 때 한 번 읽는다.
4. **긴 출력은 로그 파일로.** 6000자를 넘는 Bash 출력은 훅이 전체를 로그 파일로 빼고 앞부분·오류·실패·결과 요약·끝부분만 보여 준다(config `pipeline.token.bash_compact_chars`).
   더 필요하면 그 로그를 Grep 한다. 테스트 수·실패 수는 출력이 아니라 결과 파일(JUnit XML, `tools/surefire_sum.py`)에서 읽는다.
   전체 출력이 정말 필요할 때만 명령에 `PA_FULL_OUTPUT=1` 을 붙인다. 파일 내용을 보려고 `cat` 하지 말고 Read 를 쓴다.
5. **보고는 짧게, 상세는 파일로**(§12 `report_file`). 블록 밖 산문 3000자 이내.
6. **오케스트레이터**:
   - 다음 에이전트에게 앞 에이전트의 보고 전문을 붙이지 않는다. `report_file` 경로와 결과 블록의 필요한 값(지적 목록·계약 경로 등)만 준다.
   - 결과 블록은 훅이 저장한 파일을 `tools/ingest_result.py` 로 옮기고(§12), 마무리 검사는 `gate.py finalize` 로 한다(채번·검사·문제만 출력).
   - 범용 에이전트(general-purpose)에게 탐색·확인을 맡기지 않는다. 범용 에이전트는 시작부터 문맥이 크다(실측: 시작 문맥 약 96k, 파이프라인 에이전트의 5배 이상) —
     정해진 일은 해당 파이프라인 에이전트로, 짧은 확인은 오케스트레이터가 Grep·Read 로 직접 한다.
   - `docs/LESSONS.md` 는 읽지 않는다. 덧붙이기는 `python tools/lessons.py add`, 찾기는 `lessons.py grep` 으로 한다.
   - 한 세션에서 이미 읽은 절·지침은 다시 읽지 않는다.
7. **설정으로 거는 상한** (`.claude/settings.json`):
   - `autoCompactWindow: 400000` — 문맥이 40만 토큰에 이르면 자동 압축한다(기본은 1M 모델에서 약 967K). 실측: 메인 세션 하나가 5일 동안 호출 2,209회·최대 966k 로
     전체 캐시 읽기의 약 21% 를 냈다. 상태는 `state.yaml`·HANDOFF·레포트에 있으므로 압축 뒤에도 이어 갈 수 있다. 실측 평균 최대 문맥이 12만~30만인 에이전트는 영향이 없고,
     70만 넘게 길어진 실행만 압축된다(서브에이전트 적용 여부는 문서에 명시가 없어 실측으로 확인한다).
   - `subagentPromptCacheTtl: "1h"` — 서브에이전트 캐시를 1시간 유지한다. 실측: 빌드 대기로 5분이 지나 문맥을 다시 쓴 양이 캐시 쓰기의 약 43%.
     1시간 캐시는 쓰기 단가가 더 비싸므로(입력의 2배, 5분은 1.25배) 적용 뒤 `cost_probe.py` 로 순효과를 확인한다.
   - 되돌리기: 해당 키를 지우거나 개인 설정(`.claude/settings.local.json`)에서 덮는다.
8. **재작업은 새 에이전트로 좁게.** reviewer 지적을 반영할 때 이미 문맥이 큰 developer 를 재개하지 말고, 새 developer 에게 지적 목록·대상 파일·`report_file` 만 준다.
   예외: API 서버 오류(5xx)로 중단된 에이전트는 산출물 손실을 막기 위해 같은 에이전트를 재개한다(§6).

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

코드·주석·로그·SQL·설정·DDL `COMMENT`·테스트 이름·화면 문구·커밋 메시지·레포트·보고(`pa-agent-result` 포함) 어디에도 이모지를 쓰지 않는다.
상태와 강조는 텍스트(`완료`·`주의`·`[의미차이:태그명]`)로 쓴다. 전문·예외 처리(escape 표기)는 §15. 훅이 막으면 우회하지 말고 텍스트로 고친다.
