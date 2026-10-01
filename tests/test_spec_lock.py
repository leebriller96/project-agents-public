# spec_lock.py + 훅 + gate spec-lock — 기대 동작 테스트를 코드 작성자가 고쳐 통과시키지 못하게 하는 장치
import json
import os
import subprocess
import sys

from conftest import dev_meta

SPEC_REL = "backend/loan/src/test/java/com/ex/spec/loan/LoanSpecTest.java"
SPEC_BODY = """package com.ex.spec.loan;

/** 대출 기대 동작 (AS-IS 동작 계약 FC-LOAN-01~03) */
class LoanSpecTest {
    @org.junit.jupiter.api.Test
    void 금리_계산은_원단위_반올림() { }

    @org.junit.jupiter.api.ParameterizedTest
    void 휴일에는_목록이_비어있다() { }

    @org.junit.jupiter.api.Test
    void 페이지_오프셋() { }
}
"""


def write_spec(sandbox, rel=SPEC_REL, body=SPEC_BODY):
    p = os.path.join(sandbox.target, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


def guard(sandbox, payload):
    return subprocess.run([sys.executable, os.path.join(sandbox.root, "tools", "hooks", "guard.py"), "pre-tool-use"],
                          input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True,
                          encoding="utf-8", cwd=sandbox.root, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def test_lock_discovers_slice_specs_and_counts_tests(sandbox):
    write_spec(sandbox)
    out = sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0).stdout
    assert "테스트 3건" in out
    m = json.load(open(os.path.join(sandbox.ws, "specs", "loan.lock.json"), encoding="utf-8"))
    assert list(m["files"]) == [SPEC_REL] and m["test_count"] == 3
    sandbox.run("spec_lock.py", "verify", "--slice", "loan", check=0)


def test_modification_is_detected_and_relock_is_append_only(sandbox):
    p = write_spec(sandbox)
    sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0)
    with open(p, "a", encoding="utf-8") as f:
        f.write("// 기대값 완화\n")
    assert sandbox.run("spec_lock.py", "verify", "--slice", "loan").returncode == 1
    r = sandbox.run("spec_lock.py", "lock", "--slice", "loan")
    assert r.returncode != 0 and "추가만 가능" in r.stderr


def test_new_spec_files_can_be_added_to_lock(sandbox):
    write_spec(sandbox)
    sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0)
    write_spec(sandbox, SPEC_REL.replace("LoanSpecTest", "LoanRateSpecTest"),
               "class LoanRateSpecTest {\n    @org.junit.jupiter.api.Test\n    void a() { }\n}\n")
    out = sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0).stdout
    assert "신규 1" in out and "테스트 4건" in out


def test_unlock_moves_manifest_to_history(sandbox):
    write_spec(sandbox)
    sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0)
    sandbox.run("spec_lock.py", "unlock", "--slice", "loan", "--by", "홍길동", "--reason", "AS-IS 계약 오독", check=0)
    assert not os.path.exists(os.path.join(sandbox.ws, "specs", "loan.lock.json"))
    hist = os.listdir(os.path.join(sandbox.ws, "specs", "history"))
    assert len(hist) == 1 and hist[0].startswith("loan.")


def test_hook_blocks_edits_to_locked_specs_and_manifest(sandbox):
    p = write_spec(sandbox)
    sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0)
    r = guard(sandbox, {"tool_name": "Edit", "tool_input": {"file_path": p, "old_string": "a", "new_string": "b"}})
    assert r.returncode == 2 and "잠긴 기대 동작 테스트" in r.stderr
    r = guard(sandbox, {"tool_name": "Write", "tool_input": {"file_path": os.path.join(sandbox.ws, "specs", "loan.lock.json"),
                                                               "content": "{}"}})
    assert r.returncode == 2
    for cmd in [f"sed -i 's/3/4/' {SPEC_REL}", "rm target/" + SPEC_REL, "git checkout -- LoanSpecTest.java"]:
        assert guard(sandbox, {"tool_name": "Bash", "tool_input": {"command": cmd}}).returncode == 2, cmd
    # 읽기·실행과 잠기지 않은 파일 편집은 허용
    assert guard(sandbox, {"tool_name": "Bash", "tool_input": {"command": f"cat {SPEC_REL}"}}).returncode == 0
    other = os.path.join(sandbox.target, "backend/loan/src/main/java/com/ex/loan/LoanService.java")
    assert guard(sandbox, {"tool_name": "Write", "tool_input": {"file_path": other, "content": "class A {}"}}).returncode == 0


def _spec_meta(test_count, failures=0):
    meta = dev_meta(slice="loan")
    meta["gates"].append({"kind": "test", "suite": "spec", "command": "./gradlew test --tests '*spec.loan*'",
                          "exit_code": 0, "executed_at": "2026-09-28 10:58", "axis": "module",
                          "test_count": test_count, "failures": failures, "skipped": 0})
    return meta


def _hook(out, name):
    return next(r for r in json.loads(out)["results"] if r["hook"] == name)


def test_gate_requires_full_passing_spec_run(sandbox):
    write_spec(sandbox)
    sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0)
    ok = sandbox.write_report("2609281100_stage2_loan_backend.md", _spec_meta(3))
    assert _hook(sandbox.run("gate.py", "check", "--report", ok, "--format", "json").stdout, "spec-lock")["result"] == "PASS"
    partial = sandbox.write_report("2609281101_stage2_loan_backend.md", _spec_meta(2))
    r = _hook(sandbox.run("gate.py", "check", "--report", partial, "--format", "json").stdout, "spec-lock")
    assert r["result"] == "FAIL" and any("3건 중 2건" in f["message"] for f in r["findings"])
    failing = sandbox.write_report("2609281102_stage2_loan_backend.md", _spec_meta(3, failures=1))
    assert _hook(sandbox.run("gate.py", "check", "--report", failing, "--format", "json").stdout, "spec-lock")["result"] == "FAIL"
    missing = sandbox.write_report("2609281103_stage2_loan_backend.md", dev_meta(slice="loan"))
    assert _hook(sandbox.run("gate.py", "check", "--report", missing, "--format", "json").stdout, "spec-lock")["result"] == "FAIL"


def test_gate_detects_tampered_spec(sandbox):
    p = write_spec(sandbox)
    sandbox.run("spec_lock.py", "lock", "--slice", "loan", check=0)
    with open(p, "w", encoding="utf-8") as f:
        f.write(SPEC_BODY.replace("원단위_반올림", "아무_값"))
    rpt = sandbox.write_report("2609281100_stage2_loan_backend.md", _spec_meta(3))
    r = _hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "spec-lock")
    assert r["result"] == "FAIL" and any("수정됐다" in f["message"] for f in r["findings"])


def test_required_policy_blocks_unlocked_completion(sandbox):
    rpt = sandbox.write_report("2609281100_stage2_loan_backend.md", dev_meta(slice="loan"))
    assert _hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "spec-lock")["result"] == "SKIPPED"
    sandbox.write_config("verification:\n  locked_spec: required\n")
    assert _hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "spec-lock")["result"] == "FAIL"
