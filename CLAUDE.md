# CLAUDE.md — project-agents

이 repo는 대규모 프로젝트를 **단계 × 업무(slice) × 계층**으로 나누어 에이전트가 순차 수행하는
파이프라인이다. 상세 단계 정의는 `README.md`, 설계 근거는 `docs/DESIGN.md`를 따른다.

## 핵심 원칙

- **말로 시키면 조합으로 받는다**: 사용자가 `/명령` 이름 없이 상황("3차 범위 들어왔어", "버그 제보", "테이블 정의서 뽑아줘")을 말하면
  먼저 `.claude/skills/work-router/SKILL.md` 를 읽고 알맞은 조합(기존 명령·에이전트의 실행 순서)을 골라 진행한다.
  사람 확인 지점·게이트는 조합 안에서도 그대로 멈춘다.
- **근거 기반**: 모든 코드는 `workspace/<project>/knowledge/PROJECT_BRIEF.md`와 `workspace/<project>/00_inputs/`의 문서를 근거로 작성한다.
  근거가 없는 기능은 추측으로 만들지 말고 `workspace/<project>/reports/`에 "근거 부족" 항목으로 남긴다.
- **slice 단위 작업**: 2·4단계는 항상 하나의 slice만 대상으로 한다. 전체를 한 번에 만들지 않는다.
- **계약 우선**: Backend는 slice마다 OpenAPI 계약을 산출하고, Frontend는 그 계약만 보고 개발한다.
- **게이트 준수**: 2·3·4단계는 빌드와 단위테스트가 통과해야 완료로 기록한다. 실패하면 상태를 `blocked`로 남긴다.
- **developer → reviewer**: 생성 에이전트와 검토 에이전트를 분리한다. 검토에서 나온 지적은 같은 단계 안에서 수정한다.
- **되먹임은 요구서로만**: 5~7단계의 결함은 반드시 `templates/refactor-request.yaml` 형식으로
  `workspace/<project>/refactor-requests/`에 기록한다. 요구서 없이 코드를 직접 고치지 않는다.
- **상태는 파일로**: 진행 상황은 `workspace/<project>/state.yaml`에만 기록한다. 대화 기억에 의존하지 않는다.
- **세션 인계는 HANDOFF.md 로**: 새 세션은 작업 전에 `workspace/<project>/HANDOFF.md`(없으면 `templates/HANDOFF.md` 로 만든다)를 먼저 읽는다.
  사용자 원칙·작업 트리와 브랜치·업로드 규칙·세션 시작 루틴·현재 진행·핵심 결정·사람만 하는 일을 담고, 단계가 끝나거나 사람 결정이 나올 때마다 갱신한다.
  프로젝트 고유 정보는 여기(workspace, git 제외)에만 두고 이 저장소의 지침에는 일반화한 규칙만 둔다.
- **정직한 보고**: 실행하지 못한 테스트, 구성하지 못한 환경은 통과시키지 말고 그 사실을 레포트에 남긴다.
- **게이트는 증거로**: 레포트 끝에 `pa-meta` 블록(실행 명령·종료 코드·테스트 개수·git 실측)을 붙이고
  `python tools/gate.py check --stage <N> [--slice <id>]` 를 통과해야 단계를 `done` 으로 기록한다. 서브에이전트 보고도 `pa-agent-result` 블록으로 끝낸다.
- **(차세대) 공통은 먼저, 한 번에, 계약으로**: 업무 변환 전에 공통 사용 행렬(`tools/common_usage.py`)과 공통 계약(`tools/common_contract.py`)을
  만들고 사람이 승인한다. 공통은 `common-porter` 만 수정하고 업무 slice 는 소비만 한다. 공통을 업무 안에 임시 구현·복제하지 않는다 — 없으면 공통 요청(CR) (`pipeline-core §17`).
- **기대 동작 테스트는 다른 에이전트가 먼저 쓰고 잠근다**: 코드 작성자가 자기 테스트로 자기 코드를 확인하지 않는다. 잠긴 spec 은 고칠 수 없고 해제는 사람만 한다 (`pipeline-core §18`).
- **큰 slice 는 필요할 때만 업무 프로세스 기준 unit 으로 나눈다**: `tools/slice_units.py measure` 가 기준을 넘는다고 판정한 slice 만 상태 전이 기준으로 나누고,
  여러 unit 이 쓰는 코드는 core unit 이 먼저 만든다(공용 유틸·상위 클래스·DAO 는 클래스 통째, 거대 컨트롤러·서비스 구현체는 메서드 단위). 계약·도메인은 slice 하나로 두고, slice 완료는 모든 unit·흐름 테스트·AS-IS 전수 대조를 통과해야 한다 (`pipeline-core §20`).
- **화면은 기계가 판정하고 AI 는 고른 이미지만 본다**: 통과한 스크린샷은 읽지 않는다 (`pipeline-core §19`).
- **판단은 기록하고 검증 단계에서 다시 확인한다**: 자동 변환이 아니라 판단으로 정한 것(사람 결정·대체 매핑·`불필요:`·의미 차이 수용·범위 제외·해석·지시와 다른 결정)은
  `python tools/judgment.py` 로 채번하고(JD), 5단계(필요 시 7단계)가 영향 slice 마다 다시 확인한다. 기준은 차세대면 "AS-IS 기능이 손실 없이 동작하고 요구사항에 맞게 온전히 개발돼 있다",
  신규 개발이면 "요구사항에 맞게 온전히 개발돼 있다". 확인 결과가 없으면 게이트가 막는다 (`pipeline-core §21`).
- **확인 필요는 파일로**: "확인 필요·미검증·결정 대기" 는 레포트 산문에 두지 말고 `python tools/gate.py oi new …` 로 채번한다.
  `high` 이상은 RR 전환이나 사람 승인 없이 단계를 끝낼 수 없다.
- **검증 축을 바꿔 가며 본다**: 단계를 늘려도 같은 축(mock·jsdom·단위)에서만 보면 새 결함은 나오지 않는다.
  slice 의 `traits` 가 요구하는 축(`real-db`·`real-server`·`browser`·`concurrency` 등)을 닫거나, 닫을 단계를 예약한다.
- **깨뜨릴 수 있는 것을 먼저 말한다**: RR 을 반영할 때는 `risk_surface` 에 "이 수정이 무엇을 깨뜨릴 수 있는가" 를 적고 그 축을 덮는다.
- **부분 재실행 가능**: 전수 변환이 기본이 아니다. `/rerun`·`/refactor` 의 slice·layer 필터로 지정 범위만 돌리고 나머지는 건드리지 않는다.
- **재실행 = 업그레이드**: 다시 돌릴 때마다 왜 처음에 못 잡았는지를 `docs/LESSONS.md` 에 적고 해당 stage 의 스킬·프로필·에이전트를 같은 회차에 갱신한다.
- **git 에는 스킬만**: `workspace/<project>/`(입력·AS-IS·산출물)와 `target_dir`(변환 소스)는 절대 커밋하지 않는다. `.gitignore` 가 막고 있으며, 커밋 전 `git ls-files | grep workspace/` 가 비어 있어야 한다.
- **target_dir 의 지침을 먼저 따른다**: target_dir 에 `CLAUDE.md`·`AGENTS.md` 등 작업 지침이 있으면 모든 단계·에이전트가 작업 전에 읽는다.
  브랜치·push·DB 이름·마이그레이션 번호 규칙 같은 운영 제약은 그 지침을 따르고, 품질 규칙은 양쪽 중 더 엄격한 쪽을 따른다.
- **target_dir 은 스스로 push 하지 않는다**: 파이프라인은 target_dir 에 로컬 커밋까지만 한다. push 는 사용자가 직접 하거나,
  사용자가 대상 브랜치를 지정하고 그 건마다 명시 승인한 경우에만 한다. target_dir 지침이 push 를 금지한 브랜치는 승인이 있어도 push 하지 않는다.
- **이 repo 의 push 는 매번 묻는다**: `python tools/selfcheck.py` 와 `pytest` 가 통과한 뒤 사용자에게 묻고 승인받은 건만 push 한다. 한 번의 승인은 그 건에만 유효하다.
- **실전 개선은 일반화해서 단계 끝에 커밋한다**: 실전 수행 중 발견한 지침·도구 개선은 프로젝트 고유 정보(프로젝트명·업무명·고객명·경로) 없이
  일반화해 `docs/LESSONS.md`·스킬·에이전트에 반영하고, 그 단계가 끝날 때 커밋한다.
- **기존 코드 위에 얹을 때는 부족점을 모은다 (brownfield)**: target_dir 에 파이프라인 밖에서 만든 기존 코드가 있으면, 파이프라인이 지원하지 못한 점을
  단계마다 `workspace/<project>/reports/<ts>_brownfield_gaps.md` 에 누적하고(무엇이 없었나·어떻게 우회했나·지침을 어떻게 고칠까), 일반화한 것은 위 규칙대로 반영한다.
  brownfield 모드가 파이프라인에 정식으로 생기기 전까지의 임시 규칙이다.
- 모든 레포트·문서·코드 주석은 **한글**로 작성한다.
- **이모지 금지 (예외 없음)**: 소스 주석·Javadoc·로그 문구·Mapper 쿼리 주석·yml/properties 주석·DDL `COMMENT`·테스트 이름·
  화면 문구·커밋 메시지·레포트·산출물·에이전트 보고·이 저장소의 지침 어디에도 이모지를 쓰지 않는다. 상태와 강조는 텍스트로 쓴다
  (`완료`·`주의`·`[의미차이:태그명]`). 강제 장치: 쓰기 시점 훅(`tools/hooks/guard.py`) → `tools/quality.py`(NO-EMOJI, critical) →
  `gate.py`(no-emoji) → `tools/selfcheck.py`·CI. 판정 기준은 `tools/_emoji.py` 하나다.
- **전역 규칙은 에이전트 지침보다 우선한다**: 이 파일과 `pipeline-core` 의 규칙은 모든 명령·에이전트·스킬에 예외 없이 적용된다.
  개별 지침과 충돌하면 전역 규칙을 따르고 보고의 `deviations` 에 적는다.
- **훅이 원칙을 강제한다** (`.claude/settings.json`, `pipeline-core §16`): 이모지가 든 쓰기, 게이트를 통과하지 못한 단계의 완료 기록,
  결과 블록 없는 서브에이전트 종료를 도구 호출 시점에 막는다. 막히면 우회하지 말고 원인을 고친다.

## 외부 도구

6단계(보안)와 7단계(QA)는 `external/` 아래 git subtree 로 편입된 도구 repo(`config/tools.yaml` 경로)의 `SKILL.md`를 읽어 그 방법론대로 수행하고,
결과 레포트를 `workspace/<project>/reports/`로 가져온 뒤 리팩토링 요구서로 변환한다.

## 파일명 규칙

레포트 파일명은 한국시각(KST) 기준 `yymmddhhmm_<설명>.<확장자>` 접두어를 붙인다.
(`TZ=Asia/Seoul date '+%y%m%d%H%M'` / PowerShell: `Get-Date -Format 'yyMMddHHmm'`)
