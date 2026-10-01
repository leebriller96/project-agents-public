# visual.py + gate visual + 훅 — AI 가 볼 이미지만 고르고(토큰 추정), 승인 안 된 기준 이미지·실패 diff 를 차단하는지
import json
import os
import struct
import subprocess
import sys
import zlib

from conftest import dev_meta, REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import visual  # noqa: E402


def png(path, w, h, seed=0):
    """크기만 맞는 최소 PNG (IHDR + 빈 IDAT + IEND)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = zlib.compress(bytes([seed]) * 8)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


BASE = "frontend/e2e/__screenshots__/loan/list.spec.ts/loan-list-empty.png"
BASE2 = "frontend/e2e/__screenshots__/loan/list.spec.ts/loan-list-rows.png"
OTHER = "frontend/e2e/__screenshots__/deposit/list.spec.ts/deposit-list.png"
DIFF = "frontend/test-results/loan-list-rows/loan-list-rows-diff.png"


def test_token_estimate_matches_image_input_rule():
    assert visual.image_tokens(1280, 800) == 1366          # 1280*800/750
    # 큰 이미지는 긴 변 1568·약 1.15 메가픽셀로 축소되므로 장당 약 1,600 토큰을 넘지 않는다
    assert 1500 <= visual.image_tokens(3000, 2000) <= 1600
    assert visual.image_tokens(4000, 4000) <= 1600
    assert visual.image_tokens(0, 0) == 1600


def test_pending_lists_only_unapproved_and_failed(sandbox):
    for r in (BASE, BASE2, OTHER):
        png(os.path.join(sandbox.target, r), 1280, 800)
    r = sandbox.run("visual.py", "pending", "--slice", "loan", "--format", "json", check=0)
    res = json.loads(r.stdout)
    assert [i["file"] for i in res["items"]] == [BASE, BASE2] and res["estimated_tokens"] == 2 * 1366
    sandbox.run("visual.py", "approve", "--files", BASE, BASE2, "--by", "ui-verifier", check=0)
    assert sandbox.run("visual.py", "verify", "--slice", "loan").returncode == 0
    # 승인 후 기준 이미지가 바뀌면 다시 검토 대상, 실패 diff 도 검토 대상
    png(os.path.join(sandbox.target, BASE), 1280, 800, seed=7)
    png(os.path.join(sandbox.target, DIFF), 1280, 800)
    res = json.loads(sandbox.run("visual.py", "pending", "--slice", "loan", "--format", "json", check=0).stdout)
    assert sorted((i["reason"], i["file"]) for i in res["items"]) == [("changed-baseline", BASE), ("failed-diff", DIFF)]
    assert sandbox.run("visual.py", "verify", "--slice", "loan").returncode == 1


def test_diff_images_cannot_be_approved(sandbox):
    png(os.path.join(sandbox.target, DIFF), 100, 100)
    r = sandbox.run("visual.py", "approve", "--files", DIFF, "--by", "ui-verifier")
    assert r.returncode != 0 and "승인 대상이 아니다" in r.stderr


def test_budget_warning(sandbox):
    sandbox.write_config("verification:\n  visual:\n    review_budget_images: 1\n")
    for r in (BASE, BASE2):
        png(os.path.join(sandbox.target, r), 1280, 800)
    assert "예산(1장)" in sandbox.run("visual.py", "pending", check=0).stdout


def _hook(out, name):
    return next(r for r in json.loads(out)["results"] if r["hook"] == name)


def test_gate_visual_blocks_unapproved_when_enabled(sandbox):
    png(os.path.join(sandbox.target, BASE), 1280, 800)
    meta = dev_meta(slice="loan", stage=4)
    rpt = sandbox.write_report("2609281100_stage4_loan_frontend.md", meta)
    assert _hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "visual")["result"] == "SKIPPED"
    sandbox.write_config("verification:\n  visual:\n    enabled: true\n")
    assert _hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "visual")["result"] == "FAIL"
    sandbox.run("visual.py", "approve", "--files", BASE, "--by", "ui-verifier", check=0)
    assert _hook(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout, "visual")["result"] == "PASS"


def _guard(sandbox, payload):
    return subprocess.run([sys.executable, os.path.join(sandbox.root, "tools", "hooks", "guard.py"), "pre-tool-use"],
                          input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True,
                          encoding="utf-8", cwd=sandbox.root, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def test_human_approver_mode_blocks_agent_approval(sandbox):
    cmd = "python tools/visual.py " + "approve --files a.png --by ui-verifier"
    assert _guard(sandbox, {"tool_name": "Bash", "tool_input": {"command": cmd}}).returncode == 0
    sandbox.write_config("verification:\n  visual:\n    approver: human\n")
    assert _guard(sandbox, {"tool_name": "Bash", "tool_input": {"command": cmd}}).returncode == 2
    manifest = os.path.join(sandbox.ws, "visual", "approved.json")
    assert _guard(sandbox, {"tool_name": "Write", "tool_input": {"file_path": manifest, "content": "{}"}}).returncode == 2
