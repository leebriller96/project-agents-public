# common_usage.py — 공통 메서드·statement 를 어느 업무가 쓰는지 정확히(결정적으로) 계산하는지
# 레거시 예제(tests/fixtures/legacy): 대출(loan)·예금(deposit) 업무가 공통 유틸·상위 서비스·공통 DAO·공통 Mapper 를
# 서로 다른 조합으로 쓴다 — 실제로 겪은 "공통 클래스가 업무별로 쪼개지는" 상황의 축소판.
import json
import os
import subprocess
import sys

from conftest import FIXTURES, REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import common_usage  # noqa: E402
from _common import load_yaml  # noqa: E402

LEGACY = os.path.join(FIXTURES, "legacy")


def result():
    slices = load_yaml(os.path.join(LEGACY, "slices.yaml"))["slices"]
    return common_usage.analyze(LEGACY, slices)


def methods(r):
    return {f"{c['class'].rsplit('.', 1)[-1]}#{m['id']}": m["used_by"] for c in r["common_classes"] for m in c["methods"]}


def test_method_level_usage_matches_ground_truth():
    assert methods(result()) == {
        # 정적 유틸 — 오버로드는 인자 수로 구분, 내부 호출(padLeft)은 전이로 잡는다
        "CommonUtil#formatDate/1": {"loan": "direct"},
        "CommonUtil#padLeft/2": {"loan": "via:CommonUtil#formatDate/1"},
        "CommonUtil#calcInterest/2": {"loan": "direct"},
        "CommonUtil#calcInterest/3": {"deposit": "direct"},
        "CommonUtil#maskName/1": {"deposit": "direct"},
        "CommonUtil#unusedLegacy/0": {},
        # 상속 — m(), this.m(), super.m() 모두 상위 클래스 메서드로 해석
        "BaseService#getLoginUserId/1": {"loan": "inherited"},
        "BaseService#writeAudit/1": {"loan": "inherited"},
        "BaseService#calcOffset/2": {"deposit": "inherited", "loan": "inherited"},
        "BaseService#isHoliday/1": {"deposit": "inherited"},
        # 상위 클래스에 선언된 필드(commonDAO)의 타입으로 호출 대상 해석
        "CommonDAO#selectCode/1": {"loan": "direct"},
        "CommonDAO#selectHoliday/1": {"deposit": "via:BaseService#isHoliday/1"},
        "CommonDAO#insertAudit/1": {"loan": "via:BaseService#writeAudit/1"},
        "CommonDAO#selectDynamic/1": {},
    }


def test_class_level_usage_records_inheritance():
    by_class = {c["class"].rsplit(".", 1)[-1]: c["used_by"] for c in result()["common_classes"]}
    assert by_class["BaseService"] == {"deposit": "extends:DepositService", "loan": "extends:LoanService"}


def test_statement_and_fragment_usage():
    r = result()
    st = {s["id"]: (s["namespace_owner"], s["used_by"]) for s in r["statements"] + r["fragments"]}
    assert st["common.selectCode"] == (None, {"loan": "via:CommonDAO#selectCode/1"})
    assert st["common.selectHoliday"] == (None, {"deposit": "via:CommonDAO#selectHoliday/1"})
    assert st["common.selectUnused"] == (None, {})
    assert st["deposit.selectBaseRate"] == ("deposit", {"loan": "direct"})
    # 공통 SQL 조각은 두 업무가 statement 를 통해 공유
    assert st["common.pagingHead"][1] == {"deposit": "via:deposit.selectDepositList", "loan": "via:loan.selectLoanList"}
    assert st["deposit.depositCols"] == ("deposit", {"deposit": "via:deposit.selectDepositList"})


def test_cross_slice_and_unresolved_are_reported_not_guessed():
    r = result()
    assert r["cross_slice"] == [{"from": "loan", "kind": "statement", "to": "deposit", "what": "deposit.selectBaseRate"}]
    assert [(u["call"], u["slice"]) for u in r["unresolved"]] == [("sqlSession.selectOne(queryId)", None)]


def test_output_is_deterministic(sandbox):
    a = json.dumps(result(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(result(), ensure_ascii=False, sort_keys=True)
    assert a == b
    # CLI 는 config 를 읽는다 - 저장소의 실제 config(예: project.modules)에 결과가 흔들리지 않도록 격리 환경에서 실행한다
    cli = subprocess.run(sandbox.cmd("common_usage.py", "--source", LEGACY,
                                     "--slices", os.path.join(LEGACY, "slices.yaml"), "--format", "json"),
                         cwd=sandbox.root, capture_output=True, text=True, encoding="utf-8",
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert json.loads(cli.stdout)["summary"] == result()["summary"]


def test_mybatis_mapper_interface_calls_map_to_statements(tmp_path):
    """Mapper 인터페이스 방식(namespace = 인터페이스 FQN)도 statement 사용으로 잡는다."""
    java = tmp_path / "src/main/java/com/x"
    (java / "common").mkdir(parents=True)
    (java / "order").mkdir(parents=True)
    (java / "common/CodeMapper.java").write_text(
        "package com.x.common;\npublic interface CodeMapper {\n    java.util.List<String> selectCodes(String g);\n}\n", encoding="utf-8")
    (java / "order/OrderService.java").write_text(
        "package com.x.order;\nimport com.x.common.CodeMapper;\npublic class OrderService {\n"
        "    private CodeMapper codeMapper;\n    public void run() { codeMapper.selectCodes(\"A\"); }\n}\n", encoding="utf-8")
    xml = tmp_path / "src/main/resources/mapper"
    xml.mkdir(parents=True)
    (xml / "CodeMapper.xml").write_text(
        '<mapper namespace="com.x.common.CodeMapper">\n<select id="selectCodes">SELECT 1</select>\n</mapper>\n', encoding="utf-8")
    r = common_usage.analyze(str(tmp_path), [{"id": "order", "asis": {"packages": ["com.x.order"]}}])
    st = {s["id"]: s["used_by"] for s in r["statements"]}
    assert st["com.x.common.CodeMapper.selectCodes"] == {"order": "direct"}


def test_framework_entry_points_are_not_unused(tmp_path):
    """@Bean·@GetMapping·main·접근자처럼 프레임워크가 호출하는 메서드는 폐기 후보(미사용)로 세지 않는다."""
    d = tmp_path / "src/main/java/com/x/common"
    d.mkdir(parents=True)
    (d / "WebConfig.java").write_text(
        "package com.x.common;\n@Configuration\npublic class WebConfig {\n"
        "    private String name;\n"
        "    @Bean\n    public Object resolver() { return null; }\n"
        "    public String getName() { return name; }\n"
        "    public static void main(String[] a) { }\n"
        "    String dead() { return \"\"; }\n}\n", encoding="utf-8")
    r = common_usage.analyze(str(tmp_path), [])
    entry = {m["id"]: m["entry"] for c in r["common_classes"] for m in c["methods"]}
    assert entry == {"resolver/0": "@Bean", "getName/0": "accessor", "main/1": "main", "dead/0": None}
    assert r["summary"]["methods_unused"] == 1 and r["summary"]["methods_entry_only"] == 3


# ---------------------------------------------------------------- brownfield: 범위 제외·모듈·업무 소유 미사용

BROWN = os.path.join(FIXTURES, "brownfield")


def brown(scope=True, modules=None):
    doc = load_yaml(os.path.join(BROWN, "slices.yaml"))
    return common_usage.analyze(BROWN, doc["slices"], None,
                                scope=common_usage.scope_from_slices(doc) if scope else None, modules=modules)


def test_out_of_scope_and_pre_pipeline_are_excluded_from_common():
    """범위 외(unassigned.asis)·이전 차수(pre_pipeline) 코드는 공통이 아니고, 그 코드에서 출발한 호출은 slice 사용이 아니다."""
    before = brown(scope=False)
    assert {c["class"] for c in before["common_classes"]} >= {"com.legacy.batch.NightBatch", "com.legacy.join.JoinService"}
    assert methods(before)["StrUtil#legacyJoin/1"] == {"member": "via:JoinService#isJoined/1"}
    r = brown()
    assert [c["class"] for c in r["common_classes"]] == ["com.legacy.common.util.StrUtil"]
    m = {x["id"]: x for c in r["common_classes"] for x in c["methods"]}
    assert m["legacyJoin/1"]["used_by"] == {} and m["legacyJoin/1"]["excluded_use"] == {"pre_pipeline": "direct"}
    assert m["batchOnly/1"]["used_by"] == {} and m["batchOnly/1"]["excluded_use"] == {"out_of_scope": "direct"}
    # slice 가 이전 차수 코드를 부르면 기록만 한다 (TO-BE 에 이미 있다)
    assert {c["class"]: (c["scope"], c["used_by"]) for c in r["excluded_classes"]} == {
        "com.legacy.batch.NightBatch": ("out_of_scope", {}),
        "com.legacy.join.JoinService": ("pre_pipeline", {"member": "direct"})}
    st = {s["id"]: s["scope"] for s in r["statements"]}
    assert (st["batch.selectTargets"], st["join.selectJoin"], st["common.selectCode"]) == ("out_of_scope", "pre_pipeline", None)
    assert r["summary"]["statements_unused"] == 2      # 범위 제외 statement 는 미사용으로 세지 않는다


def test_module_sets_per_common_item():
    r = brown(modules=["user", "admin"])
    m = {x["id"]: x["modules"] for c in r["common_classes"] for x in c["methods"]}
    assert m["trimAll/1"] == ["user"] and m["formatPhone/1"] == ["admin", "user"] and m["dead/0"] == []
    assert r["summary"]["methods_multi_module"] == 2 and r["summary"]["slices_without_module"] == []
    # modules 가 없으면 필드를 만들지 않는다 (하위 호환)
    assert "modules" not in brown()["common_classes"][0]["methods"][0]


def test_unused_public_method_of_slice_owned_callee_class():
    """다른 클래스가 부르는 업무 클래스(DAO 등)의 미사용 public 메서드만 잡는다. 진입점 클래스(서비스)는 뺀다."""
    assert [(u["slice"], u["class"], u["method"]) for u in brown()["slice_unused_methods"]] == [
        ("member", "com.legacy.member.MemberDAO", "purgeAll/0")]
    assert result()["slice_unused_methods"] == []


def test_interface_dispatch_reaches_implementation_sql(tmp_path):
    # 실측: 업무가 공통 서비스 인터페이스를 부르면 구현체가 쓰는 SQL 이 '미사용' 으로 빠져 계약에서 이관 안 함이 됐다
    src = tmp_path / "src"
    (src / "com/acme/common").mkdir(parents=True)
    (src / "com/acme/order").mkdir(parents=True)
    (src / "sqlmap").mkdir()
    (src / "com/acme/common/CommonService.java").write_text(
        "package com.acme.common;\npublic interface CommonService { String code(String k); }\n", encoding="utf-8")
    (src / "com/acme/common/CommonServiceImpl.java").write_text(
        "package com.acme.common;\nimport org.apache.ibatis.session.SqlSession;\n"
        "public class CommonServiceImpl implements CommonService {\n  private SqlSession sqlSession;\n"
        "  public String code(String k) { return sqlSession.selectOne(\"common.code\", k); }\n}\n", encoding="utf-8")
    (src / "com/acme/order/OrderController.java").write_text(
        "package com.acme.order;\nimport com.acme.common.CommonService;\n"
        "public class OrderController {\n  private CommonService commonService;\n"
        "  public String view() { return commonService.code(\"A\"); }\n}\n", encoding="utf-8")
    (src / "sqlmap/common.xml").write_text(
        '<mapper namespace="common"><select id="code">SELECT 1 FROM dual</select></mapper>', encoding="utf-8")
    slices = [{"id": "order", "asis": {"packages": ["com.acme.order"]}}]
    r = common_usage.analyze(str(src), slices)
    st = {s["id"]: s for s in r["statements"]}
    assert "order" in st["common.code"]["used_by"]
    impl = next(c for c in r["common_classes"] if c["class"].endswith("CommonServiceImpl"))
    assert "order" in next(m for m in impl["methods"] if m["id"] == "code/1")["used_by"]


# ---------------------------------------------------------------- 정적 필드(상수) 참조

def _const_src(tmp_path):
    """메서드 없는 기반 상수 클래스(Consts)·상수 인터페이스(Codes)·상수를 참조하는 공통 유틸(Fmt)."""
    j = tmp_path / "src/main/java/com/x"
    for d in ("common", "order", "member"):
        (j / d).mkdir(parents=True)
    (j / "common/Consts.java").write_text(
        "package com.x.common;\npublic class Consts {\n"
        "    public static final String YES = \"Y\";\n    public static final String NO = \"N\";\n"
        "    public static final int PAGE_SIZE = 10;\n    public static final String UNUSED = \"U\";\n}\n", encoding="utf-8")
    (j / "common/Codes.java").write_text(
        "package com.x.common;\npublic interface Codes {\n    String OK = \"00\";\n}\n", encoding="utf-8")
    (j / "common/Base.java").write_text(
        "package com.x.common;\npublic class Base {\n    public static final String PREFIX = Consts.YES + \"-\";\n}\n",
        encoding="utf-8")
    (j / "common/Fmt.java").write_text(
        "package com.x.common;\npublic class Fmt {\n"
        "    public static String flag(boolean b) { return b ? Consts.YES : Consts.NO; }\n"
        "    public static String dead() { return \"\"; }\n"
        "    static String helper() { return \"\"; }\n"
        "    public static String inner() { return helper(); }\n}\n", encoding="utf-8")
    (j / "order/OrderService.java").write_text(
        "package com.x.order;\nimport com.x.common.Consts;\n"
        "public class OrderService {\n    private int size = Consts.PAGE_SIZE;\n"
        "    public String run() { return Consts.YES; }\n}\n", encoding="utf-8")
    (j / "member/MemberService.java").write_text(
        "package com.x.member;\nimport static com.x.common.Consts.NO;\nimport static com.x.common.Codes.*;\n"
        "import com.x.common.Fmt;\nimport com.x.common.Base;\n"
        "public class MemberService {\n    public String run() { return NO + OK + Base.PREFIX + Fmt.flag(true); }\n}\n",
        encoding="utf-8")
    return [{"id": "order", "asis": {"packages": ["com.x.order"]}},
            {"id": "member", "asis": {"packages": ["com.x.member"]}}]


def test_static_field_references_fill_constant_only_class_usage(tmp_path):
    """실측: 메서드 없는 상수 클래스의 `X.FIELD` 참조를 세지 않아 used_by 가 비고 계약 판단에서 빠졌다."""
    slices = _const_src(tmp_path)
    r = common_usage.analyze(str(tmp_path), slices)
    cls = {c["class"].rsplit(".", 1)[-1]: c for c in r["common_classes"]}
    consts = cls["Consts"]
    assert consts["methods"] == []
    assert set(consts["used_by"]) == {"order", "member"}
    f = {x["id"]: x["used_by"] for x in consts["fields"]}
    # 업무 직접 참조(필드 초기화식 포함)·static import 단건·공통 메서드 경유·공통 필드 초기화식 경유
    assert f["PAGE_SIZE"] == {"order": "direct"}
    assert f["YES"]["order"] == "direct"
    assert f["YES"]["member"] in ("via:Base", "via:Fmt#flag/1")   # 공통 필드 초기화식·공통 메서드 본문 경유
    assert f["NO"] == {"member": "direct"}
    assert "UNUSED" not in f                      # 참조 없는 필드는 행을 만들지 않는다
    # static import 와일드카드로 들여온 상수 인터페이스
    assert cls["Codes"]["used_by"] == {"member": "field:OK"}
    assert r["summary"]["classes_used_without_methods"] >= 3   # Consts·Codes·Base
    assert r["summary"]["static_fields_used"] >= 5
    assert "## 공통 정적 필드(상수) × 업무" in common_usage.to_markdown(r)


def test_asis_callers_counts_intra_class_and_unreached_calls(tmp_path):
    """통째 이관의 본문/전체 주석 판정 근거: AS-IS 어디서든(같은 클래스 내부 포함) 호출되는 곳 수."""
    r = common_usage.analyze(str(tmp_path), _const_src(tmp_path))
    fmt = next(c for c in r["common_classes"] if c["class"].endswith(".Fmt"))
    calls = {m["id"]: m["asis_callers"] for m in fmt["methods"]}
    assert calls == {"dead/0": 0, "flag/1": 1, "helper/0": 1, "inner/0": 0}
