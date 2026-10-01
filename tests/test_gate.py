# gate.py 의 핵심 판정 — 증거 없는 통과를 막는 규칙들이 계속 동작하는지
import json
import os
import shutil

from conftest import FIXTURES, dev_meta


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
