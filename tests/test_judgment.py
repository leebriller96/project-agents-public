# judgment.py 와 gate 훅 judgments — 판단으로 정한 것이 기록되고 검증 단계에서 다시 확인되는지 (pipeline-core §21)
import json
import os

from conftest import dev_meta


def hook(result_json, name):
    return next(r for r in json.loads(result_json)["results"] if r["hook"] == name)


def new_jd(sandbox, **over):
    a = {"--stage": "2", "--slice": "common-port", "--kind": "substitution", "--by": "사람:검토자",
         "--summary": "메시지 후 이동을 jsonSuccess + navigate 로 대체", "--rationale": "2차 기반에 같은 의미의 응답 도우미가 있다",
         "--source": "reports/x.md#4-3", "--check": "저장 후 목록 화면으로 이동하고 메시지가 보이는지",
         "--verify-slices": "notice,member"}
    a.update(over)
    args = [x for kv in a.items() for x in kv if kv[1] is not None]
    return sandbox.run("judgment.py", "new", *args)


def verify_meta(**over):
    meta = dev_meta(stage=5, slice="notice", agent="integration-tester")
    meta.update(over)
    return meta


def test_new_requires_check_and_records_criterion_by_mode(sandbox):
    p = new_jd(sandbox, **{"--check": ""})
    assert p.returncode != 0
    sandbox.write_config("  mode: migration\n")
    new_jd(sandbox).check_returncode()
    out = json.loads(sandbox.run("judgment.py", "list", "--format", "json", check=0).stdout)
    assert out[0]["id"] == "JD-0001"
    assert "AS-IS" in out[0]["criterion"]
    assert out[0]["verify_slices"] == ["notice", "member"]


def test_verify_stage_blocks_until_each_slice_is_checked(sandbox):
    new_jd(sandbox).check_returncode()
    rpt = sandbox.write_report("2610011000_stage5_notice_integration.md", verify_meta())
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    r = hook(p.stdout, "judgments")
    assert r["result"] == "FAIL" and "JD-0001" in r["findings"][0]["message"]
    sandbox.run("judgment.py", "verify", "JD-0001", "--slice", "notice", "--result", "verified",
                "--req-evidence", "ITS-notice-j001 통과", check=0)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert hook(p.stdout, "judgments")["result"] != "FAIL"
    # 다른 확인 slice 가 남았으므로 전체 상태는 아직 pending
    out = json.loads(sandbox.run("judgment.py", "list", "--format", "json", check=0).stdout)
    assert out[0]["status"] == "pending"


def test_migration_verify_needs_asis_evidence(sandbox):
    sandbox.write_config("  mode: migration\n")
    new_jd(sandbox).check_returncode()
    p = sandbox.run("judgment.py", "verify", "JD-0001", "--slice", "notice", "--result", "verified",
                    "--req-evidence", "ITS-notice-j001 통과")
    assert p.returncode != 0 and "asis-evidence" in p.stderr
    sandbox.run("judgment.py", "verify", "JD-0001", "--slice", "notice", "--result", "verified",
                "--req-evidence", "ITS-notice-j001 통과", "--asis-evidence", "AS-IS 같은 입력 결과 동일", check=0)


def test_failed_needs_existing_rr_and_waive_needs_human(sandbox):
    new_jd(sandbox).check_returncode()
    p = sandbox.run("judgment.py", "verify", "JD-0001", "--slice", "notice", "--result", "failed")
    assert p.returncode != 0
    p = sandbox.run("judgment.py", "set", "JD-0001", "--waive", "--note", "사유")
    assert p.returncode != 0
    sandbox.run("judgment.py", "set", "JD-0001", "--waive", "--approved-by", "검토자", "--note", "범위 밖", check=0)
    rpt = sandbox.write_report("2610011000_stage5_notice_integration.md", verify_meta())
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert hook(p.stdout, "judgments")["result"] != "FAIL"


def test_dev_report_deviations_without_judgments_warns_and_unknown_id_fails(sandbox):
    rpt = sandbox.write_report("2610011000_stage2_notice_backend.md",
                               dev_meta(deviations=["계약과 다르게 normalizeSize 로 지정"]))
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "judgments")
    assert r["result"] == "WARN"
    rpt = sandbox.write_report("2610011001_stage2_notice_backend.md", dev_meta(judgments=["JD-0009"]))
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "judgments")
    assert r["result"] == "FAIL"


def test_import_numbers_report_judgments_and_writes_ids(sandbox):
    meta = dev_meta(judgments=[{"kind": "semantic", "summary": "AS-IS 결함 값 유지", "rationale": "동등 이관 원칙",
                                "check": "경계일 입력에서 AS-IS 와 같은 값", "verify_slices": ["notice"]}])
    rpt = sandbox.write_report("2610011000_stage2_notice_backend.md", meta)
    sandbox.run("judgment.py", "import", "--report", rpt, "--write", check=0)
    with open(rpt, encoding="utf-8") as f:
        assert '"id": "JD-0001"' in f.read()
    r = hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "judgments")
    assert r["result"] == "PASS"


def test_resolving_decision_open_item_requires_judgment(sandbox):
    sandbox.run("gate.py", "oi", "new", "--stage", "2", "--kind", "decision", "--severity", "medium",
                "--summary", "대체 방식", "--evidence", "x.md#4", "--target", "2", check=0)
    p = sandbox.run("gate.py", "oi", "set", "OI-0001", "resolved")
    assert p.returncode != 0 and "--jd" in p.stderr
    p = sandbox.run("gate.py", "oi", "set", "OI-0001", "resolved", "--jd", "JD-0001")
    assert p.returncode != 0
    new_jd(sandbox, **{"--oi": "OI-0001"}).check_returncode()
    sandbox.run("gate.py", "oi", "set", "OI-0001", "resolved", "--jd", "JD-0001", check=0)
    assert os.path.exists(os.path.join(sandbox.ws, "judgments.yaml"))
