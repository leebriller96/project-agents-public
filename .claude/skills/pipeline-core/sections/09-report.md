<!-- pipeline-core §9 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 9. 레포트

- 위치: `workspace/<project>/reports/`, 파일명 `yymmddhhmm_stage<N>_<slice|all>_<설명>.md` (KST).
  unit 레포트는 `yymmddhhmm_stage<N>_<slice>_unit-<unit>_<설명>.md` 이고 pa-meta 에 `unit`·`asis_covered` 를 적는다 (§20).
- HTML 변환: `python tools/build_report.py <md파일>`.
- 타임스탬프는 항상 `python tools/kst_now.py` (파일명용 `yyMMddHHmm`; `--full` 은 본문용 `YYYY-MM-DD HH:MM`). bash `TZ=... date` 는 Windows Git Bash 에서 틀린다. HANDOFF 진행 기록은 `python tools/handoff.py note "<내용>"` 이 실측 시각을 붙여 넣는다.
- 레포트에는 항상 포함: 대상·입력 근거·수행 내용·게이트 결과(빌드/테스트 명령과 출력 요약)·미완료/근거 부족 항목·다음 단계 안내.
- 실행하지 못한 것은 "실행하지 못함 + 이유" 로 쓴다. 통과한 것처럼 쓰지 않는다.
- **레포트 끝에 `pa-meta` 블록을 붙인다** (형식·필드: `templates/report-meta.md`).
  골격: `python tools/gate.py template --stage <N> --slice <id> --agent <이름>`.
  서브에이전트 결과가 있으면 손으로 옮기지 않는다 — 훅이 저장한 `reports/agent-results/*.json` 을 `tools/ingest_result.py` 로 옮긴다(§12, §26).
  본문의 서술과 별개로 이 블록이 기계 대조 대상이다 — `gates[]`(명령·종료 코드·테스트 개수),
  `repo`(git HEAD·브랜치·dirty·변경 파일), `open_items[]`, `rr_ids[]`, `not_executed[]`.
- **레포트를 쓴 직후 `python tools/gate.py finalize --stage <N> [--slice <id>]` 를 실행한다** — id 없는 확인 필요 항목을 채번한 뒤
  `check` 와 같은 검사를 돌리고 문제만 출력한다(통과 훅 목록을 문맥에 남기지 않는다, §26). 전체 표가 필요하면 `gate.py check`.
  FAIL 이면 그 단계를 `done` 으로 기록하지 않는다. 검사 항목:
  실패한 게이트를 통과로 적기 · 테스트 0건 통과 · git 실측과 다른 기재 ·
  high 이상 확인 필요 항목의 무단 종료 · state.yaml 과의 모순 · 레포트의 자격증명/개인정보 노출 ·
  (2·3·4단계) 바뀐 소스의 상품화 품질(`tools/quality.py` 규칙: Javadoc·로거·traceId·Mapper 주석·콘솔 출력·민감정보 로깅·이모지) ·
  테스트 수·실패 수 ↔ 실제 결과 파일(`gates[].results` 의 JUnit XML) 불일치 · 단계 시작 전 결과 파일 재사용 · 레포트의 이모지 ·
  (migration) 외부 데이터소스 테이블의 CREATE·데이터소스 지도의 비밀정보(§22) ·
  (migration) **AS-IS 원본이 실제로 있는가**(`asis-source` — 없으면 `state.yaml` 의 `asis_source` 선언이 필요하다, §24 배경) ·
  (2·4단계) **slice 가 소비하는 공통을 적었고 그것이 실제로 있는가**(`consumes-integrity` — 적지 않은 공통을 쓰면 WARN, §17) ·
  (4단계) **화면 주소·메뉴 시드 주소가 slices.yaml `routes` 와 같은가**(`routes-match` — routes 가 없으면 건너뜀, §25).
  (2·3·4단계) **계약에서 만든 산출물(FE 타입 등)이 계약과 같은가**(`contract-sync` — 설정 `pipeline.gate.contract_sync` 의 비교 명령을 돌린다, 없으면 건너뜀).
  (차세대 2·3단계) **AS-IS 실행 자원 설정(스레드·풀·시간 제한·업로드·세션)마다 TO-BE 대응이 판정됐는가**(`runtime-config` — 표 `knowledge/ASIS_RUNTIME_CONFIG.yaml` 이 없으면 WARN, 미판정이면 FAIL).
  (도구가 잡아낸 것은 사람이 다시 읽어 확인하지 않아도 되고, 도구가 못 보는 것만 사람이 본다.)
- 레포트·산출물에 비밀번호·토큰·키·주민번호·연락처 **원문을 적지 않는다.** 값은 `***` 로 가리고 경로·변수명만 남긴다.
  별도 스캔: `python tools/gate.py secrets workspace/<project>/reports`.
