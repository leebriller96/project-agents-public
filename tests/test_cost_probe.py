# tools/cost_probe.py — Claude Code 기록에서 캐시 읽기를 정확히 세고 원인을 줄 세우는지
import json
import os

COST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


def _asst(mid, ts, cr, cw, blocks):
    usage = {"input_tokens": 1, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw, "output_tokens": 10}
    # 한 응답이 블록마다 한 줄씩 기록되고 usage 가 반복된다
    return [{"type": "assistant", "timestamp": ts, "message": {"id": mid, "model": "m", "usage": usage, "content": [b]}}
            for b in blocks]


def _result(tid, text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def _write(path, recs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_dedup_subagent_type_contribution_and_cache_expiry(tmp_path, sandbox):
    proj = tmp_path / "proj"
    recs = []
    recs += _asst("m1", "2026-10-01T00:00:00Z", 1000, 9000,
                  [{"type": "thinking"}, {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cd x && mvn test"}}])
    recs.append(_result("t1", "x" * 33000))   # 약 1만 토큰
    recs += _asst("m2", "2026-10-01T00:01:00Z", 20000, 100,
                  [{"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/r/.claude/skills/a/SKILL.md"}}])
    recs.append(_result("t2", "짧음"))
    recs += _asst("m3", "2026-10-01T00:20:00Z", 0, 21000, [{"type": "text", "text": "끝"}])   # 19분 공백 뒤 재작성
    _write(str(proj / "s1.jsonl"), recs)
    sub = proj / "s1" / "subagents"
    _write(str(sub / "agent-x.jsonl"), _asst("a1", "2026-10-01T00:00:00Z", 500, 0, [{"type": "text", "text": "a"}]))
    (sub / "agent-x.meta.json").write_text(json.dumps({"agentType": "backend-developer"}), encoding="utf-8")

    p = sandbox.run("cost_probe.py", str(proj), "--format", "json", check=0)
    res = json.loads(p.stdout)
    g = res["totals"]
    assert g["calls"] == 4                      # m1 이 두 줄이어도 한 번만 센다
    assert g["cache_read"] == 1000 + 20000 + 0 + 500
    assert g["expiry_rewrites"] == 1
    types = {t["agent"]: t for t in res["agent_types"]}
    assert types["backend-developer"]["n"] == 1 and types["(메인)"]["calls"] == 3
    top = res["categories"][0]
    assert top["key"] == "Bash mvn" and top["contrib"] == 10000 * 2   # 그 뒤 호출 2번에서 다시 읽힘
    assert any("만료" in a for a in res["advice"])
    human = sandbox.run("cost_probe.py", str(proj), check=0).stdout
    assert "캐시 읽기" in human and "Bash mvn" in human


def test_compaction_stops_contribution(tmp_path, sandbox):
    recs = _asst("m1", "2026-10-01T00:00:00Z", 0, 100,
                 [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pnpm test"}}])
    recs.append(_result("t1", "y" * 3300))
    recs.append({"type": "system", "subtype": "compact_boundary"})
    for i in range(5):
        recs += _asst(f"m{i + 2}", "2026-10-01T00:00:10Z", 100, 0, [{"type": "text", "text": "."}])
    _write(str(tmp_path / "p" / "s.jsonl"), recs)
    res = json.loads(sandbox.run("cost_probe.py", str(tmp_path / "p"), "--format", "json", check=0).stdout)
    assert all(c["contrib"] == 0 for c in res["categories"] if c["key"] == "Bash pnpm test")


def test_instruction_files_are_broken_down_and_out_file_is_utf8(tmp_path, sandbox):
    big = "가" * 3000
    recs = [{"type": "attachment", "attachment": {"type": "instructions", "files": [
        {"path": "C:\\proj\\CLAUDE.md", "type": "Project", "content": big},
        {"path": "C:\\proj\\external\\x\\CLAUDE.md", "type": "Project", "content": "짧음"}]}}]
    for i in range(3):
        recs += _asst(f"m{i}", "2026-10-01T00:00:00Z", 100, 0, [{"type": "text", "text": "."}])
    _write(str(tmp_path / "p" / "s.jsonl"), recs)
    res = json.loads(sandbox.run("cost_probe.py", str(tmp_path / "p"), "--format", "json", check=0).stdout)
    files = {f["path"]: f for f in res["instruction_files"]}
    assert files["C:/proj/CLAUDE.md"]["avg_chars"] == 3000 and files["C:/proj/CLAUDE.md"]["contrib"] == 2700 * 3
    out = tmp_path / "cost.txt"
    p = sandbox.run("cost_probe.py", str(tmp_path / "p"), "--out", str(out), check=0)
    assert "결과 저장" in p.stdout
    text = out.read_text(encoding="utf-8")
    assert "자동으로 올라오는 지침 파일" in text and "C:/proj/CLAUDE.md" in text
