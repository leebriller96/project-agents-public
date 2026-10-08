# gate.py 의 핵심 판정 — 증거 없는 통과를 막는 규칙들이 계속 동작하는지
import json
import os
import shutil

from conftest import FIXTURES, REPO, dev_meta


def hook(result_json, name):
    return next(r for r in json.loads(result_json)["results"] if r["hook"] == name)


def test_zero_tests_counted_as_pass_is_blocked(sandbox):
    meta = dev_meta()
    meta["gates"][1]["test_count"] = 0
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert p.returncode == 1
    r = hook(p.stdout, "gate-proof")
    assert r["result"] == "FAIL"
    assert any("0건" in f["message"] for f in r["findings"])


def test_failed_exit_code_with_done_is_blocked(sandbox):
    meta = dev_meta()
    meta["gates"][0]["exit_code"] = 1
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert p.returncode == 1
    assert hook(p.stdout, "gate-proof")["result"] == "FAIL"


def test_missing_meta_block_is_reported(sandbox):
    d = os.path.join(sandbox.ws, "reports")
    os.makedirs(d)
    rpt = os.path.join(d, "2609281100_stage2_notice_backend.md")
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("# 레포트\n빌드·테스트 모두 통과했습니다.\n")
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert p.returncode == 1
    r = hook(p.stdout, "report-meta")
    assert r["result"] == "FAIL"
    assert any("report-meta.md" in f["message"] for f in r["findings"])


def test_deviations_key_must_be_declared_even_when_empty(sandbox):
    """검출 방향과 미검출 방향을 둘 다 본다 (pipeline-core §14-10).

    산문에만 적힌 "지시와 다른 결정" 이 인계 때 사라진 실측에서 나온 규칙이라,
    키가 없으면 FAIL 하고 빈 배열(= 벗어난 것이 없다는 선언)이면 통과해야 한다.
    """
    meta = dev_meta()
    del meta["deviations"]
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "report-meta")
    assert r["result"] == "FAIL"
    assert any(f["field"] == "deviations" for f in r["findings"])

    # 빈 배열은 선언이므로 이 검사에 걸리지 않는다
    rpt = sandbox.write_report("2609281200_stage2_notice_backend.md", dev_meta())
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "report-meta")
    assert not any(f["field"] == "deviations" for f in r["findings"]), r


def test_latest_report_is_found_by_stage_and_slice(sandbox):
    sandbox.write_report("2609281000_stage2_notice_backend.md", dev_meta())
    newest = sandbox.write_report("2609281200_stage2_notice_backend.md", dev_meta())
    sandbox.write_report("2609281300_stage2_notice-admin_backend.md", dev_meta(slice="notice-admin"))
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "notice", "--format", "json")
    assert json.loads(p.stdout)["report"] == newest


def test_secret_in_report_is_blocked(sandbox):
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta(),
                               body="# 레포트\n접속 정보 password: Sup3rS3cret!\n")
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert hook(p.stdout, "secret-scan")["result"] == "FAIL"


def test_empty_value_is_not_a_secret(sandbox):
    """오검출 방향을 본다 - 이름이 token·secret 으로 끝나는 선언의 빈 값은 비밀값이 아니다.

    실측(2026-10-05): OpenAPI 의 보안 요구 선언 `csrfToken: []` 이 password 규칙에 걸렸다.
    스키마 이름이 그렇게 끝나는 것은 흔하다(csrfToken·accessToken·apiKey) -
    오검출은 검출 실패보다 위험하다(pipeline-core §14-10).
    """
    body = """# 레포트
security:
  - sessionCookie: []
    csrfToken: []
mapping: {}
app.secret: ""
api_key: -
"""
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta(), body=body)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert hook(p.stdout, "secret-scan")["result"] == "PASS", p.stdout

    # 검출 방향은 그대로다 - 값이 있으면 잡는다
    real = """# 레포트
csrfToken: opaquevalue_abcdefghijklmnopqrstuvwxyz0123
"""
    rpt = sandbox.write_report("2609281200_stage2_notice_backend.md", dev_meta(), body=real)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert hook(p.stdout, "secret-scan")["result"] == "FAIL"


def test_oi_converted_requires_rr(sandbox):
    sandbox.run("gate.py", "oi", "new", "--stage", "2", "--kind", "risk", "--severity", "high",
                "--summary", "경합", "--evidence", "A.java:1", "--target", "5", check=0)
    p = sandbox.run("gate.py", "oi", "set", "OI-0001", "converted")
    assert p.returncode != 0
    sandbox.run("gate.py", "oi", "set", "OI-0001", "converted", "--rr", "RR-0001", check=0)
    out = sandbox.run("gate.py", "oi", "list", "--status", "converted", check=0).stdout
    assert "OI-0001" in out


def test_template_meta_is_parseable(sandbox):
    out = sandbox.run("gate.py", "template", "--stage", "2", "--slice", "notice", check=0).stdout
    body = out.split("<!-- pa-meta:start", 1)[1].split("pa-meta:end -->", 1)[0]
    meta = json.loads(body)
    assert meta["stage"] == 2 and meta["slice"] == "notice"


def _copy_fixture(sandbox, which):
    shutil.rmtree(sandbox.target)
    shutil.copytree(os.path.join(FIXTURES, "quality", which), sandbox.target)


def test_productization_blocks_critical_in_changed_files(sandbox):
    _copy_fixture(sandbox, "bad")
    meta = dev_meta()
    meta["repo"]["changed_files"] = ["backend/src/main/java/com/ex/notice/NoticeService.java"]
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "productization")
    assert r["result"] == "FAIL"
    rules = {f["message"].split()[0] for f in r["findings"]}
    assert "JAVA-CONSOLE" in rules
    # 변경 파일만 봤으므로 다른 파일의 규칙(NoticeAudit 의 민감정보 로깅)과 프로젝트 단위 규칙은 없다
    assert "JAVA-LOG-SENSITIVE" not in rules and "JAVA-NO-MDC" not in rules


def test_productization_major_is_warning_by_default_and_blocking_when_strict(sandbox):
    _copy_fixture(sandbox, "bad")
    meta = dev_meta()
    meta["repo"]["changed_files"] = ["backend/src/main/resources/mapper/NoticeMapper.xml"]
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "productization")
    assert r["result"] == "WARN"
    sandbox.write_config("pipeline:\n  gate:\n    productization: strict\n")
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "productization")
    assert r["result"] == "FAIL"


def test_productization_passes_clean_code(sandbox):
    _copy_fixture(sandbox, "good")
    sandbox.write_config("pipeline:\n  gate:\n    productization: strict\n")
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "productization")
    assert r["result"] == "PASS", r


def test_productization_skipped_when_code_not_changed(sandbox):
    _copy_fixture(sandbox, "bad")
    meta = dev_meta()
    meta["repo"]["head"] = "NOT_CHANGED"
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "productization")
    assert r["result"] == "SKIPPED"


# ---------------------------------------------------------------- 테스트 결과 파일 대조 (test-evidence)

def _junit(path, cases, failures=0):
    """testcase 가 cases 개, 그중 failures 개가 실패인 JUnit XML 을 만든다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = "".join(
        f'<testcase name="t{i}" classname="x.T">' + ('<failure message="x"/>' if i < failures else "") + "</testcase>"
        for i in range(cases))
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'<?xml version="1.0"?><testsuite name="x.T" tests="{cases}">{body}</testsuite>')


def _evidence_meta(sandbox, results, test_count, failures=0, started="2026-01-01 00:00"):
    meta = dev_meta(started_at=started)
    meta["gates"][1].update({"results": results, "test_count": test_count, "failures": failures})
    return sandbox.write_report("2609281100_stage2_notice_backend.md", meta)


def test_test_count_is_checked_against_result_files(sandbox):
    _junit(os.path.join(sandbox.target, "backend/build/test-results/test/TEST-a.xml"), 7)
    _junit(os.path.join(sandbox.target, "backend/build/test-results/test/TEST-b.xml"), 5)
    ok = _evidence_meta(sandbox, ["backend/build/test-results/test/*.xml"], 12)
    assert hook(sandbox.run("gate.py", "check", "--report", ok, "--format", "json").stdout, "test-evidence")["result"] == "PASS"
    bad = _evidence_meta(sandbox, ["backend/build/test-results/test/*.xml"], 226)
    r = hook(sandbox.run("gate.py", "check", "--report", bad, "--format", "json").stdout, "test-evidence")
    assert r["result"] == "FAIL" and any("실측 12건" in f["message"] for f in r["findings"])


def test_failures_in_result_files_block_done(sandbox):
    _junit(os.path.join(sandbox.target, "frontend/reports/junit.xml"), 4, failures=1)
    rpt = _evidence_meta(sandbox, "frontend/reports/junit.xml", 4, failures=0)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "test-evidence")
    assert r["result"] == "FAIL"


def test_baseline_allows_known_failures_but_blocks_new_ones(sandbox):
    # 전체 회귀는 "전부 통과" 가 아니라 "기준선보다 나빠지지 않았는가" 로 본다
    _junit(os.path.join(sandbox.target, "all/TEST-a.xml"), 4, failures=2)   # x.T.t0·t1 실패
    with open(os.path.join(sandbox.target, "baseline.txt"), "w", encoding="utf-8") as f:
        f.write("# 기존 실패\nT.t0\nT.t1\n")
    meta = dev_meta(started_at="2026-01-01 00:00")
    meta["gates"][1].update({"results": "all/*.xml", "test_count": 4, "failures": 2, "baseline": "baseline.txt"})
    ok = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    assert hook(sandbox.run("gate.py", "check", "--report", ok, "--format", "json").stdout, "test-evidence")["result"] != "FAIL"
    with open(os.path.join(sandbox.target, "baseline.txt"), "w", encoding="utf-8") as f:
        f.write("T.t0\n")   # t1 은 기준선 밖 = 새 실패
    r = hook(sandbox.run("gate.py", "check", "--report", ok, "--format", "json").stdout, "test-evidence")
    assert r["result"] == "FAIL" and any("기준선 밖 새 실패 1건" in f["message"] for f in r["findings"])
    with open(os.path.join(sandbox.target, "baseline.txt"), "w", encoding="utf-8") as f:
        f.write("T\n")      # 클래스 단위 항목은 그 클래스 전체를 덮는다
    assert hook(sandbox.run("gate.py", "check", "--report", ok, "--format", "json").stdout, "test-evidence")["result"] != "FAIL"


def test_baseline_gate_with_failures_can_be_done_and_baseline_folder_works(sandbox):
    # 기존 실패가 섞인 회귀 게이트는 baseline 을 적으면 result=done 이어도 gate-proof 가 막지 않는다.
    # baseline 이 결과 사본 폴더여도 그 안의 실패 이름을 기준선으로 쓴다(실측: 폴더를 열다 PermissionError).
    _junit(os.path.join(sandbox.target, "all/TEST-a.xml"), 4, failures=2)
    _junit(os.path.join(sandbox.target, "base/TEST-a.xml"), 4, failures=2)
    meta = dev_meta(started_at="2026-01-01 00:00")
    meta["gates"][1].update({"results": "all/*.xml", "test_count": 4, "failures": 2, "baseline": "base"})
    ok = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    out = sandbox.run("gate.py", "check", "--report", ok, "--format", "json").stdout
    assert hook(out, "gate-proof")["result"] != "FAIL"
    assert hook(out, "test-evidence")["result"] != "FAIL"
    del meta["gates"][1]["baseline"]
    bad = sandbox.write_report("2609281101_stage2_notice_backend.md", meta)
    out = sandbox.run("gate.py", "check", "--report", bad, "--format", "json").stdout
    assert hook(out, "gate-proof")["result"] == "FAIL"


def test_stale_result_files_are_rejected(sandbox):
    path = os.path.join(sandbox.target, "backend/build/test-results/test/TEST-a.xml")
    _junit(path, 3)
    os.utime(path, (1_000_000_000, 1_000_000_000))   # 2001년 — 이번 단계 이전
    rpt = _evidence_meta(sandbox, ["backend/build/test-results/test/*.xml"], 3, started="2026-09-28 10:00")
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "test-evidence")
    assert r["result"] == "FAIL" and any("이전" in f["message"] for f in r["findings"])


def test_missing_results_warns_by_default_and_blocks_when_strict(sandbox):
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "test-evidence")
    assert r["result"] == "WARN"
    sandbox.write_config("pipeline:\n  gate:\n    test_evidence: strict\n")
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "test-evidence")
    assert r["result"] == "FAIL"


def test_skip_option_excludes_hook(sandbox):
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    out = json.loads(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json",
                                 "--skip", "state-consistency").stdout)
    assert "state-consistency" not in {r["hook"] for r in out["results"]}


def test_emoji_in_report_is_blocked(sandbox):
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta(),
                               body="# 레포트\n빌드 통과 \u2705\n")
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert p.returncode == 1
    assert hook(p.stdout, "no-emoji")["result"] == "FAIL"


# ---------------------------------------------------------------- 공통 계약 (common-integrity)

def _migration_sandbox(sandbox, strict=False, contract=True, approved=True):
    import sys as _sys
    import yaml
    _sys.path.insert(0, os.path.join(sandbox.root, "tools"))
    legacy = os.path.join(FIXTURES, "legacy")
    extra = f"  mode: migration\nasis:\n  source_dir: {legacy}\n"
    if strict:
        extra += "pipeline:\n  gate:\n    common_contract: strict\n"
    sandbox.write_config(extra)
    if not contract:
        return
    import common_contract as ccm
    import common_usage
    usage = common_usage.analyze(legacy, yaml.safe_load(open(os.path.join(legacy, "slices.yaml"), encoding="utf-8"))["slices"])
    up = os.path.join(sandbox.root, "usage.yaml")
    with open(up, "w", encoding="utf-8") as f:
        yaml.safe_dump(usage, f, allow_unicode=True)
    out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
    ccm.main(["--contract", out, "init", "--usage", up, "--out", out])
    data = yaml.safe_load(open(out, encoding="utf-8"))
    for i in data["items"]:
        if i["owner"] == "review":
            i["owner"] = "discard"
    data["approved"] = approved
    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def test_migration_without_contract_warns_or_blocks(sandbox):
    _migration_sandbox(sandbox, contract=False)
    rpt = sandbox.write_report("2609281100_stage2_loan_backend.md", dev_meta(slice="loan"))
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "common-integrity")
    assert r["result"] == "WARN"
    _migration_sandbox(sandbox, strict=True, contract=False)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "common-integrity")
    assert r["result"] == "FAIL"


def test_unapproved_contract_blocks_done(sandbox):
    _migration_sandbox(sandbox, approved=False)
    rpt = sandbox.write_report("2609281100_stage2_loan_backend.md", dev_meta(slice="loan"))
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "common-integrity")
    assert r["result"] == "FAIL" and any("승인되지 않은" in f["message"] for f in r["findings"])


def test_private_copy_of_common_blocks_slice_gate(sandbox):
    _migration_sandbox(sandbox)
    rel = "backend/loan/src/main/java/com/ex/loan/LoanService.java"
    p = os.path.join(sandbox.target, rel)
    os.makedirs(os.path.dirname(p))
    with open(p, "w", encoding="utf-8") as f:
        f.write("package com.ex.loan;\n/** 대출 */\npublic class LoanService {\n"
                "    private String pad(String value, int width) {\n        String out = value;\n"
                "        while (out.length() < width) { out = \"0\" + out; }\n        return out;\n    }\n}\n")
    meta = dev_meta(slice="loan")
    meta["repo"]["changed_files"] = [rel]
    rpt = sandbox.write_report("2609281100_stage2_loan_backend.md", meta)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "common-integrity")
    assert r["result"] == "FAIL" and any("공통 복제" in f["message"] for f in r["findings"])


# ---------------------------------------------------------------- brownfield: hold·모듈 (slice-scope, plan, common-integrity)

def _brown_sandbox(sandbox, extra="", state=None, contract=False):
    """brownfield 예제(user·admin 모듈, hold slice)를 sandbox 에 깐다."""
    import yaml
    brown = os.path.join(FIXTURES, "brownfield")
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(brown, "slices.yaml"), os.path.join(sandbox.ws, "slices", "slices.yaml"))
    sandbox.write_config("  modules: [user, admin]\n  common_module: common\n"
                         "  module_paths:\n    user: [server/user]\n    admin: [server/admin]\n    common: [server/common]\n"
                         + extra)
    st = state or {"iteration": 1, "stages": {"stage1_slicing": "done", "stage2_scaffold": "done"}, "slices": {}}
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(st, f, allow_unicode=True)
    if contract:
        import sys as _sys
        _sys.path.insert(0, os.path.join(sandbox.root, "tools"))
        import common_contract as ccm
        import common_usage
        doc = yaml.safe_load(open(os.path.join(brown, "slices.yaml"), encoding="utf-8"))
        usage = common_usage.analyze(brown, doc["slices"], None, scope=common_usage.scope_from_slices(doc),
                                     modules=["user", "admin"])
        up = os.path.join(sandbox.root, "usage.yaml")
        with open(up, "w", encoding="utf-8") as f:
            yaml.safe_dump(usage, f, allow_unicode=True)
        out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
        ccm.main(["--contract", out, "init", "--usage", up, "--out", out, "--common-module", "common"])
        data = yaml.safe_load(open(out, encoding="utf-8"))
        for i in data["items"]:
            if i["owner"] == "review":
                i["owner"] = "discard"
        data["approved"] = True
        with open(out, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return brown


def test_plan_excludes_hold_slice_and_its_dependents(sandbox):
    import yaml
    _brown_sandbox(sandbox)
    sp = os.path.join(sandbox.ws, "slices", "slices.yaml")
    doc = yaml.safe_load(open(sp, encoding="utf-8"))
    doc["slices"].append({"id": "noticeview", "name": "공지 조회", "module": "admin", "depends_on": ["notice"],
                          "traits": [], "asis": {}})
    with open(sp, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
    plan = json.loads(sandbox.run("gate.py", "plan", "--format", "json", check=0).stdout)
    in_waves = {i for w in plan["waves"] for i in w}
    assert in_waves == {"member", "board", "adminmember"}
    assert plan["slices"] == 3 and plan["runnable"]
    assert any(h.startswith("notice: 근거 대기 hold") and "요구사항 근거 대기" in h for h in plan["held"])
    assert any(h.startswith("noticeview:") and "notice" in h for h in plan["held"])
    human = sandbox.run("gate.py", "plan", check=0).stdout
    assert "착수 보류" in human and "근거 대기 hold" in human


def test_hold_slice_cannot_be_recorded_done(sandbox):
    _brown_sandbox(sandbox)
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta(slice="notice"))
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "slice-scope")
    assert r["result"] == "FAIL" and any("근거 대기 hold" in f["message"] for f in r["findings"])


def test_change_outside_own_module_is_warned(sandbox):
    _brown_sandbox(sandbox)
    meta = dev_meta(slice="board")
    meta["repo"]["changed_files"] = ["server/user/src/main/java/com/ex/user/board/BoardService.java",
                                     "server/common/src/main/java/com/ex/common/Auth.java",
                                     "server/admin/src/main/java/com/ex/admin/board/AdminBoard.java"]
    rpt = sandbox.write_report("2609281100_stage2_board_backend.md", meta)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "slice-scope")
    assert r["result"] == "WARN"
    # 자기 모듈(user)·전 모듈 공통(common) 경로는 통과, 다른 모듈(admin) 경로만 경고
    assert len(r["findings"]) == 1 and "admin/board/AdminBoard.java" in r["findings"][0]["message"]
    # 모듈 경로 매핑이 없으면 검사하지 않는다 (하위 호환)
    sandbox.write_config("")
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "slice-scope")
    assert r["result"] in ("PASS", "SKIP") and not r["findings"]


def test_common_integrity_allows_contract_copy_but_blocks_same_module_copy(sandbox):
    brown = _brown_sandbox(sandbox, extra=f"  mode: migration\nasis:\n  source_dir: {os.path.join(FIXTURES, 'brownfield')}\n",
                           contract=True)
    assert brown
    body = ("package com.ex.{m}.x;\n/** 복사본 */\npublic class {c} {{\n    /** 전화번호 */\n"
            "    public static String phone(String raw) {{\n        String d = raw.replace(\"-\", \"\");\n"
            "        return d.substring(0, 3) + \"-\" + d.substring(3, 7) + \"-\" + d.substring(7);\n    }}\n}}\n")

    def put(rel, text):
        p = os.path.join(sandbox.target, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return rel

    admin = put("server/admin/src/main/java/com/ex/admin/x/AdminPhone.java", body.format(m="admin", c="AdminPhone"))
    meta = dev_meta(slice="adminmember")
    meta["repo"]["changed_files"] = [admin]
    rpt = sandbox.write_report("2609281100_stage2_adminmember_backend.md", meta)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "common-integrity")
    assert r["result"] == "PASS", r
    put("server/user/src/main/java/com/ex/user/x/MemberPhone.java", body.format(m="user", c="MemberPhone"))
    board = put("server/user/src/main/java/com/ex/user/x/BoardPhone.java", body.format(m="user", c="BoardPhone"))
    meta = dev_meta(slice="board")
    meta["repo"]["changed_files"] = [board]
    rpt = sandbox.write_report("2609281200_stage2_board_backend.md", meta)
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "common-integrity")
    assert r["result"] == "FAIL" and any("같은 모듈 안 복제" in f["message"] for f in r["findings"])


def test_future_executed_at_is_blocked(sandbox):
    # 실측: 서브에이전트가 실행 시각을 실측하지 않고 적어 기록 시점보다 30분 뒤의 시각이 보고됐다
    meta = dev_meta()
    meta["gates"][0]["executed_at"] = "2099-01-01 00:00"
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert p.returncode == 1
    r = hook(p.stdout, "gate-proof")
    assert r["result"] == "FAIL"
    assert any("미래" in f["message"] for f in r["findings"])


def test_oi_set_retarget_keeps_history(sandbox):
    # 실측: 1단계 예약 항목 29건을 다음 단계로 옮길 명령이 없어 에이전트가 제안값만 레포트에 남겼다
    sandbox.run("gate.py", "oi", "new", "--stage", "0", "--kind", "decision", "--severity", "high",
                "--summary", "범위 결정", "--evidence", "a.md", "--target", "1", check=0)
    sandbox.run("gate.py", "oi", "set", "OI-0001", "open", "--target", "2", "--note", "slice 분류 후 결정", check=0)
    import yaml
    with open(os.path.join(sandbox.ws, "open-items.yaml"), encoding="utf-8") as f:
        item = yaml.safe_load(f)["items"][0]
    assert item["target_stage"] == 2 and item["status"] == "open"
    assert "재예약 1→2" in item["note"]


def test_repo_consistency_accepts_git_worktree(sandbox):
    # 실측: target 이 git worktree 면 .git 이 파일이라 repo 대조를 건너뛰었다
    import subprocess as sp
    sp.run(["git", "init", "-q", "main"], cwd=sandbox.target, check=True)
    main = os.path.join(sandbox.target, "main")
    sp.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"], cwd=main, check=True)
    wt = os.path.join(sandbox.root, "wt")
    sp.run(["git", "worktree", "add", "-q", wt], cwd=main, check=True)
    with open(os.path.join(sandbox.root, "config", "project.yaml"), "w", encoding="utf-8") as f:
        f.write("project:\n  name: t\n  target_dir: wt\n")
    assert os.path.isfile(os.path.join(wt, ".git"))
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "repo-consistency")
    assert not any("찾지 못해" in x["message"] for x in r["findings"])


def _slices_with_traits(sandbox, traits):
    d = os.path.join(sandbox.ws, "slices")
    os.makedirs(d, exist_ok=True)
    yml = """approved: true
slices:
  - id: notice
    traits: [%s]
"""
    with open(os.path.join(d, "slices.yaml"), "w", encoding="utf-8") as f:
        f.write(yml % ", ".join(traits))


def test_coverage_axis_reads_reservations_from_open_items_file(sandbox):
    """예약의 정본은 open-items.yaml 이다 - 레포트에 다시 싣지 않아도 축이 닫힌 것으로 본다.

    실측: 레포트의 open_items 만 보던 구현은 이전 회차에 채번된 예약을 회차마다 다시 실어야 했고,
    잊으면 닫힌 것이 다시 열린 것처럼 보였다.
    """
    _slices_with_traits(sandbox, ["transaction"])   # transaction trait 가 real-db 축을 요구한다
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())

    # 1) 예약이 아무 데도 없으면 요구 축이 비어 경고가 난다 (검출 방향)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "coverage-axis")
    assert any("real-db" in f["message"] for f in r["findings"]), r

    # 2) open-items.yaml 에만 예약돼 있어도 닫힌 것으로 본다 (미검출 방향)
    sandbox.run("gate.py", "oi", "new", "--stage", "2", "--slice", "notice", "--kind", "unverified",
                "--severity", "medium", "--summary", "real-db 미검증", "--evidence", "reports/x.md",
                "--target", "5", "--axis", "real-db", check=0)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "coverage-axis")
    assert not any("real-db" in f["message"] for f in r["findings"]), r


def test_repo_head_that_is_an_ancestor_is_info_not_failure(sandbox):
    """레포트를 쓴 뒤 커밋되면 HEAD 가 앞으로 나간다 - 그것은 불일치가 아니라 정상 진행이다.

    실측: 현재 HEAD 와 문자열 비교만 하던 구현은 커밋 직후 모든 레포트를 영원히 FAIL 로 만들었다.
    """
    import subprocess as sp

    def g(*a):
        sp.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", *a], cwd=sandbox.target, check=True,
               capture_output=True)
    g("init", "-q", "-b", "main")
    g("commit", "-q", "--allow-empty", "-m", "first")
    first = sp.run(["git", "rev-parse", "HEAD"], cwd=sandbox.target, capture_output=True, text=True).stdout.strip()

    meta = dev_meta()
    meta["repo"] = {"dir": "target", "branch": "main", "head": first, "base": "", "dirty": True,
                    "changed_files": []}
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    g("commit", "-q", "--allow-empty", "-m", "second")   # 레포트 작성 뒤 커밋

    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "repo-consistency")
    assert r["result"] == "PASS", r                       # INFO 는 통과를 깎지 않는다
    assert [f["severity"] for f in r["findings"]] == ["INFO", "INFO"], r

    # 트리가 갈라지면(조상이 아니면) 그대로 FAIL 이다 (검출 방향)
    meta["repo"]["head"] = "0" * 40
    rpt = sandbox.write_report("2609281200_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "repo-consistency")
    assert r["result"] == "FAIL" and any(f["field"] == "repo.head" for f in r["findings"]), r


def test_harm_evidence_method_requires_enforced_by(sandbox):
    """규약을 고친 회차는 변이시킬 구현이 없다 - 해악 재현만으로 끝내지 않고 강제 수단을 밝힌다."""
    meta = dev_meta()
    meta["discrimination"] = [{
        "target": "CA2-03 / AuditTransactionIntegrationTest#propagation",
        "method": "harm_evidence", "scope": "server/common-audit 모듈 전체",
        "failures": 1, "evidence": "reports/discrimination/common-audit_r1/TEST-*.xml",
    }]
    rpt = sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "cost-record")
    assert r["result"] == "FAIL"
    assert any(f["field"].endswith(".enforced_by") for f in r["findings"]), r

    meta["discrimination"][0]["enforced_by"] = "ArchUnit 규약 검사 TransactionBoundaryRuleTest"
    rpt = sandbox.write_report("2609281200_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "cost-record")
    assert not any(f["field"].endswith(".enforced_by") for f in r["findings"]), r


# ---------------------------------------------------------------- 채번 시작 번호 (BG-03)

def test_numbering_start_avoids_collision_with_other_environment(sandbox):
    """이력이 다른 작업 환경에 있을 때 1 부터 다시 채번하지 않는다.

    실측(2026-10-05): 번호는 target 소스 주석에 박히는 순간 그 저장소의 공용 자원이 되는데
    이력이 담긴 workspace 는 환경마다 다르다. 환경을 옮기니 max+1 채번이 1 로 돌아가
    이미 다른 뜻으로 쓰인 번호와 정면 충돌했다.
    """
    def new_oi():
        return sandbox.run("gate.py", "oi", "new", "--stage", "2", "--kind", "risk", "--severity", "low",
                           "--summary", "x", "--evidence", "A.java:1", "--target", "5",
                           check=0).stdout.strip().splitlines()[0]

    # 설정이 없으면 종전대로 1 부터 (뒤로 호환)
    assert new_oi() == "OI-0001"

    # 시작 번호를 주면 그 번호부터
    sandbox.write_config("numbering:\n  oi_start: 201\n")
    assert new_oi() == "OI-0201"
    # 이미 더 큰 번호가 있으면 max+1 이 이긴다 (시작 번호가 뒤로 끌지 않는다)
    assert new_oi() == "OI-0202"
    sandbox.write_config("numbering:\n  oi_start: 50\n")
    assert new_oi() == "OI-0203"


def test_numbering_start_applies_to_jd_and_rr(sandbox):
    sandbox.write_config("numbering:\n  jd_start: 301\n  rr_start: 101\n")
    jd = sandbox.run("judgment.py", "new", "--stage", "2", "--kind", "scope", "--by", "사람:홍길동",
                     "--summary", "s", "--rationale", "r", "--source", "reports/x.md#1", "--check", "c",
                     check=0).stdout.strip().splitlines()[0]
    assert jd == "JD-0301", jd
    rr = sandbox.run("rr.py", "new", "--title", "t", "--slice", "notice", "--source", "2", "--target", "2",
                     "--severity", "low", "--description", "d", "--fix", "f", check=0).stdout
    assert "RR-0101" in rr, rr


def test_next_number_helper_is_pure_about_start():
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.join(REPO, "tools"))
    from _common import next_number
    assert next_number([], "OI", 4, start=201) == 201
    assert next_number(["OI-0205"], "OI", 4, start=201) == 206     # max+1 이 시작 번호보다 크면 그쪽
    assert next_number(["OI-0100"], "OI", 4, start=201) == 201     # 시작 번호가 크면 시작 번호
    assert next_number(["OI-0100"], "OI", 4, start=1) == 101



# ---------------------------------------------------------------- brownfield: slice 의 공통 소비 목록 (BG-08)

def _consumes_sandbox(sandbox, consumes, files=None, external=False):
    """brownfield 예제에 board slice 의 consumes 를 심고, target 에 공통 클래스를 깐다."""
    import yaml
    _brown_sandbox(sandbox, extra="  base_package: com.ex\n")
    sp = os.path.join(sandbox.ws, "slices", "slices.yaml")
    doc = yaml.safe_load(open(sp, encoding="utf-8"))
    for sl in doc["slices"]:
        if sl["id"] == "board":
            if consumes is None:
                sl.pop("consumes", None)
            else:
                sl["consumes"] = consumes
    with open(sp, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
    # target 에 공통 클래스를 둔다 (scan_target_names 가 FQCN 을 모은다)
    d = os.path.join(sandbox.root, "target", "server", "common", "src", "main", "java", "com", "ex", "common", "util")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "AesUtil.java"), "w", encoding="utf-8") as f:
        f.write("package com.ex.common.util;\n/** 암복호 */\npublic class AesUtil {\n"
                "    /** 암호화 */\n    public static String encrypt(String s) { return s; }\n}\n")
    if external:
        out = os.path.join(sandbox.ws, "contracts", "common-contract.yaml")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            yaml.safe_dump({"schema": 1, "status": "external", "source": "CONVENTIONS.md 5절",
                            "numbering": "CC-0028~CC-1473", "evidence": "BRANCH_NOTE.md",
                            "decided_by": "사람:홍길동", "items": [], "approved": True}, f, allow_unicode=True)
    meta = dev_meta(slice="board")
    meta["repo"]["changed_files"] = list(files or ["server/user/src/main/java/com/ex/user/board/BoardService.java"])
    for rel in meta["repo"]["changed_files"]:
        ap = os.path.join(sandbox.root, "target", rel.replace("/", os.sep))
        if not os.path.exists(ap):
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "w", encoding="utf-8") as f:
                f.write("package com.ex.user.board;\n/** 업무 */\npublic class BoardService {}\n")
    rpt = sandbox.write_report("2610061300_stage2_board_backend.md", meta)
    return hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout,
                "consumes-integrity")


GOOD_CONSUME = [{"item": "com.ex.common.util.AesUtil", "kind": "class", "source": "CONVENTIONS.md#5-4"}]


def test_consumes_absent_is_info_normally_but_warns_when_contract_is_external(sandbox):
    """공통 사용 행렬이 있으면 계산되지만, 외부 확정 계약이면 소비 목록이 유일한 연결 수단이다."""
    r = _consumes_sandbox(sandbox, None)
    assert r["result"] == "PASS" and [f["severity"] for f in r["findings"]] == ["INFO"]

    r = _consumes_sandbox(sandbox, None, external=True)
    assert r["result"] == "WARN"
    assert any("사용 행렬이 없고" in f["message"] for f in r["findings"]), r["findings"]


def test_consumes_that_exists_passes_and_missing_one_fails(sandbox):
    r = _consumes_sandbox(sandbox, GOOD_CONSUME)
    assert r["result"] == "PASS", r["findings"]

    # 메서드 단위도 본다
    r = _consumes_sandbox(sandbox, [dict(GOOD_CONSUME[0], item="com.ex.common.util.AesUtil#encrypt",
                                         kind="method")])
    assert r["result"] == "PASS", r["findings"]

    # 적었는데 target 에 없으면 FAIL — "공통에 있다고 적기만 하면 통과" 를 막는다
    for bad in ("com.ex.common.util.NoSuchUtil", "com.ex.common.util.AesUtil#decrypt"):
        r = _consumes_sandbox(sandbox, [dict(GOOD_CONSUME[0], item=bad,
                                             kind="method" if "#" in bad else "class")])
        assert r["result"] == "FAIL" and any("찾지 못했다" in f["message"] for f in r["findings"]), (bad, r)


def test_consumes_requires_item_kind_source_and_rejects_bad_shapes(sandbox):
    for bad, want in (([{"kind": "class", "source": "x"}], "item"),
                      ([{"item": "com.ex.common.util.AesUtil", "source": "x"}], "kind"),
                      ([{"item": "com.ex.common.util.AesUtil", "kind": "class"}], "source"),
                      ([{"item": "com.ex.common.util.AesUtil", "kind": "소비", "source": "x"}], "kind"),
                      (["문자열"], "사전"),
                      ("목록아님", "목록이 아니다")):
        r = _consumes_sandbox(sandbox, bad)
        assert r["result"] == "FAIL", (bad, r["findings"])
        assert any(want in f["message"] for f in r["findings"]), (bad, r["findings"])

    # 중복은 경고
    r = _consumes_sandbox(sandbox, GOOD_CONSUME + GOOD_CONSUME)
    assert r["result"] == "WARN" and any("중복" in f["message"] for f in r["findings"])


def test_using_an_undeclared_common_is_warned(sandbox):
    """적지 않은 공통을 쓰면 공통을 고칠 때 영향 slice 에서 빠진다."""
    rel = "server/user/src/main/java/com/ex/user/board/BoardService.java"
    ap = os.path.join(sandbox.root, "target", rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(ap), exist_ok=True)
    with open(ap, "w", encoding="utf-8") as f:
        f.write("package com.ex.user.board;\n\nimport com.ex.common.util.AesUtil;\n"
                "import java.util.List;\n/** 업무 */\npublic class BoardService {}\n")

    # 적지 않았으면 경고한다
    r = _consumes_sandbox(sandbox, [], files=[rel])
    assert r["result"] == "WARN", r["findings"]
    assert any("AesUtil" in f["message"] and "consumes 에 없다" in f["message"]
               for f in r["findings"]), r["findings"]

    # 적었으면 경고하지 않는다. 공통이 아닌 import(java.util)는 애초에 보지 않는다
    r = _consumes_sandbox(sandbox, GOOD_CONSUME, files=[rel])
    assert r["result"] == "PASS", r["findings"]


# ---------------------------------------------------------------- done_elsewhere (BG-01)

ELSEWHERE_OK = {
    "where": "다른 작업 환경 (브랜치 dev3 · 커밋 fd0f5f76)",
    "evidence": "target_dir docs/pipeline/BRANCH_NOTE.md 완료 내역 표",
    "not_verified_here": "레포트·pa-meta 부재 · 잠금 매니페스트 부재",
    "declared_by": "사람:홍길동",
    "declared_at": "2026-10-06 03:30",
}


def _state_hook(sandbox, state, meta):
    import yaml
    os.makedirs(sandbox.ws, exist_ok=True)
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(state, f, allow_unicode=True)
    rpt = sandbox.write_report("2610061500_stage3_common.md", meta)
    return hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout,
                "state-consistency")


def test_done_elsewhere_needs_a_human_declaration_that_says_what_was_not_verified(sandbox):
    """"다른 환경에서 끝났다" 는 skipped(안 했다)·blocked(막혔다)와 다른 사실이다.

    실측(2026-10-06): 공통 선행 변환을 다른 PC 에서 끝낸 뒤 이 환경에는 레포트·pa-meta·잠금 매니페스트가
    없었다. 상태 값에 그 개념이 없어 skipped 또는 blocked 를 골라야 했고 둘 다 사실이 아니었으며,
    어느 쪽도 "무엇을 확인하지 못했나" 를 남기지 못했다.
    """
    meta = dev_meta(stage=3, slice=None, result="done")

    # (1) 선언이 없으면 차단한다 — 상태 값만 바꿔 통과시킬 수 없다
    r = _state_hook(sandbox, {"stages": {"stage3_common": "done_elsewhere"}}, meta)
    assert r["result"] == "FAIL"
    assert any("elsewhere 선언이 없다" in f["message"] for f in r["findings"]), r["findings"]

    # (2) 칸이 비어 있으면 선언으로 보지 않는다 (네 칸 전부 필수)
    for k in ("where", "evidence", "not_verified_here", "declared_by"):
        rec = dict(ELSEWHERE_OK, **{k: ""})
        r = _state_hook(sandbox, {"stages": {"stage3_common": "done_elsewhere"},
                                  "elsewhere": {"stage3_common": rec}}, meta)
        assert r["result"] == "FAIL", (k, r["findings"])
        assert any(f"elsewhere.{k}" in f["message"] for f in r["findings"]), (k, r["findings"])

    # (3) 에이전트가 선언할 수 없다 — 사람만
    rec = dict(ELSEWHERE_OK, declared_by="에이전트:orchestrator")
    r = _state_hook(sandbox, {"stages": {"stage3_common": "done_elsewhere"},
                              "elsewhere": {"stage3_common": rec}}, meta)
    assert r["result"] == "FAIL"
    assert any("사람:" in f["message"] for f in r["findings"]), r["findings"]

    # (4) 제대로 채운 선언은 통과하고, 확인하지 못한 것을 INFO 로 남긴다
    r = _state_hook(sandbox, {"stages": {"stage3_common": "done_elsewhere"},
                              "elsewhere": {"stage3_common": ELSEWHERE_OK}}, meta)
    assert r["result"] == "PASS", r["findings"]
    sev = [f["severity"] for f in r["findings"]]
    assert sev == ["INFO"], r["findings"]
    msg = r["findings"][0]["message"]
    assert "매니페스트 부재" in msg and "사람:홍길동" in msg, msg

    # (5) 종전 상태 값들은 그대로 동작한다 (뒤로 호환)
    r = _state_hook(sandbox, {"stages": {"stage3_common": "done"}}, meta)
    assert r["result"] == "PASS" and not r["findings"]
    r = _state_hook(sandbox, {"stages": {"stage3_common": "skipped"}}, meta)
    assert r["result"] == "FAIL", r["findings"]


# ---------------------------------------------------------------- AS-IS 원본 부재 선행 조건 (BG-05)

def _asis_hook(sandbox, *, mode="migration", source_dir=None, state=None, files=None):
    import yaml
    extra = f"  mode: {mode}\n" if mode else ""
    if source_dir is not None:
        extra += f"asis:\n  source_dir: {source_dir}\n"
    sandbox.write_config(extra)
    os.makedirs(sandbox.ws, exist_ok=True)
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(state or {}, f, allow_unicode=True)
    for rel in (files or []):
        ap = os.path.join(sandbox.root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("// AS-IS\n")
    rpt = sandbox.write_report("2610061600_stage0_ingest.md", dev_meta(stage=0, slice=None, result="done"))
    return hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "asis-source")


def test_missing_asis_source_blocks_unless_declared(sandbox):
    """없는 경로를 가리킨 채로 0단계가 통과하면 안 된다.

    실측(BG-05): 분석 자료(인벤토리·문서)만으로 brief 를 만들고 넘어가, "원본이 없다" 는 사실을
    사람이 나중에 알아차렸다. 이관 slice 는 원본 없이 시작할 수 없다.
    """
    # (1) 경로가 없고 선언도 없으면 차단한다
    r = _asis_hook(sandbox, source_dir="asis-nowhere")
    assert r["result"] == "FAIL", r["findings"]
    assert any("찾지 못했다" in f["message"] and "선언도 없다" in f["message"] for f in r["findings"]), r["findings"]

    # config.asis 자체가 없어도 같다 — "설정을 빼면 통과" 가 되지 않게
    r = _asis_hook(sandbox)
    assert r["result"] == "FAIL", r["findings"]
    assert any("미설정" in f["message"] for f in r["findings"]), r["findings"]

    # (2) 선언하면 통과하되 그 때문에 멈춘 slice 를 드러낸다
    st = {"asis_source": "absent",
          "slices": {"legacyview": {"blocked_reason": "hold — asis_source_absent (원본 대기)"},
                     "notice": {"blocked_reason": "데이터 원천 미정"}}}
    r = _asis_hook(sandbox, source_dir="asis-nowhere", state=st)
    assert r["result"] == "WARN", r["findings"]
    msg = " ".join(f["message"] for f in r["findings"])
    assert "absent 로 선언돼 있다" in msg and "legacyview" in msg, msg
    assert "notice" not in msg, msg          # asis 때문에 멈춘 것만 센다

    # (3) 잘못된 값은 선언으로 보지 않는다
    r = _asis_hook(sandbox, source_dir="asis-nowhere", state={"asis_source": "없음"})
    assert r["result"] == "FAIL"
    assert any("값이 잘못됐다" in f["message"] for f in r["findings"]), r["findings"]

    # (4) 원본이 실제로 있으면 파일 수를 INFO 로 남긴다
    r = _asis_hook(sandbox, source_dir="asis-real", files=["asis-real/a/Svc.java", "asis-real/b/M.xml"])
    assert r["result"] == "PASS"
    assert [f["severity"] for f in r["findings"]] == ["INFO"]
    assert "2개 파일" in r["findings"][0]["message"], r["findings"]

    # (5) migration 이 아니면 검사하지 않는다 (신규 개발 프로젝트)
    r = _asis_hook(sandbox, mode="greenfield", source_dir="asis-nowhere")
    assert r["result"] == "SKIPPED", r


def test_plan_stops_on_undeclared_missing_asis_source(sandbox):
    import yaml
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(FIXTURES, "brownfield", "slices.yaml"),
                os.path.join(sandbox.ws, "slices", "slices.yaml"))
    sandbox.write_config("  mode: migration\nasis:\n  source_dir: asis-nowhere\n")
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"stages": {"stage1_slicing": "done"}}, f, allow_unicode=True)
    pl = json.loads(sandbox.run("gate.py", "plan", "--format", "json", check=0).stdout)
    assert any("AS-IS 원본이 없다" in s for s in pl["stops"]), pl["stops"]

    # 선언하면 멈춤이 아니라 참고로 바뀐다
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"stages": {"stage1_slicing": "done"}, "asis_source": "absent"}, f, allow_unicode=True)
    pl = json.loads(sandbox.run("gate.py", "plan", "--format", "json", check=0).stdout)
    assert not any("AS-IS 원본이 없다" in s for s in pl["stops"]), pl["stops"]
    assert any("이관 slice 는 시작할 수 없다" in n for n in pl["notes"]), pl["notes"]


# ---------------------------------------------------------------- 레포트 탐색 실패 안내 (BG-13)

def test_report_lookup_failure_shows_what_is_there(sandbox):
    """자동 탐색이 못 찾으면 **무엇이 있는지**와 이름 규칙을 보여 준다.

    실측(BG-13): 서브에이전트가 지시받은 이름(`..._CR-0005_...`)을 그대로 써서 자동 탐색이
    못 찾았는데, 오류는 폴더 경로만 알려 줘 "레포트를 안 썼나" 와 "이름이 다른가" 를 구분할 수 없었다.
    """
    # 폴더가 비어 있으면 "레포트를 먼저 쓴다"
    os.makedirs(os.path.join(sandbox.ws, "reports"), exist_ok=True)
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "notice")
    assert p.returncode != 0
    assert "레포트가 없다" in p.stderr, p.stderr

    # 이름이 규칙과 다른 레포트가 있으면 그것을 보여 주고 --report 를 안내한다
    sandbox.write_report("2610061700_CR-0005_복호화공통.md", dev_meta(slice="notice"))
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "notice")
    assert p.returncode != 0
    assert "찾은 이름 규칙" in p.stderr and "yymmddhhmm_stage2_notice_*.md" in p.stderr, p.stderr
    assert "2610061700_CR-0005_복호화공통.md" in p.stderr, p.stderr
    assert "--report" in p.stderr, p.stderr

    # 규칙에 맞는 이름이면 찾는다 (뒤로 호환)
    sandbox.write_report("2610061701_stage2_notice_backend.md", dev_meta(slice="notice"))
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "notice", "--format", "json")
    assert "레포트를 찾지 못했다" not in p.stderr, p.stderr
    assert '"results"' in p.stdout, p.stdout


# ---------------------------------------------------------------- AS-IS 테이블 재사용 (asis-table-reuse)

def _table_reuse_setup(sandbox, asis_programs):
    sandbox.write_config("  mode: migration\n")
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    with open(os.path.join(sandbox.ws, "slices", "slices.yaml"), "w", encoding="utf-8") as f:
        progs = "".join(f"\n        - {p}" for p in asis_programs) if asis_programs else " []"
        f.write("approved: true\nslices:\n  - id: notice\n    name: 공지\n    asis:\n      programs:" + progs + "\n")
    d = os.path.join(sandbox.target, "db", "migration", "100_asis_ddl")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "V1__create_tables.sql"), "w", encoding="utf-8") as f:
        f.write("CREATE TABLE WF_BOARD (ID INT);\n")


def _table_reuse_report(sandbox, sql, judgments=None):
    rel = "db/migration/400_tobe_ddl/V2__notice.sql"
    os.makedirs(os.path.dirname(os.path.join(sandbox.target, rel)), exist_ok=True)
    with open(os.path.join(sandbox.target, rel), "w", encoding="utf-8") as f:
        f.write(sql)
    meta = dev_meta(judgments=judgments or [])
    meta["repo"]["changed_files"] = [rel]
    return sandbox.write_report("2609281100_stage2_notice_backend.md", meta)


def test_conversion_slice_must_not_create_new_table_without_judgment(sandbox):
    _table_reuse_setup(sandbox, ["NoticeController.java"])
    rpt = _table_reuse_report(sandbox, "CREATE TABLE ispt_notice_board (id INT);")
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "asis-table-reuse")
    assert r["result"] == "FAIL" and any("새 테이블 ispt_notice_board" in f["message"] for f in r["findings"])
    rpt = _table_reuse_report(sandbox, "CREATE TABLE ispt_notice_board (id INT);",
                              [{"kind": "scope", "summary": "ispt_notice_board 신규 - REQ-099 새 요건"}])
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "asis-table-reuse")
    assert r["result"] != "FAIL"


def test_recreating_asis_table_always_fails(sandbox):
    _table_reuse_setup(sandbox, [])
    rpt = _table_reuse_report(sandbox, "CREATE TABLE IF NOT EXISTS wf_board (id INT);",
                              [{"kind": "scope", "summary": "wf_board"}])
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "asis-table-reuse")
    assert r["result"] == "FAIL" and any("다시 CREATE" in f["message"] for f in r["findings"])


def test_new_feature_slice_may_create_tables(sandbox):
    _table_reuse_setup(sandbox, [])
    rpt = _table_reuse_report(sandbox, "CREATE TABLE ispt_report (id INT);")
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "asis-table-reuse")
    assert r["result"] != "FAIL"


def test_check_target_prefers_option_then_report_repo_dir(tmp_path, monkeypatch):
    # 병렬 작업 트리 레포트를 설정의 기본 트리로 검사하면 거짓 FAIL 이 난다(실측) - 레포트 repo.dir 을 먼저 쓴다
    import argparse
    import sys
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import gate as g
    other = tmp_path / "tree2"
    other.mkdir()
    monkeypatch.setattr(g, "target_dir", lambda: str(tmp_path / "default"))
    ns = argparse.Namespace(target=None)
    assert g.check_target(ns, {"repo": {"dir": str(other)}}) == os.path.normpath(str(other))
    assert g.check_target(ns, {"repo": {"dir": str(tmp_path / "없음")}}) == str(tmp_path / "default")
    assert g.check_target(ns, {}) == str(tmp_path / "default")
    assert g.check_target(ns, {"repo": {"dir": "target"}}) == str(tmp_path / "default")   # 상대 경로는 쓰지 않는다
    assert g.check_target(argparse.Namespace(target=str(other)), {}) == os.path.abspath(str(other))
