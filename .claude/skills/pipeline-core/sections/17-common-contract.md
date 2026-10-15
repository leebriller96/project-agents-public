<!-- pipeline-core §17 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 17. 공통 계약 — 공통을 먼저 확정하고 업무는 소비만 한다 (migration)

실측된 문제: 업무 단위로 변환하면 업무 에이전트가 자기가 쓰는 공통 메서드만 보고 판단해 ① 공통 클래스를 업무별로 부분 이관하고
② 한 메서드만 쓰면 private 으로 복제했다. 그 뒤 "공통만 변환" 을 따로 돌리면 업무 코드와 어긋나 "업무 변환 → 공통 변환 → 다시 짝지어 검사"
라는 중복 공정이 생겼다. Mapper statement 도 같았다. 원인은 공통 코드의 **소유자와 확정 시점**이 없었던 것이다.

흐름(1단계 승인 직후 → 2단계 업무 slice 전):

| 순서 | 무엇 | 누가 | 산출물 |
|---|---|---|---|
| 1 | 공통 사용 행렬 — 어느 업무가 공통의 **어느 메서드·statement** 를 어떤 경로(direct·inherited·via)로 쓰는가 | `python tools/common_usage.py` (정적 분석, 결정적) | `knowledge/COMMON_USAGE.yaml`·`.md` |
| 2 | 공통 계약 초안 — 항목마다 owner·decision 제안 | `python tools/common_contract.py init` | `contracts/common-contract.yaml` |
| 3 | 검토·결정 — `review` 항목(slice 소유 미사용), 업무로 내릴 항목, 업무 간 교차, 여러 모듈 항목의 module(복사 또는 전 모듈 공통), 이관 안 함 목록(동적 호출 의심만 훑어봄) | 사람 (slice-planner 가 근거 정리) | 계약의 owner·decision·module·decided_by |
| 4 | 승인 | **사람만** — `! python tools/common_contract.py approve --by <이름>` (에이전트 실행은 훅이 차단) | `approved: true` |
| 5 | 공통 선행 변환 | `/stage2 common-port` → (sql-migrator `convert common-port`) → `common-porter` | TO-BE 공통 모듈·공유 Mapper, 계약 `tobe`·`status: ported` |
| 6 | 업무 slice 변환 | backend-developer — 계약을 **소비만** 한다 | 업무 코드 |

규칙:
- 한 업무만 쓰는 공통 메서드도 기본은 **공통 유지**다(owner: common). 업무로 내리는 것(`slice:<id>`)은 사람이 결정하고 `decided_by` 를 남긴다.
  다른 업무도 쓰는 항목은 내릴 수 없다(validate 가 거부).
- **미사용 일괄 규칙**: 어느 slice(hold 포함 전체)에서도 도달 경로가 없는 공통 메서드·공통 namespace statement 는 개별 `review` 로 올리지 않고
  `owner: none`·`status: not_migrated`(이관 안 함)로 일괄 판정해 계약 옆 목록 파일(`contracts/common-contract-not-migrated.yaml`)에만 남긴다.
  계약에는 `summary`(review 건수·일괄 규칙 전 기준 건수·이관 안 함 건수·범위 제외 건수)만 남는다. 실측: 초안 4천여 항목 중 사람 검토 2,500여 건의
  대부분이 미사용이어서 한 건씩 판단할 수 없었다. 폐기(discard)가 아니라 "이번에 옮기지 않음" 이므로, 동적 호출·리플렉션으로 쓰이는 항목은
  목록 파일에서 사람이 owner 를 `common`·`slice:<id>`·`discard` 로 바꾸고 `decided_by` 를 적으면 다음 `init` 이 계약 항목으로 올린다(승인 해제).
  **개별 review 로 남기는 것**(진짜 판단이 필요한 것): slice 소유 namespace 의 미사용 statement, slice 소유 클래스 중 다른 클래스가 부르는 클래스(서비스·DAO)의
  미사용 public 메서드. 프레임워크 진입점(@Bean·핸들러 등)은 종전대로 공통 유지이고, 접근자는 그 클래스를 어느 slice 가 쓸 때만 진입점으로 본다.
- **범위 제외(brownfield)**: slices.yaml 의 `unassigned.asis`(이번 차수 범위 외 — 분류 `out_of_scope`)와 `pre_pipeline`(이전 차수에 이미 이관 — 분류 `pre_pipeline`)에
  적힌 프로그램·패키지·namespace 는 "소유 slice 없음" 이어도 공통이 아니다. 행렬은 이들을 `excluded_classes`·statement `scope` 로 집계만 하고,
  그 코드에서 출발하는 호출은 slice 사용으로 세지 않으며 slice 가 그 코드를 부르면 그 앞에서 멈춘다(TO-BE 에 이미 있거나 이번에 옮기지 않는다).
  그래서 그 코드만 쓰는 공통 메서드는 공통 선행 변환 대상이 되지 않는다. 계약에는 항목으로 올라가지 않고 `summary.excluded` 건수만 남는다.
- **모듈 차원**: TO-BE 가 모듈(앱)로 나뉘고 config `project.modules` 가 있으면 행렬이 공통 항목마다 사용 slice 의 모듈 집합(`modules`)을 계산하고,
  계약의 owner=common 항목에 `module` 을 붙인다.

  | 사용 모듈 | 기본 제안 | 의미 |
  |---|---|---|
  | 한 모듈의 slice 들만 | `module: <모듈>` | 그 모듈의 공통. 같은 모듈의 다른 slice 는 호출만 한다 |
  | 여러 모듈 | `module: [모듈…]`·`copy: true` | 모듈별 복사본(모듈 간 공유 금지 규약). `tobe` 는 `{모듈: TO-BE}` 로 적는다 |
  | 전 모듈 기반(인증·권한 등) | 사람이 `module: <project.common_module>` 로 바꾸고 copy 를 지운다 | 전 모듈 공통 |

  validate 는 "여러 모듈이 쓰는데 한 모듈 공통", "목록인데 copy 없음", "쓰는 모듈의 복사본 누락" 을 거부한다. 사람이 바꾼 module 은 `init` 을 다시 돌려도 보존된다.
  modules 가 없으면 module·copy 필드를 만들지 않는다(종전 동작).
- 공통 모듈(`tobe.common_module`·`tobe.common_package`·`tobe.shared_mapper_dir`)은 `common-porter` 만 쓴다(3단계 공통화는 예외).
- 업무 slice 는 공통을 복제하지 않는다. 계약에 없는 공통이 필요하면 공통 요청(CR)을 남기고 그 기능만 `blocked` 로 보고한다.
  오케스트레이터는 웨이브 사이에 열린 CR 을 `common-porter cr` 로 묶어 처리한다. 새 공통 항목은 계약 개정(사람 승인) 후 반영한다.
- 강제: gate `common-integrity` — 업무 slice 의 공통 영역 수정·공통 메서드 복제(본문 유사도, 변수명 바꾼 private 복제 포함)·공유 Mapper statement
  복제는 FAIL, common-port 는 owner=common 전부가 TO-BE 에 있어야 통과. 계약 미승인 상태의 완료도 FAIL.
  migration 인데 계약이 없으면 경고(`pipeline.gate.common_contract: strict` 면 FAIL).
  모듈 차원: 계약에서 `copy: true` 로 승인된 항목의 **그 slice 모듈 복사본**은 복제로 보지 않는다. 같은 모듈 안에 복사본이 이미 있으면
  (`project.module_paths` 의 그 모듈 경로를 찾아본다. 매핑이 없으면 이번 변경 파일끼리만 대조) 업무 slice 간 복제로 FAIL 이다.
  한 모듈 공통·전 모듈 공통 항목의 복제는 종전대로 FAIL. 계약 `tobe.module_common`({모듈: 경로})을 적으면 그 경로도 common-porter 만 쓴다.
  gate `slice-scope` 는 slice 의 `module` 과 `project.module_paths` 가 있으면 2·4단계 변경 파일이 자기 모듈 경로·승인된 공통 경로·`existing_code` 밖일 때 WARN 이다.
- AS-IS 가 바뀌면(추가 입력) 행렬과 계약을 다시 만든다 — `init` 은 사람 결정·id 를 보존하고, 항목이 바뀌면 승인을 해제한다.
- **공통 선행 변환이 이 파이프라인 밖에서 이미 끝났으면 계약을 새로 만들지 않는다** (이전 차수·다른 작업 환경).
  새로 만들면 그쪽이 쓴 번호 체계(`CC-xxxx`)가 갈리고 완료된 결과와 어긋난다. 대신 **외부 확정**으로 선언한다:
  `python tools/common_contract.py external --source <정본 문서·절> --numbering <이미 쓴 번호 대역> --evidence <완료 근거> --by '사람:<이름>'`
  → `status: external` · `items: []`. 승인은 평소대로 사람이 `approve` 로 한다.
  `gate.py plan` 은 외부 확정 본문에 대해서는 common-port 단계를 넣지 않고, `common-integrity` 는
  **항목 단위 검사(공통 복제·영역 침범·이행)를 하지 않았다는 것을 INFO 로 남긴다** — 통과로 넘기지 않는다.
  그 방어가 빠지므로 **reviewer 가 slice 코드와 정본 문서의 공통 대응표를 직접 대조**한다.
- **외부가 확정한 공통에 없는 수단이 필요하면 `additions` 로 더한다** (외부 확정 계약에만 있는 자리).
  실측된 공백: `status: external` 은 항목을 두지 않으므로, 업무 slice 를 만들다 **그쪽에 없던 공통 수단**이 필요해지면
  (사번으로 이름·부서를 얻는 수단이 공통에 없었다) 등록할 자리가 없었다. 그러면 "공통을 업무 안에 임시 구현하지 않는다" 를
  지키려 해도 **그 공통이 어디에 있어야 하는지 계약이 말해 주지 못한다.**

  ```
  python tools/common_contract.py addition --cr CR-xxxx --owner common --decision 개선       --target <업무가 호출할 TO-BE 시그니처> --evidence <필요하다는 근거> --judgment JD-xxxx
  ```
  - 외부 확정 본문(`items`)은 그대로 비워 둔다. 더한 것은 **`CC-A001` 대역**으로 따로 센다 — 그쪽 번호와 섞지 않는다.
  - **공통 요청(CR)을 거친 것만** 더할 수 있고, 판단(`JD`) 또는 사람 결정(`decided_by: 사람:…`)이 있어야 한다.
    외부가 확정한 경계를 넓히는 것은 자동 변환이 아니라 판단이다(21절).
  - 더한 것은 **우리가 만든 것이므로 검사한다**: `gate.py plan` 이 미이행 건이 있으면 common-port 단계를 넣고,
    `common-integrity` 가 미이행을 WARN·`ported` 인데 target 에 없으면 FAIL 로 잡는다.
    "외부 확정이라 검사 못 한다" 와 섞지 않는다 — 섞으면 우리가 더한 공통의 미이행이 가려진다.
  - 이행은 `common-porter` 만 한다. 끝나면 `python tools/common_contract.py addition-done --id CC-A001`.
  - **먼저 따져 볼 것**: 정본 문서가 그 **클래스**를 이미 공통으로 매핑했고 빠진 것이 **메서드 하나**뿐이면
    경계를 넓히는 것이 아니라 계약 항목의 누락 보완이므로 `additions` 가 아니다(실측 사례: 암복호 유틸의 짝 메서드).
    `additions` 는 정본에 **없는** 수단을 더할 때 쓴다.
- **slice 는 "이미 있는 공통에서 무엇을 소비하는가" 를 `slices.yaml` 의 `consumes` 에 적는다** (brownfield).
  greenfield 는 공통 사용 행렬이 "누가 무엇을 쓰나" 를 계산하지만, brownfield 는 **공통이 먼저 있고 slice 가 나중에 와서
  방향이 반대**다 — 계산할 수 없다. 적히지 않으면 ① developer 가 공통에 있는 기능을 업무 안에 다시 만들고(실측된 사고)
  ② 공통을 고칠 때 영향 slice 를 역추적할 수 없고 ③ 8단계 공통 명세에 "어느 업무가 어느 공통을 쓰나" 가 빈다.
  **주석으로 적지 않는다 — 도구가 읽지 못한다**(실측: 소비 10종이 전부 YAML 주석에만 있었다).

  ```yaml
  consumes:
    - item: com.example.user.common.util.AESUtil   # FQCN · FQCN#method · Mapper statement
      kind: class                                  # class·method·mapper·statement·service
      source: CONVENTIONS.md#5-4                   # 계약 id 또는 정본 문서#절
      note: AES 암호화 (decrypt 는 CR-0005)          # (선택) 아직 호출하지 않는 것은 그렇게 적는다
  ```
  gate `consumes-integrity`(2·4단계):
  - 적었는데 target 에 **없으면 FAIL** — "공통에 있다고 적기만 하면 통과" 를 막는다. 없으면 공통 요청(CR)이다.
  - **적지 않은 공통을 쓰면 WARN** (변경 파일의 import 를 본다. 공통 접두어는 `project.tobe_common_packages`,
    없으면 `base_package` 에서 `<base>.<common_module>`·`<base>.<module>.common` 으로 유도한다).
    `asis.common_packages` 와 **다른 키**다 — 그쪽은 AS-IS 쪽 설정이고 공통 사용 행렬이 쓴다.
  - 계약이 **외부 확정인데 `consumes` 가 비어 있으면 WARN** — 그때는 이것이 유일한 연결 수단이다.
  - `consumes` 가 없고 계약이 외부 확정도 아니면 INFO (행렬로 계산한다. 뒤로 호환).
  - `existing_code` 와 다르다: `existing_code` 는 이 slice 가 **고칠** 기존 코드, `consumes` 는 **호출만** 할 공통이다.
    공통은 slice 가 고칠 수 없다(`common-integrity` 가 FAIL).
