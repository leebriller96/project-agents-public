# common_contract.py — 공통 계약 초안·사람 결정 보존·승인 조건·공통 복제/소유 침범 검출
import os
import sys

import yaml

from conftest import FIXTURES, REPO

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
