# ingest_result.py — 에이전트 결과 블록을 레포트·확인 필요 항목·판단 기록으로 빠짐없이 옮기는지
import glob
import json
import os


def result(**over):
    r = {"schema": 1, "agent": "backend-developer", "stage": 2, "slice": "notice", "attempt": 1,
         "result": "done_with_gaps",
         "gates": [{"kind": "test", "command": "mvn test", "exit_code": 0, "executed_at": "2026-10-06 09:00",
                    "test_count": 3, "failures": 0, "skipped": 0, "results": ["x/*.xml"]}],
         "changed_files": ["a/B.java"],
         "open_items": [{"kind": "decision", "severity": "low", "summary": "경로 존치 여부",
                         "evidence": "AS-IS X.java:10", "target_stage": 4},
                        {"kind": "unverified", "severity": "medium", "axis": "module", "summary": "컨텍스트 배선 미확인",
                         "evidence": "기준선", "target_stage": 5}],
         "judgments": [{"kind": "scope", "summary": "업로드 경로 폐기", "rationale": "호출 0건",
                        "source": "레포트", "check": "다시 grep 해 호출 0건 확인", "verify_slices": ["notice"]}],
         "not_executed": ["전체 테스트"], "deviations": ["3개만 계약"]}
    r.update(over)
    return r


def write_json(sandbox, data):
    path = os.path.join(sandbox.root, "res.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def read_meta(path):
    text = open(path, encoding="utf-8").read()
    s = text.index("<!-- pa-meta:start") + len("<!-- pa-meta:start")
    return json.loads(text[s:text.index("pa-meta:end -->")])


def test_ingest_numbers_open_items_and_judgments_into_report(sandbox):
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, result()), "--stage", "2",
                    "--slice", "notice", "--name", "backend_contract")
    assert p.returncode == 0, p.stderr
    reports = glob.glob(os.path.join(sandbox.ws, "reports", "*_stage2_notice_backend_contract.md"))
    assert len(reports) == 1
    meta = read_meta(reports[0])
    assert [i["id"] for i in meta["open_items"]] == ["OI-0001", "OI-0002"]
    assert meta["judgments"][0]["id"] == "JD-0001"
    assert meta["gates"][0]["test_count"] == 3
    assert meta["not_executed"] == ["전체 테스트"]
    text = open(reports[0], encoding="utf-8").read()
    assert "OI-0002(medium)" in text and "3개만 계약" in text


def test_ingest_respects_numbering_start(sandbox):
    sandbox.write_config("numbering:\n  oi_start: 500\n  jd_start: 500\n")
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, result()), "--stage", "2",
                    "--slice", "notice", "--name", "x")
    assert p.returncode == 0, p.stderr
    meta = read_meta(glob.glob(os.path.join(sandbox.ws, "reports", "*_x.md"))[0])
    assert meta["open_items"][0]["id"] == "OI-0500"
    assert meta["judgments"][0]["id"] == "JD-0500"


def test_ingest_dry_run_writes_nothing(sandbox):
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, result()), "--stage", "2",
                    "--slice", "notice", "--name", "x", "--dry-run")
    assert p.returncode == 0, p.stderr
    assert "pa-meta:start" in p.stdout
    assert not glob.glob(os.path.join(sandbox.ws, "reports", "*.md"))


def test_ingest_keeps_existing_ids_and_unit(sandbox):
    data = result(open_items=[{"id": "OI-0042", "kind": "risk", "severity": "low", "summary": "s",
                               "evidence": "e", "target_stage": 5}], judgments=[])
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, data), "--stage", "2",
                    "--slice", "notice", "--unit", "core", "--name", "backend")
    assert p.returncode == 0, p.stderr
    path = glob.glob(os.path.join(sandbox.ws, "reports", "*_stage2_notice_unit-core_backend.md"))[0]
    meta = read_meta(path)
    assert meta["open_items"][0]["id"] == "OI-0042"
    assert meta["unit"] == "core"


def test_invalid_result_is_rejected_before_any_numbering(sandbox):
    data = result(judgments=[{"kind": "scope", "summary": "s", "rationale": "r", "check": "c", "verify_stage": 2}])
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, data), "--stage", "2", "--slice", "notice", "--name", "x")
    assert p.returncode != 0 and "verify_stage" in (p.stderr + p.stdout)
    assert not os.path.exists(os.path.join(sandbox.ws, "open-items.yaml"))
    assert not glob.glob(os.path.join(sandbox.ws, "reports", "*.md"))


def test_reviewer_verdict_in_result_is_moved_to_verdict(sandbox):
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, result(result="PASS")), "--stage", "2",
                    "--slice", "notice", "--name", "review")
    assert p.returncode == 0, p.stderr
    meta = read_meta(glob.glob(os.path.join(sandbox.ws, "reports", "*_review.md"))[0])
    assert meta["result"] == "done" and meta["verdict"] == "PASS"


def test_unknown_result_is_rejected(sandbox):
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, result(result="ok")), "--stage", "2",
                    "--slice", "notice", "--name", "x")
    assert p.returncode != 0 and "result=" in (p.stderr + p.stdout)


def test_ingest_uses_worktree_from_result_or_option(sandbox):
    # 병렬 작업 트리에서 일한 결과는 그 트리를 pa-meta repo 에 적는다(기본 target_dir 이 아니라)
    wt = os.path.join(sandbox.root, "target-wt")
    os.makedirs(wt)
    data = result(repo={"dir": wt, "base": "abc1234"})
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, data), "--stage", "2",
                    "--slice", "notice", "--name", "wt_from_result")
    assert p.returncode == 0, p.stderr
    meta = read_meta(glob.glob(os.path.join(sandbox.ws, "reports", "*_wt_from_result.md"))[0])
    assert meta["repo"]["dir"] == wt and meta["repo"]["base"] == "abc1234"
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, result()), "--stage", "2",
                    "--slice", "notice", "--name", "wt_from_option", "--target", wt, "--base", "def5678")
    assert p.returncode == 0, p.stderr
    meta = read_meta(glob.glob(os.path.join(sandbox.ws, "reports", "*_wt_from_option.md"))[0])
    assert meta["repo"]["dir"] == wt and meta["repo"]["base"] == "def5678"


def test_invalid_axis_is_rejected_before_any_numbering(sandbox):
    data = result()
    data["open_items"][1]["axis"] = "security"
    p = sandbox.run("ingest_result.py", "--json", write_json(sandbox, data), "--stage", "2",
                    "--slice", "notice", "--name", "bad_axis")
    assert p.returncode != 0 and "axis" in (p.stderr + p.stdout)
    assert not os.path.exists(os.path.join(sandbox.ws, "open-items.yaml")) or "OI-0001" not in open(
        os.path.join(sandbox.ws, "open-items.yaml"), encoding="utf-8").read()
