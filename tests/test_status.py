# tools/status.py — 상태 요약 표가 blocked_reason 의 '|' 로 깨지지 않고, unit 표에 그 unit 사유만 보이는지
import os

STATE = """project: demo
mode: migration
iteration: 1
stages:
  stage0_ingest: done
slices:
  claim:
    stage2_backend: in_progress
    stage4_frontend: pending
    stage5_integration: pending
    blocked_reason: hold - 사람 사유 | [unit intake.stage2_backend] 선행 대기 | [unit core.stage4_frontend] 화면 a|b
    units:
      core: {stage2_backend: done, stage4_frontend: blocked}
      intake:
        stage2_backend: blocked
        stage4_frontend: pending
      review: {stage2_backend: pending, stage4_frontend: pending}
"""


def _rows(out, head):
    lines = out.splitlines()
    i = lines.index(head)
    rows = []
    for ln in lines[i + 2:]:
        if not ln.startswith("|"):
            break
        rows.append(ln)
    return rows


def _cells(row):
    """이스케이프되지 않은 '|' 로만 칸을 나눈다."""
    out, cur, prev = [], "", ""
    for ch in row.strip()[1:-1]:
        if ch == "|" and prev != "\\":
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        prev = ch
    out.append(cur.strip())
    return out


def test_status_escapes_pipes_and_shows_unit_reason_only(sandbox):
    os.makedirs(sandbox.ws, exist_ok=True)
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(STATE)
    p = sandbox.run("status.py", check=0)
    srows = _rows(p.stdout, "| slice | stage2 BE | stage4 FE | stage5 통합 | unit (BE/FE 완료) | blocked 사유 |")
    cells = _cells(srows[0])
    assert len(cells) == 6, srows[0]                       # 열이 밀리지 않는다
    assert cells[5].startswith("hold - 사람 사유 \\| [unit intake.stage2_backend]")
    urows = {_cells(r)[0]: _cells(r) for r in _rows(p.stdout, "| unit | stage2 BE | stage4 FE | blocked 사유 |")}
    assert all(len(c) == 4 for c in urows.values())
    assert urows["intake"][3] == "[unit intake.stage2_backend] 선행 대기"
    assert urows["core"][3] == "[unit core.stage4_frontend] 화면 a\\|b"
    assert urows["review"][3] == ""
