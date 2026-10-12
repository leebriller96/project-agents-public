---
name: stage8-deliverables
description: 8단계 산출물 작성 — 파이프라인이 남긴 brief·slices·계약·화면정의·매핑표·테스트 결과·레포트를 모아 SI 표준 산출물(요구사항 추적표, 아키텍처 정의서, 테이블 정의서, API 명세서, 화면 정의서, 테스트 결과서 등)을 생성하는 방법론. /stage8 수행 시 사용.
---

# 8단계 산출물 방법론

목표: 앞 단계가 남긴 파일들을 **재가공**해 산출물을 만든다. 새로 조사하지 않는다 — 원천이 없으면 "원천 없음" 으로 표시하고 어느 단계를 다시 돌려야 하는지 적는다.

## 1. 산출물 목록과 원천

`config/project.yaml → deliverables.items` 에서 `true` 인 것만 만든다. 위치 `<target_dir>/docs/deliverables/`, 파일명 `NN_<이름>.md` (+ html).

| NN | 산출물 | 원천 |
|---|---|---|
| 01 | 요구사항 추적표 (RTM) | brief §8, `SLICE_MAP.md`, `docs/api/*.yaml`, `docs/screens/*.md`, 단위테스트 `@DisplayName` 의 REQ ID, 시나리오 문서 — 요구사항 ↔ slice ↔ API ↔ 화면 ↔ 테스트 매트릭스. 연결이 끊긴 요구사항은 붉게 표시 |
| 02 | 아키텍처 정의서 | brief §2·§3, `backend/CONVENTIONS.md`, `frontend/CONVENTIONS.md`, 골격 구조, 배포 구성(있으면) — 구성도는 Mermaid |
| 03 | 업무 분류표 | `slices.yaml`, `SLICE_MAP.md` |
| 04 | 테이블 정의서 + ERD | `db/migration/*.sql` 을 파싱 — 테이블·컬럼·타입·제약·설명(주석), ERD 는 Mermaid erDiagram |
| 05 | API 명세서 | `docs/api/*.yaml` → slice 별 엔드포인트 표 + 요청/응답 스키마 + 에러 코드 표(ErrorCode enum) |
| 06 | 화면 정의서 | `docs/screens/*.md` + 라우트 + 권한 |
| 07 | 공통 모듈 명세 | `docs/deliverables/common-module-spec.md` (3단계) |
| 08 | 단위테스트 결과서 | 2·4단계 레포트의 테스트 결과 + 최신 실행 결과(다시 실행해서 현재 값으로) |
| 09 | 통합테스트 시나리오·결과서 | `docs/test/*-scenario.md`, 5단계 레포트 |
| 10 | 보안 점검 결과서 | 6단계 레포트 + 관련 RR 상태(done 여부) |
| 11 | QA 결과서 | 7단계 레포트 + 관련 RR 상태 |
| 12 | AS-IS/TO-BE 매핑표 | `docs/deliverables/mapping/*-{table,sql,function}-mapping.md`, `common-inheritance.md`, `ASIS_INVENTORY.md`·`ASIS_SQL_INVENTORY.md`·`ASIS_FUNCTION_CONTRACTS.md`·`ASIS_COMMON_INVENTORY.md`, `slices.yaml → asis` — 테이블·SQL(방언 변환·의미차이 판정)·기능(동작 차이)·공통 클래스(4분류) 매핑 + 이관 커버리지(기능 행 100%, SQL A 항목 실행률) (migration 모드만) |
| 13 | 빌드·배포·운영 가이드 | 프로필 명령, 설정 파일·환경변수 목록(값 제외), 마이그레이션 절차, 헬스체크 |
| 00 | 산출물 목록·이력 | 위 파일 목록, 생성 시각, 파이프라인 iteration, open RR 수 |

## 2. 작성 원칙
- 각 산출물 상단에 "원천 파일·생성 시각·iteration" 을 적는다. 사람이 고친 내용을 보존하기 위해 **재생성 시 기존 파일을 `NN_<이름>.prev.md` 로 보관**한다.
- 표는 원천을 그대로 옮기되 설명 열은 한글로 보완한다. 추측으로 채우지 않는다.
- 08~11 결과서는 "실행하지 못함" 항목을 그대로 싣는다.
- 형식: md 원본 + `python tools/build_report.py` 로 html. `deliverables.format` 에 docx 가 있으면 docx 스킬로 변환 (선택).

## 3. 산출물 및 상태
- `<target_dir>/docs/deliverables/NN_*.md|html`
- 레포트 `workspace/<project>/reports/<ts>_stage8_all_deliverables.md`: 생성 목록, 원천 없음 목록, 끊긴 추적 항목 수
- `state.yaml → stages.stage8_deliverables: done`

## 4. 납품 소스 패키지 (`/stage8 package`)

고객사에는 소스만 넘긴다. 개발 중 쓰던 md 문서와 파이프라인 흔적(판단·요구서·확인 항목 번호, `[의미차이:…]`, AS-IS 파일:줄 참조,
에이전트 용어)은 공유 저장소에서는 개발자끼리 쓰는 근거라 지우지 않고, **납품 패키지를 만들 때만** 걷어낸다.

- 도구: `python tools/package_delivery.py --target <target_dir> --ref <납품 브랜치|태그> --out <빈 폴더> [--rules workspace/<project>/delivery.yaml]`
  (`--check` 는 쓰지 않고 검사만). 규칙은 `config/delivery/rules.yaml`(exclude·keep·scrub·scrub_strings·drop_if_only·deny),
  프로젝트별 추가는 `workspace/<project>/delivery.yaml`(목록은 이어 붙인다 - 고객이 요구한 문서·시험은 `keep`).
- 커밋된 내용만 꺼낸다(git 이력·커밋 메시지·커밋 안 한 변경은 나가지 않는다). **주석 구간 안만** 고치고 문자열·코드는 바꾸지 않는다.
  설명용 문자열만 있는 파일(DDL `COMMENT`)은 `scrub_strings` 로 문자열까지 고친다 - 문장 끝 `;` 같은 코드 글자는 건드리지 않는다.
- **금지어(deny)가 문자열·코드에 남으면 패키지를 만들지 않는다(종료 코드 2).** 로그·예외 문구에 판단 번호가 들어 있으면 소스를 고친다
  (시험이 문구를 단언할 수 있어 패키지에서 몰래 바꾸지 않는다).
- 확인: 패키지 폴더에서 빌드(시험 제외)를 돌리고, `<out>.changes.txt`(바뀐 주석 전부)를 사람이 표본 검토한다.
  표지 규칙은 휴리스틱이라 남는 흔적·지나친 삭제가 있을 수 있다 - 발견하면 규칙을 고치고 다시 만든다.
- 레포트 `workspace/<project>/reports/<ts>_stage8_package.md`: 기준 커밋, 패키지 파일 수·제외 수, 정리한 주석 수, 금지어 결과, 빌드 결과, 표본 검토 결과.

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
