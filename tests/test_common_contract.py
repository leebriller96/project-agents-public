# common_contract.py — 공통 계약 초안·사람 결정 보존·승인 조건·공통 복제/소유 침범 검출
import os
import sys

import pytest
import yaml

from conftest import FIXTURES, REPO, dev_meta

sys.path.insert(0, os.path.join(REPO, "tools"))
import common_contract as cc  # noqa: E402
import common_usage  # noqa: E402
from _common import load_yaml  # noqa: E402

LEGACY = os.path.join(FIXTURES, "legacy")
BROWN = os.path.join(FIXTURES, "brownfield")
MODULES = ["user", "admin"]


def usage_file(tmp_path, src=LEGACY, scope=False, modules=None, name="COMMON_USAGE.yaml"):
    doc = load_yaml(os.path.join(src, "slices.yaml"))
    r = common_usage.analyze(src, doc["slices"], None,
                             scope=common_usage.scope_from_slices(doc) if scope else None, modules=modules)
    p = tmp_path / name
    p.write_text(yaml.safe_dump(r, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(p)


def init(tmp_path, *extra, usage=None):
    out = str(tmp_path / "common-contract.yaml")
    assert cc.main(["--contract", out, "init", "--usage", usage or usage_file(tmp_path), "--out", out, *extra]) == 0
    return out


def items(path):
    return {i["asis"]: i for i in load_yaml(path)["items"]}


def not_migrated(path):
    return {i["asis"]: i for i in load_yaml(cc.not_migrated_path(path))["items"]}


def _decide(path, **owners):
    data = load_yaml(path)
    for i in data["items"]:
        if i["asis"] in owners:
            i.update(owners[i["asis"]])
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


REVIEW_DONE = {}    # 레거시 예제는 미사용 일괄 규칙으로 review 가 없다
BROWN_REVIEW_DONE = {"com.legacy.member.MemberDAO#purgeAll/0": {"owner": "discard"},
                     "member.selectMemberOld": {"owner": "slice:member"}}


def test_draft_keeps_single_slice_methods_in_common(tmp_path):
    path = init(tmp_path)
    it = items(path)
    # 한 업무만 쓰는 공통 메서드도 기본은 공통 유지 — 업무별 분해·private 복제를 막는 핵심 결정
    assert it["com.legacy.common.util.CommonUtil#maskName/1"]["owner"] == "common"
    assert it["com.legacy.common.util.CommonUtil#padLeft/2"]["owner"] == "common"
    assert "단일 업무(deposit)" in it["com.legacy.common.util.CommonUtil#maskName/1"]["note"]
    # SQL: 공유 조각은 공통, 소유 업무만 쓰는 statement 는 그 업무, 업무 간 교차는 공유 Mapper 로 승격 제안
    assert it["common.pagingHead"]["owner"] == "common"
    assert it["loan.selectLoanList"]["owner"] == "slice:loan"
    assert it["deposit.depositCols"]["owner"] == "slice:deposit"
    assert it["deposit.selectBaseRate"]["owner"] == "common" and "업무 간 교차" in it["deposit.selectBaseRate"]["note"]
    assert list(load_yaml(path)["items"][0])[0] == "id"


def test_unused_items_are_bulk_not_migrated_not_reviewed(tmp_path):
    """어느 slice 도 도달하지 않는 공통 메서드·공통 namespace statement 는 개별 review 가 아니라 일괄 이관 안 함."""
    path = init(tmp_path)
    it, nm = items(path), not_migrated(path)
    for asis in ("com.legacy.common.util.CommonUtil#unusedLegacy/0", "com.legacy.common.dao.CommonDAO#selectDynamic/1",
                 "common.selectUnused"):
        assert asis not in it
        assert nm[asis]["owner"] == "none" and nm[asis]["status"] == "not_migrated"
    # 동적 호출이 있으면 목록에서 살릴 수 있다는 안내를 남긴다 (자동 폐기가 아니라 이관 안 함)
    assert "동적 호출 1건" in nm["com.legacy.common.util.CommonUtil#unusedLegacy/0"]["note"]
    sm = load_yaml(path)["summary"]
    assert (sm["review"], sm["review_old_rule"], sm["not_migrated"]) == (0, 3, 3)
    assert cc.validate(load_yaml(path)) == []


def test_slice_owned_unused_items_stay_in_review(tmp_path):
    """slice 소유 namespace 의 미사용 statement 와 slice 소유 클래스의 미사용 public 메서드는 사람이 판단한다."""
    path = init(tmp_path, usage=usage_file(tmp_path, BROWN, scope=True))
    it = items(path)
    review = sorted(a for a, i in it.items() if i["owner"] == "review")
    assert review == ["com.legacy.member.MemberDAO#purgeAll/0", "member.selectMemberOld"]
    assert "not_migrated" not in {i["status"] for i in it.values()}
    sm = load_yaml(path)["summary"]
    assert (sm["review"], sm["review_old_rule"], sm["not_migrated"]) == (2, 7, 4)


def test_approval_requires_every_review_item_decided(tmp_path):
    path = init(tmp_path, usage=usage_file(tmp_path, BROWN, scope=True))
    assert cc.main(["--contract", path, "validate"]) == 1
    try:
        cc.main(["--contract", path, "approve", "--by", "홍길동"])
        raise AssertionError("review 가 남았는데 승인됐다")
    except SystemExit as ex:
        assert "승인할 수 없다" in str(ex)
    _decide(path, **BROWN_REVIEW_DONE)
    assert cc.main(["--contract", path, "validate"]) == 0
    assert cc.main(["--contract", path, "approve", "--by", "홍길동"]) == 0
    assert load_yaml(path)["approved_by"] == "홍길동"


def test_out_of_scope_and_pre_pipeline_are_not_common(tmp_path):
    """범위 외·이전 차수 이관 코드는 공통 선행 변환 대상이 아니고, 그 코드만 쓰는 공통 메서드도 공통이 되지 않는다."""
    # 종전(범위 제외 없음): 가입(이전 차수) 클래스가 공통으로 잡히고, 가입만 쓰는 legacyJoin 이 member 경유로 공통이 된다
    before = items(init(tmp_path, usage=usage_file(tmp_path, BROWN, name="u0.yaml")))
    assert before["com.legacy.join.JoinService#isJoined/1"]["owner"] == "common"
    assert before["com.legacy.common.util.StrUtil#legacyJoin/1"]["owner"] == "common"
    os.remove(str(tmp_path / "common-contract.yaml"))
    path = init(tmp_path, usage=usage_file(tmp_path, BROWN, scope=True))
    it, nm = items(path), not_migrated(path)
    assert not any(a.startswith(("com.legacy.batch.", "com.legacy.join.", "batch.", "join.")) for a in it)
    assert "범위 제외 코드(pre_pipeline)만 사용" in nm["com.legacy.common.util.StrUtil#legacyJoin/1"]["note"]
    assert "범위 제외 코드(out_of_scope)만 사용" in nm["com.legacy.common.util.StrUtil#batchOnly/1"]["note"]
    assert load_yaml(path)["summary"]["excluded"] == {"class_out_of_scope": 1, "class_pre_pipeline": 1,
                                                     "statement_out_of_scope": 1, "statement_pre_pipeline": 1}


def test_module_dimension_one_module_common_and_multi_module_copy(tmp_path):
    usage = usage_file(tmp_path, BROWN, scope=True, modules=MODULES)
    path = init(tmp_path, "--common-module", "common", usage=usage)
    data = load_yaml(path)
    assert data["modules"] == MODULES and data["common_module"] == "common"
    it = items(path)
    trim = it["com.legacy.common.util.StrUtil#trimAll/1"]          # user 모듈 slice 둘만 쓴다
    assert (trim["owner"], trim["module"], trim.get("copy")) == ("common", "user", None)
    phone = it["com.legacy.common.util.StrUtil#formatPhone/1"]     # user·admin 이 쓴다 → 모듈별 복사가 기본
    assert (phone["owner"], phone["module"], phone["copy"]) == ("common", ["admin", "user"], True)
    code = it["common.selectCode"]
    assert (code["module"], code["copy"]) == (["admin", "user"], True)
    assert it["member.selectMember"]["module"] == "user"
    _decide(path, **BROWN_REVIEW_DONE)
    assert cc.validate(load_yaml(path)) == []
    # 전 모듈 기반(인증·권한)은 사람이 common_module 로 올린다
    auth = "com.legacy.common.util.StrUtil#checkAuth/1"
    _decide(path, **{auth: {"module": "common", "copy": False}})
    assert cc.validate(load_yaml(path)) == []
    # 잘못된 결정은 거부: 여러 모듈이 쓰는데 한 모듈 공통으로, 목록인데 copy 없음
    _decide(path, **{auth: {"module": "user"}})
    assert any("다른 모듈(admin)도 쓴다" in e for e in cc.validate(load_yaml(path)))
    _decide(path, **{auth: {"module": ["admin", "user"], "copy": False}})
    assert any("copy: true" in e for e in cc.validate(load_yaml(path)))
    # 사람의 모듈 결정은 init 을 다시 돌려도 보존된다
    _decide(path, **{auth: {"module": "common", "copy": False}})
    cc.main(["--contract", path, "init", "--usage", usage, "--out", path, "--common-module", "common"])
    assert items(path)[auth]["module"] == "common" and not items(path)[auth].get("copy")


def test_contract_without_modules_is_unchanged(tmp_path):
    """config 에 modules 가 없으면 module·copy 필드를 만들지 않는다 (하위 호환)."""
    data = load_yaml(init(tmp_path, usage=usage_file(tmp_path, BROWN, scope=True)))
    assert "modules" not in data
    assert not any("module" in i or "copy" in i for i in data["items"])


def test_not_migrated_item_can_be_promoted_by_human(tmp_path):
    """목록 파일에서 사람이 owner 를 바꾸면 다음 init 이 계약 항목으로 올리고 승인을 해제한다."""
    path = init(tmp_path)
    cc.main(["--contract", path, "approve", "--by", "홍길동"])
    nm_path = cc.not_migrated_path(path)
    nm = load_yaml(nm_path)
    for e in nm["items"]:
        if e["asis"] == "com.legacy.common.dao.CommonDAO#selectDynamic/1":
            e.update({"owner": "common", "decision": "계승", "decided_by": "홍길동"})
    with open(nm_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(nm, f, allow_unicode=True, sort_keys=False)
    cc.main(["--contract", path, "init", "--usage", usage_file(tmp_path), "--out", path])
    it = items(path)["com.legacy.common.dao.CommonDAO#selectDynamic/1"]
    assert (it["owner"], it["status"], it["decided_by"]) == ("common", "pending", "홍길동")
    assert "com.legacy.common.dao.CommonDAO#selectDynamic/1" not in not_migrated(path)
    assert load_yaml(path)["approved"] is False
    assert cc.validate(load_yaml(path)) == []


def test_moving_common_to_slice_needs_human_and_single_user(tmp_path):
    path = init(tmp_path)
    _decide(path, **REVIEW_DONE)
    _decide(path, **{"com.legacy.common.base.BaseService#calcOffset/2": {"owner": "slice:loan"}})
    errs = cc.validate(load_yaml(path))
    assert any("다른 업무도 쓴다" in e for e in errs)     # deposit 도 쓰므로 loan 으로 내릴 수 없다
    _decide(path, **{"com.legacy.common.base.BaseService#calcOffset/2": {"owner": "common"},
                     "com.legacy.common.util.CommonUtil#maskName/1": {"owner": "slice:deposit"}})
    assert any("decided_by" in e for e in cc.validate(load_yaml(path)))
    _decide(path, **{"com.legacy.common.util.CommonUtil#maskName/1": {"owner": "slice:deposit", "decided_by": "홍길동"}})
    assert cc.validate(load_yaml(path)) == []


def test_reinit_preserves_human_decisions_and_ids(tmp_path):
    path = init(tmp_path)
    _decide(path, **REVIEW_DONE)
    _decide(path, **{"com.legacy.common.util.CommonUtil#formatDate/1": {"tobe": "com.ex.common.DateUtils#formatDate",
                                                                         "decision": "대체"}})
    cc.main(["--contract", path, "approve", "--by", "홍길동"])
    before = items(path)
    cc.main(["--contract", path, "init", "--usage", usage_file(tmp_path), "--out", path])
    after = items(path)
    assert {k: v["id"] for k, v in before.items()} == {k: v["id"] for k, v in after.items()}
    assert after["com.legacy.common.util.CommonUtil#formatDate/1"]["decision"] == "대체"
    assert load_yaml(path)["approved"] is True        # 항목 변화가 없으면 승인 유지


def test_reinit_keeps_ported_fields_extra_keys_and_note_tail_once(tmp_path):
    """재현: 이관(ported)된 항목의 스키마 밖 필드(tobe_location)·사람이 정한 module·note 꼬리말이
    init 재실행으로 지워지거나 중복되던 결함. init 을 두 번 돌려도 필드는 그대로, 꼬리말은 1회."""
    usage = usage_file(tmp_path, BROWN, scope=True, modules=MODULES)
    path = init(tmp_path, "--common-module", "common", usage=usage)
    _decide(path, **BROWN_REVIEW_DONE)
    trim = "com.legacy.common.util.StrUtil#trimAll/1"
    _decide(path, **{trim: {"status": "ported", "tobe": "com.ex.common.StrUtil#trimAll",
                            "tobe_location": "common/StrUtil.java 주석 블록", "owner_memo": "추가 필드"}})
    # 도달 slice 가 없는(이관 안 함 목록) 항목을 사람이 공통으로 올려 이관까지 끝낸 상태
    nm_asis = sorted(not_migrated(path))[0]
    nm = not_migrated(path)[nm_asis]
    data = load_yaml(path)
    tail = " [행렬: 도달 slice 없음 — 이관 안 함 제안]"
    data["items"].append({"id": "CC-0999", "kind": nm["kind"], "asis": nm_asis, "file": nm["file"], "line": nm["line"],
                          "used_by": [], "usage": {}, "suggestion": "none", "owner": "common", "decision": "계승",
                          "decided_by": "홍길동", "module": "user", "status": "ported", "tobe": "x",
                          "tobe_location": "mapper 주석 블록", "note": "사람 메모" + tail})
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    for _ in range(2):
        assert cc.main(["--contract", path, "init", "--usage", usage, "--out", path, "--common-module", "common"]) == 0
    it = items(path)
    t = it[trim]
    assert (t["status"], t["tobe"], t["tobe_location"], t["owner_memo"], t["module"]) == (
        "ported", "com.ex.common.StrUtil#trimAll", "common/StrUtil.java 주석 블록", "추가 필드", "user")
    n = it[nm_asis]
    assert (n["id"], n["owner"], n["module"], n["status"], n["tobe_location"], n["decided_by"]) == (
        "CC-0999", "common", "user", "ported", "mapper 주석 블록", "홍길동")
    assert n["note"].count(tail.strip()) == 1
    assert not any(i.get("stale") for i in it.values())


# ---------------------------------------------------------------- 복제·침범 검출 (TO-BE)

def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return rel


LOAN_WITH_PRIVATE_COPY = """package com.ex.loan;

/** 대출 서비스 */
public class LoanService {

    /** 대출 번호 포맷 */
    public String loanNo(String raw) {
        return pad(raw, 8);
    }

    // 공통 CommonUtil.padLeft 를 이관하지 않고 private 으로 복제 (실측된 문제 행동)
    private String pad(String value, int width) {
        String out = value;
        while (out.length() < width) { out = "0" + out; }
        return out;
    }
}
"""

LOAN_CALLING_COMMON = """package com.ex.loan;

import com.ex.common.util.StringUtils;

/** 대출 서비스 */
public class LoanService {

    /** 대출 번호 포맷 */
    public String loanNo(String raw) {
        return StringUtils.padLeft(raw, 8);
    }
}
"""


def contract_data(tmp_path):
    path = init(tmp_path)
    _decide(path, **REVIEW_DONE)
    return load_yaml(path)


def test_private_copy_of_common_method_is_blocked(tmp_path):
    td = str(tmp_path / "target")
    f = write(td, "backend/loan/src/main/java/com/ex/loan/LoanService.java", LOAN_WITH_PRIVATE_COPY)
    out = cc.integrity_findings("loan", [f], td, contract_data(tmp_path), LEGACY)
    fails = [x for x in out if x[0] == "FAIL"]
    assert len(fails) == 1 and "padLeft" in fails[0][2] and "공통 복제" in fails[0][2]



def test_test_sources_are_not_checked_for_common_copies(tmp_path):
    # 테스트 fixture·도우미가 짧은 공통 메서드와 우연히 닮는 오탐(실측) - 테스트 소스는 복제 대상이 아니다
    td = str(tmp_path / "target")
    f = write(td, "backend/loan/src/test/java/com/ex/loan/LoanServiceTest.java", LOAN_WITH_PRIVATE_COPY)
    out = cc.integrity_findings("loan", [f], td, contract_data(tmp_path), LEGACY)
    assert [x for x in out if x[0] == "FAIL"] == []

PHONE_COPY = """package com.ex.{mod}.{pkg};

/** {cls} */
public class {cls} {{

    /** 전화번호 형식 */
    public static String phone(String raw) {{
        String digits = raw.replace("-", "");
        return digits.substring(0, 3) + "-" + digits.substring(3, 7) + "-" + digits.substring(7);
    }}
}}
"""

TRIM_COPY = """package com.ex.user.board;

/** 게시판 */
public class BoardHelper {

    /** 공백 제거 */
    public static String clean(String text) {
        if (text == null) { return ""; }
        return text.replace(" ", "").replace("\\t", "");
    }
}
"""

MODULE_PATHS = {"user": ["server/user"], "admin": ["server/admin"]}


def module_contract(tmp_path):
    path = init(tmp_path, "--common-module", "common", usage=usage_file(tmp_path, BROWN, scope=True, modules=MODULES))
    _decide(path, **BROWN_REVIEW_DONE)
    return load_yaml(path)


def test_module_copy_approved_in_contract_is_not_a_duplicate(tmp_path):
    """copy: true 로 승인된 공통의 모듈 복사본은 복제 결함이 아니다 (모듈 간에는 공유하지 않고 복사하는 규약)."""
    td = str(tmp_path / "target")
    data = module_contract(tmp_path)
    f = write(td, "server/admin/src/main/java/com/ex/admin/member/AdminPhone.java",
              PHONE_COPY.format(mod="admin", pkg="member", cls="AdminPhone"))
    assert cc.integrity_findings("adminmember", [f], td, data, BROWN, "admin", MODULE_PATHS) == []
    # 모듈을 모르면(모듈 차원 없음) 종전대로 복제로 본다
    assert [x[0] for x in cc.integrity_findings("adminmember", [f], td, data, BROWN)] == ["FAIL"]


def test_second_copy_in_same_module_is_blocked(tmp_path):
    """같은 모듈 안에 복사본이 이미 있으면 업무 slice 간 복제다 — 기존 복사본을 호출해야 한다."""
    td = str(tmp_path / "target")
    data = module_contract(tmp_path)
    write(td, "server/user/src/main/java/com/ex/user/member/MemberPhone.java",
          PHONE_COPY.format(mod="user", pkg="member", cls="MemberPhone"))
    f = write(td, "server/user/src/main/java/com/ex/user/board/BoardPhone.java",
              PHONE_COPY.format(mod="user", pkg="board", cls="BoardPhone"))
    out = cc.integrity_findings("board", [f], td, data, BROWN, "user", MODULE_PATHS)
    assert [x[0] for x in out] == ["FAIL"] and "같은 모듈 안 복제" in out[0][2] and "MemberPhone" in out[0][2]
    # 다른 모듈(admin)의 복사본은 같은 모듈이 아니므로 막지 않는다
    g = write(td, "server/admin/src/main/java/com/ex/admin/member/AdminPhone.java",
              PHONE_COPY.format(mod="admin", pkg="member", cls="AdminPhone"))
    assert cc.integrity_findings("adminmember", [g], td, data, BROWN, "admin", MODULE_PATHS) == []


def test_copy_of_single_module_common_is_still_blocked(tmp_path):
    """한 모듈의 공통(copy 아님)을 같은 모듈 업무 slice 가 복제하면 종전대로 차단한다."""
    td = str(tmp_path / "target")
    data = module_contract(tmp_path)
    f = write(td, "server/user/src/main/java/com/ex/user/board/BoardHelper.java", TRIM_COPY)
    out = cc.integrity_findings("board", [f], td, data, BROWN, "user", MODULE_PATHS)
    assert [x[0] for x in out] == ["FAIL"] and "trimAll" in out[0][2] and "공통 복제" in out[0][2]


def test_calling_common_is_allowed(tmp_path):
    td = str(tmp_path / "target")
    f = write(td, "backend/loan/src/main/java/com/ex/loan/LoanService.java", LOAN_CALLING_COMMON)
    assert cc.integrity_findings("loan", [f], td, contract_data(tmp_path), LEGACY) == []


def test_slice_editing_common_module_is_blocked_but_porter_is_allowed(tmp_path):
    td = str(tmp_path / "target")
    f = write(td, "backend/common/src/main/java/com/example/common/util/StringUtils.java",
              "package com.example.common.util;\n/** x */\npublic class StringUtils {}\n")
    data = contract_data(tmp_path)
    assert [x[0] for x in cc.integrity_findings("loan", [f], td, data, LEGACY)] == ["FAIL"]
    assert cc.integrity_findings("common-port", [f], td, data, LEGACY) == []


def test_duplicated_shared_mapper_statement_is_blocked(tmp_path):
    td = str(tmp_path / "target")
    write(td, "backend/common/src/main/resources/mapper/common/CommonCodeMapper.xml",
          '<mapper namespace="com.example.common.CommonCodeMapper">\n'
          '  <!-- 공통 코드 조회 -->\n  <select id="selectCode" resultType="map">\n'
          '    SELECT cd, cd_nm FROM tb_code WHERE grp_cd = #{groupCd} ORDER BY sort_no\n  </select>\n</mapper>\n')
    f = write(td, "backend/loan/src/main/resources/mapper/loan/LoanMapper.xml",
              '<mapper namespace="com.ex.loan.LoanMapper">\n'
              '  <select id="selectLoanCodes" resultType="map">\n'
              '    SELECT CD, CD_NM FROM TB_CODE WHERE GRP_CD = #{grp} ORDER BY SORT_NO\n  </select>\n</mapper>\n')
    out = cc.integrity_findings("loan", [f], td, contract_data(tmp_path), LEGACY)
    assert [x[0] for x in out] == ["FAIL"] and "SQL 복제" in out[0][2]


def test_common_port_fulfillment(tmp_path):
    td = str(tmp_path / "target")
    data = contract_data(tmp_path)
    missing = cc.fulfillment_findings(td, data)
    assert missing and all(x[0] == "FAIL" for x in missing)
    # 공통 항목 하나만 남기고 tobe 를 채워 구현
    keep = "com.legacy.common.util.CommonUtil#padLeft/2"
    for i in data["items"]:
        if i["owner"] == "common" and i["asis"] != keep:
            i["owner"] = "discard"
            i["used_by"] = []
        if i["asis"] == keep:
            i["tobe"] = "com.example.common.util.StringUtils#padLeft"
    assert [x[2] for x in cc.fulfillment_findings(td, data)][0].startswith("tobe com.example")
    write(td, "backend/common/src/main/java/com/example/common/util/StringUtils.java",
          "package com.example.common.util;\n/** 문자열 */\npublic class StringUtils {\n"
          "    /** 왼쪽 0 채움 */\n    public static String padLeft(String s, int len) { return s; }\n}\n")
    assert cc.fulfillment_findings(td, data) == []


def test_common_request_is_numbered_safely(sandbox):
    for i in range(3):
        sandbox.run("common_contract.py", "request", "--slice", "loan", "--asis", f"X#m{i}/0", "--reason", "필요", check=0)
    d = os.path.join(sandbox.ws, "common-requests")
    assert sorted(os.listdir(d))[:3] == ["CR-0001.yaml", "CR-0002.yaml", "CR-0003.yaml"]


# ---------------------------------------------------------------- /run 계획에 공통 선행 변환이 들어가는가

def _plan(sandbox):
    import json as _json
    return _json.loads(sandbox.run("gate.py", "plan", "--to", "5", "--max", "8", "--format", "json", check=0).stdout)


def test_run_plan_orders_common_port_before_business_slices(sandbox, tmp_path):
    import shutil
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(LEGACY, "slices.yaml"), os.path.join(sandbox.ws, "slices", "slices.yaml"))
    state = {"iteration": 1, "stages": {"stage1_slicing": "done", "stage2_scaffold": "done"}, "slices": {}}
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    shutil.copy(str(tmp_path / "s.yaml"), os.path.join(sandbox.ws, "state" + ".yaml"))
    sandbox.write_config(f"  mode: migration\nasis:\n  source_dir: {LEGACY}\n")
    assert any("공통 계약이 없다" in s for s in _plan(sandbox)["stops"])
    # 계약 생성 → 미승인이면 멈춤
    out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
    cc.main(["--contract", out, "init", "--usage", usage_file(tmp_path), "--out", out])
    assert any("approved=false" in s for s in _plan(sandbox)["stops"])
    # 사람 결정·승인 후에는 공통 선행 변환이 업무 slice 보다 먼저
    _decide(out, **REVIEW_DONE)
    data = load_yaml(out)
    data["approved"] = True
    (tmp_path / "c.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    shutil.copy(str(tmp_path / "c.yaml"), out)
    cmds = [s["command"] for s in _plan(sandbox)["steps"]]
    assert cmds.index("/stage2 common-port") < cmds.index("/stage2 all")


def test_same_arity_overloads_get_distinct_stable_ids():
    # 실측: 같은 이름·같은 인자 수 오버로드 47건이 같은 asis 로 겹쳐 init 마다 id 가 흔들렸다
    its = [{"kind": "method", "asis": "a.Util#getMap/2", "signature": "public static Map getMap(String k, Map<String, Object> m)", "file": "Util.java"},
           {"kind": "method", "asis": "a.Util#getMap/2", "signature": "public static Map getMap(Map m, String k)", "file": "Util.java"},
           {"kind": "method", "asis": "a.Util#other/1", "signature": "void other(int x)", "file": "Util.java"},
           {"kind": "method", "asis": "a.Dup#run/0", "signature": "void run()", "file": "src/a/Dup.java"},
           {"kind": "method", "asis": "a.Dup#run/0", "signature": "void run()", "file": "doc/Dup.java"}]
    cc.disambiguate_overloads(its)
    got = [i["asis"] for i in its]
    assert got[0] == "a.Util#getMap(String,Map<String,Object>)"
    assert got[1] == "a.Util#getMap(Map,String)"
    assert got[2] == "a.Util#other/1"            # 겹치지 않으면 그대로 (기존 계약과 계속 맞는다)
    assert got[3] != got[4] and len(set(got)) == 5   # 타입까지 같으면 파일로 구분


def test_slice_may_add_migration_inside_common_module(tmp_path):
    # 실측: brownfield 에서 Flyway 폴더가 공통 모듈(server/common) 안에 있어 DDL 이 있는 slice 가 전부 공통 침범으로 FAIL 했다
    data = {"tobe": {"common_module": "server/common", "common_package": "com.acme.common"}, "items": []}
    mig = "server/common/src/main/resources/db/migration/400_tobe_ddl/V1_1_401__order_table.sql"
    code = "server/common/src/main/java/com/acme/common/util/DateUtil.java"
    out = cc.integrity_findings("order", [mig, code], str(tmp_path), data, None)
    flagged = {f for _lvl, f, *_ in out}
    assert mig not in flagged
    assert code in flagged


def test_not_needed_replacement_is_fulfilled_only_for_replace_with_reason(tmp_path):
    # 실측: 서버 렌더링·팝업 리다이렉트 같은 AS-IS 기능은 REST 전환으로 대응이 없어 대체 35건을 표현할 수 없었다
    base = {"id": "CC-1", "kind": "method", "asis": "a.Base#popup/1", "owner": "common", "status": "pending",
            "used_by": ["order"]}
    ok = dict(base, decision="대체", tobe="불필요: REST 전환으로 팝업 리다이렉트가 화면(FE) 몫")
    bad_decision = dict(base, id="CC-2", asis="a.Base#b/1", decision="계승", tobe="불필요: 사유")
    bad_reason = dict(base, id="CC-3", asis="a.Base#c/1", decision="대체", tobe="불필요:")
    data = {"items": [ok, bad_decision, bad_reason]}
    errs = cc.validate(data)
    assert not any(e.startswith("CC-1:") for e in errs)
    assert any(e.startswith("CC-2:") for e in errs) and any(e.startswith("CC-3:") for e in errs)
    out = cc.fulfillment_findings(str(tmp_path), {"items": [ok]})
    assert out == []


def test_empty_module_share_of_replaced_item_is_not_fulfilled(tmp_path):
    # 실측: copy 가 아닌 대체 항목의 dict tobe 에서 쓰는 모듈(user) 몫이 비어도 이행 검사를 통과했다
    it = {"id": "CC-1", "kind": "method", "asis": "a.Base#isAdmin/0", "owner": "common", "decision": "대체",
          "module": "common", "modules": ["admin", "user"], "status": "pending",
          "tobe": {"admin": "불필요: 사유가 있는 대체", "user": ""}}
    out = cc.fulfillment_findings(str(tmp_path), {"items": [it]})
    assert any("user" in msg for _lvl, _id, msg, *_ in out)


def test_statement_replaced_by_java_port_method_is_checked_in_java(tmp_path):
    # 실측: 외부 DB statement 를 Mapper 가 아니라 Java 포트 인터페이스 메서드로 대체했는데 Mapper 에서만 찾아 미이행으로 나왔다
    src = tmp_path / "app" / "src" / "main" / "java" / "com" / "ex"
    src.mkdir(parents=True)
    (src / "ExtPort.java").write_text(
        "package com.ex;\npublic interface ExtPort {\n    int updateDlp(java.util.Map<String, Object> m);\n}\n",
        encoding="utf-8")
    base = {"kind": "statement", "owner": "common", "decision": "대체", "status": "ported", "used_by": ["order"]}
    ok = dict(base, id="CC-1", asis="ext.updateDlp", tobe="com.ex.ExtPort#updateDlp")
    missing = dict(base, id="CC-2", asis="ext.selectDlp", tobe="com.ex.ExtPort#selectDlp")
    out = cc.fulfillment_findings(str(tmp_path), {"items": [ok, missing]})
    assert [x[1] for x in out] == ["CC-2"]
    assert "찾지 못했다" in out[0][2]


# ------------------------------------------------- 외부 확정 계약 (공통 선행 변환이 파이프라인 밖에서 끝난 경우, BG-07)

def external_doc(**over):
    d = {"schema": 1, "status": "external", "source": "target_dir docs/pipeline/CONVENTIONS.md 5-1·5-4~5-7",
         "numbering": "CC-0028~CC-1473", "evidence": "docs/pipeline/BRANCH_NOTE.md 완료 내역 표 · dev3 fd0f5f76",
         "decided_by": "사람:홍길동", "items": [], "approved": False}
    d.update(over)
    return d


def test_external_contract_requires_source_numbering_evidence_and_human(tmp_path):
    """검출 방향과 미검출 방향을 둘 다 본다 (pipeline-core §14-10)."""
    assert cc.validate(external_doc()) == []                       # 제대로 채운 것은 통과
    for bad, want in ((external_doc(source=""), "source"),
                      (external_doc(numbering=""), "numbering"),
                      (external_doc(evidence=""), "evidence"),
                      (external_doc(decided_by=""), "decided_by"),
                      (external_doc(decided_by="에이전트:orchestrator"), "사람:"),
                      (external_doc(items=[{"id": "CC-0001"}]), "items")):
        errs = cc.validate(bad)
        assert any(want in e for e in errs), (bad, errs)


def test_external_cli_declares_and_refuses_to_overwrite_item_contract(tmp_path):
    out = str(tmp_path / "c.yaml")
    assert cc.main(["--contract", out, "external", "--source", "CONVENTIONS.md 5절",
                    "--numbering", "CC-0028~CC-1473", "--evidence", "BRANCH_NOTE.md",
                    "--by", "사람:홍길동"]) == 0
    d = load_yaml(out)
    assert d["status"] == "external" and d["items"] == [] and d["approved"] is False
    # 항목이 있는 계약을 덮어쓰지 않는다
    init(tmp_path, usage=usage_file(tmp_path), )
    item_out = str(tmp_path / "common-contract.yaml")
    try:
        cc.main(["--contract", item_out, "external", "--source", "x", "--numbering", "y",
                 "--evidence", "z", "--by", "사람:홍길동"])
        raise AssertionError("항목이 있는 계약을 덮어썼다")
    except SystemExit as ex:
        assert "덮어쓰지 않는다" in str(ex)


def test_external_contract_unblocks_plan_without_common_port(sandbox, tmp_path):
    """외부 확정 계약이면 공통 선행 변환 단계를 넣지 않고, 계약 없음으로 멈추지도 않는다."""
    import shutil
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(LEGACY, "slices.yaml"), os.path.join(sandbox.ws, "slices", "slices.yaml"))
    state = {"iteration": 1, "stages": {"stage1_slicing": "done", "stage2_scaffold": "done",
                                        "stage2_common_port": "skipped"}, "slices": {}}
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    shutil.copy(str(tmp_path / "s.yaml"), os.path.join(sandbox.ws, "state.yaml"))
    sandbox.write_config(f"  mode: migration\nasis:\n  source_dir: {LEGACY}\n")
    out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 미승인 외부 계약은 여전히 멈춘다 (승인은 사람 몫)
    (tmp_path / "e.yaml").write_text(yaml.safe_dump(external_doc(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    shutil.copy(str(tmp_path / "e.yaml"), out)
    assert any("approved=false" in s for s in _plan(sandbox)["stops"])

    # 승인하면 계약 관련 멈춤이 사라지고 common-port 단계도 들어가지 않는다
    (tmp_path / "e2.yaml").write_text(yaml.safe_dump(external_doc(approved=True), allow_unicode=True, sort_keys=False), encoding="utf-8")
    shutil.copy(str(tmp_path / "e2.yaml"), out)
    plan = _plan(sandbox)
    assert not any("공통 계약" in s for s in plan["stops"]), plan["stops"]
    assert "/stage2 common-port" not in [s["command"] for s in plan["steps"]]
    assert any("외부 확정" in n for n in plan["notes"])


def test_external_contract_gate_records_what_was_not_checked(sandbox):
    """통과로 넘기지 않고 '항목 단위 검사를 하지 않았다' 를 INFO 로 남긴다 (pipeline-core §23)."""
    import json as _json
    out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump(external_doc(approved=True), f, allow_unicode=True, sort_keys=False)
    sandbox.write_config("  mode: migration\n")
    rpt = sandbox.write_report("2610051100_stage2_notice_backend.md", dev_meta())
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = next(x for x in _json.loads(p.stdout)["results"] if x["hook"] == "common-integrity")
    assert r["result"] == "PASS"                                  # INFO 는 통과를 깎지 않는다
    sev = [f["severity"] for f in r["findings"]]
    assert sev == ["INFO"] and any("항목 단위 검사" in f["message"] for f in r["findings"])


# ------------------------------------------------- 외부 확정 계약에 더한 공통 (BG-07 후속)

def good_addition(**over):
    d = {"id": "CC-A001", "cr": "CR-0006", "kind": "method", "owner": "common", "decision": "개선",
         "asis": "", "tobe": "com.example.user.common.service.UserProfileCommonService#findProfile/1",
         "evidence": "신고채널 응답 3건이 사번만 담는다 — 화면은 이름이 필요하다", "judgment": "JD-0350",
         "status": "open"}
    d.update(over)
    return d


def test_external_contract_accepts_additions_only_with_cr_target_evidence_and_judgment():
    """외부가 확정한 경계를 넓히는 것은 판단이다 — 근거 없이 더할 수 없다.

    배경(실측): status: external 은 항목을 두지 않으므로, 업무 slice 를 만들다
    **그쪽에 없던 공통 수단**이 필요해지면(CR-0006) 등록할 자리가 없었다.
    그러면 17절("공통을 업무 안에 임시 구현하지 않는다")을 지켜도 그 공통이 어디 있어야 하는지
    계약이 말해 주지 못한다.
    """
    # 제대로 채운 것은 통과하고, 외부 확정 본문(items)은 여전히 비어 있어야 한다
    assert cc.validate(external_doc(additions=[good_addition()])) == []
    assert any("items" in e for e in cc.validate(
        external_doc(items=[{"id": "CC-0001"}], additions=[good_addition()])))

    for bad, want in ((good_addition(id="CC-0001"), "CC-A001 꼴"),      # 외부 번호 대역과 섞지 않는다
                      (good_addition(id="A1"), "CC-A001 꼴"),
                      (good_addition(cr=""), "cr"),
                      (good_addition(cr="CR-6"), "cr"),
                      (good_addition(owner="nobody"), "owner"),
                      (good_addition(decision=None), "decision"),      # owner=common 이면 필수
                      (good_addition(tobe=""), "target"),
                      (good_addition(evidence=""), "evidence"),
                      (good_addition(judgment=None), "judgment"),      # 판단도 사람 결정도 없다
                      (good_addition(judgment="JD-9"), "judgment"),
                      (good_addition(status="알수없음"), "status")):
        errs = cc.validate(external_doc(additions=[bad]))
        assert any(want in e for e in errs), (bad, errs)

    # judgment 대신 사람 결정이면 통과한다
    assert cc.validate(external_doc(
        additions=[good_addition(judgment=None, decided_by="사람:홍길동")])) == []
    # id 중복은 막는다
    assert any("중복" in e for e in cc.validate(
        external_doc(additions=[good_addition(), good_addition()])))
    # additions 가 없는 외부 확정 계약은 종전대로 통과한다 (뒤로 호환)
    assert cc.validate(external_doc()) == []


def test_addition_cli_numbers_in_its_own_band_and_records_fulfillment(tmp_path):
    out = str(tmp_path / "c.yaml")
    assert cc.main(["--contract", out, "external", "--source", "CONVENTIONS.md 5절",
                    "--numbering", "CC-0028~CC-1473", "--evidence", "BRANCH_NOTE.md",
                    "--by", "사람:홍길동"]) == 0
    args = ["--contract", out, "addition", "--cr", "CR-0006", "--owner", "common",
            "--decision", "개선", "--target", "com.example.user.common.service.P#find/1",
            "--evidence", "응답 3건이 사번만 담는다", "--judgment", "JD-0350"]
    assert cc.main(args) == 0
    assert cc.main(args[:3] + ["--cr", "CR-0007"] + args[5:]) == 0
    d = load_yaml(out)
    assert [it["id"] for it in d["additions"]] == ["CC-A001", "CC-A002"]
    assert d["items"] == []                      # 외부 확정 본문은 건드리지 않는다
    assert all(it["status"] == "open" for it in d["additions"])

    # 이행 기록
    assert cc.main(["--contract", out, "addition-done", "--id", "CC-A001", "--note", "공통에 만들었다"]) == 0
    d = load_yaml(out)
    hit = next(it for it in d["additions"] if it["id"] == "CC-A001")
    assert hit["status"] == "ported" and hit["resolution"] == "공통에 만들었다" and hit["resolved_at"]
    # 없는 번호는 막는다
    with pytest.raises(SystemExit):
        cc.main(["--contract", out, "addition-done", "--id", "CC-A099"])


def test_addition_cli_refuses_contract_that_is_not_external(tmp_path):
    out = str(tmp_path / "c.yaml")
    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump({"schema": 1, "items": [{"id": "CC-0001"}], "approved": True}, f)
    with pytest.raises(SystemExit) as ex:
        cc.main(["--contract", out, "addition", "--cr", "CR-0006", "--target", "X#y/1",
                 "--evidence", "e", "--judgment", "JD-0350", "--decision", "개선"])
    assert "external" in str(ex.value)


def test_gate_checks_our_additions_even_though_external_body_is_unchecked(sandbox):
    """외부 확정 본문은 검사할 수 없지만 **우리가 더한 공통**은 검사한다.

    둘을 섞어 "전부 검사 못 한다" 로 넘기면 우리가 더한 공통의 미이행이 가려진다.
    """
    import json as _json
    out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    def check(doc):
        with open(out, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        rpt = sandbox.write_report("2610061200_stage2_notice_backend.md", dev_meta())
        p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
        return next(x for x in _json.loads(p.stdout)["results"] if x["hook"] == "common-integrity")

    sandbox.write_config("  mode: migration\n")

    # (1) 더한 것이 없으면 종전대로 INFO 하나 (뒤로 호환)
    r = check(external_doc(approved=True))
    assert [f["severity"] for f in r["findings"]] == ["INFO"]
    assert len(r["findings"]) == 1

    # (2) 미이행(open)이면 경고로 드러난다 — "업무 안에 임시 구현하지 않는다" 를 안내한다
    r = check(external_doc(approved=True, additions=[good_addition()]))
    warns = [f for f in r["findings"] if f["severity"] == "WARN"]
    assert len(warns) == 1, r["findings"]
    assert "CC-A001" in warns[0]["message"] and "CR-0006" in warns[0]["message"]
    assert "임시 구현" in warns[0]["action"]
    # 몇 건을 검사했는지도 남긴다 — "검사하지 않았다" 와 섞이지 않게
    assert any(f["severity"] == "INFO" and "미이행 1" in f["message"] for f in r["findings"]), r["findings"]

    # (3) ported 라고 적었는데 target 에 없으면 미이행으로 막는다 (적었다고 통과시키지 않는다)
    r = check(external_doc(approved=True, additions=[good_addition(status="ported")]))
    assert any(f["severity"] == "FAIL" and "찾지 못했다" in f["message"] for f in r["findings"]), r["findings"]
    assert r["result"] == "FAIL"


def test_plan_adds_common_port_for_open_additions_only(sandbox, tmp_path):
    """외부 확정 본문은 common-port 를 돌리지 않지만, 우리가 더한 공통은 돌려야 한다."""
    import shutil
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(LEGACY, "slices.yaml"), os.path.join(sandbox.ws, "slices", "slices.yaml"))
    state = {"iteration": 1, "stages": {"stage1_slicing": "done", "stage2_scaffold": "done"}, "slices": {}}
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    shutil.copy(str(tmp_path / "s.yaml"), os.path.join(sandbox.ws, "state" + ".yaml"))
    sandbox.write_config("  mode: migration\n")
    out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    def plan(doc):
        with open(out, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        return _plan(sandbox)

    pl = plan(external_doc(approved=True))
    assert "/stage2 common-port" not in [s["command"] for s in pl["steps"]]

    pl = plan(external_doc(approved=True, additions=[good_addition()]))
    hit = [s for s in pl["steps"] if s["command"] == "/stage2 common-port"]
    assert len(hit) == 1 and "CR-0006" in hit[0]["note"], pl["steps"]

    # 이행이 끝나면 다시 들어가지 않는다
    pl = plan(external_doc(approved=True, additions=[good_addition(status="ported")]))
    assert "/stage2 common-port" not in [s["command"] for s in pl["steps"]]



def test_commented_statement_is_not_a_live_port(tmp_path):
    # XML 주석 안의 statement 는 계약 이행이 아니다 - note 에 '주석 이관' 이 있을 때만 통과한다
    td = str(tmp_path / "t")
    write(td, "server/src/main/resources/mapper/X.xml",
          '<mapper namespace="m.X">\n<!-- [AS-IS 원문]\n<update id="dead">UPDATE T SET A=1</update>\n-->\n</mapper>\n')
    item = {"id": "CC-9", "kind": "statement", "asis": "x.dead", "owner": "common", "tobe": "m.X.dead", "status": "ported"}
    data = {"items": [item]}
    out = cc.fulfillment_findings(td, data)
    assert out and "주석 안에만" in out[0][2]
    item["note"] = "주석 이관 JD-0589"
    assert cc.fulfillment_findings(td, data) == []


SHARED_STMT = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="{ns}">
  <select id="{sid}" resultType="map">
    SELECT emp_no, emp_name, dept_code, dept_name FROM v_ext_user WHERE emp_no = #{{empNo}} AND use_yn = 'Y' ORDER BY emp_no
  </select>
</mapper>
"""


def test_shared_mapper_dirs_accepts_list_and_glob(tmp_path):
    # 다중 데이터소스: 공통 statement 가 데이터소스별 폴더에 나뉘어 있다(실측: 폴더 하나만 보아 외부 공통 statement 복제를 놓침)
    td = str(tmp_path / "target")
    write(td, "res/mapper/common/A.xml", SHARED_STMT.format(ns="a", sid="x"))
    write(td, "res/mapper-ds2/common/B.xml", SHARED_STMT.format(ns="b", sid="y"))
    write(td, "res/mapper-ds3/common/C.xml", SHARED_STMT.format(ns="c", sid="z"))
    assert cc.shared_mapper_dirs({"shared_mapper_dir": "res/mapper/common"}, td) == ["res/mapper/common"]
    got = cc.shared_mapper_dirs({"shared_mapper_dir": ["res/mapper/common", "res/mapper-ds*/common", "res/없음"]}, td)
    assert got == ["res/mapper/common", "res/mapper-ds2/common", "res/mapper-ds3/common"]


def test_business_copy_of_external_common_statement_is_blocked(tmp_path):
    td = str(tmp_path / "target")
    write(td, "res/mapper-ds2/common/ExtUser.xml", SHARED_STMT.format(ns="ext", sid="selectUser"))
    f = write(td, "res/mapper/loan/LoanMapper.xml", SHARED_STMT.format(ns="loan", sid="selectLoanUser"))
    data = contract_data(tmp_path)
    data.setdefault("tobe", {})["shared_mapper_dir"] = "res/mapper/common"
    assert [x for x in cc.integrity_findings("loan", [f], td, data, LEGACY) if "SQL 복제" in x[2]] == []
    data["tobe"]["shared_mapper_dir"] = ["res/mapper/common", "res/mapper-ds*/common"]
    fails = [x for x in cc.integrity_findings("loan", [f], td, data, LEGACY) if "SQL 복제" in x[2]]
    assert len(fails) == 1 and "ExtUser.xml:selectUser" in fails[0][2]
