# 병렬 에이전트가 RR·OI 를 동시에 만들 때 번호 충돌·덮어쓰기가 없는지 (2026-09-28 재현된 결함의 회귀 테스트)
import glob
import os

import yaml

N = 16


def test_rr_new_parallel_keeps_every_request(sandbox):
    procs = [sandbox.popen("rr.py", "new", "--title", f"t{i}", "--slice", "s", "--severity", "low")
             for i in range(N)]
    outs = [p.communicate() for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    files = sorted(glob.glob(os.path.join(sandbox.ws, "refactor-requests", "RR-*.yaml")))
    assert [os.path.basename(f) for f in files] == [f"RR-{i:04d}.yaml" for i in range(1, N + 1)]
    titles = sorted(yaml.safe_load(open(f, encoding="utf-8"))["title"] for f in files)
    assert titles == sorted(f"t{i}" for i in range(N))
    # 발급된 id 가 파일 내용의 id 와 같고, 잠금 파일이 남지 않는다
    for f in files:
        assert yaml.safe_load(open(f, encoding="utf-8"))["id"] == os.path.basename(f)[:-5]
    assert not glob.glob(os.path.join(sandbox.ws, "refactor-requests", "*.lock"))


def test_oi_new_parallel_keeps_every_item(sandbox):
    procs = [sandbox.popen("gate.py", "oi", "new", "--stage", "2", "--slice", "s", "--kind", "unverified",
                           "--severity", "low", "--summary", f"o{i}", "--evidence", "x:1", "--target", "5")
             for i in range(N)]
    outs = [p.communicate() for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    items = yaml.safe_load(open(os.path.join(sandbox.ws, "open-items.yaml"), encoding="utf-8"))["items"]
    assert sorted(i["id"] for i in items) == [f"OI-{i:04d}" for i in range(1, N + 1)]
    assert sorted(i["summary"] for i in items) == sorted(f"o{i}" for i in range(N))
    assert not glob.glob(os.path.join(sandbox.ws, "*.lock"))


def test_rr_new_skips_existing_numbers(sandbox):
    """손으로 만든 파일이 있어도 덮어쓰지 않고 다음 번호를 쓴다."""
    d = os.path.join(sandbox.ws, "refactor-requests")
    os.makedirs(d)
    with open(os.path.join(d, "RR-0007.yaml"), "w", encoding="utf-8") as f:
        f.write("id: RR-0007\ntitle: 기존\n")
    out = sandbox.run("rr.py", "new", "--title", "새것", check=0).stdout.split()
    assert out[0] == "RR-0008"
    assert yaml.safe_load(open(os.path.join(d, "RR-0007.yaml"), encoding="utf-8"))["title"] == "기존"


def test_rr_set_updates_state_counts(sandbox):
    os.makedirs(sandbox.ws, exist_ok=True)
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        f.write("iteration: 3\n")
    sandbox.run("rr.py", "new", "--title", "a", "--severity", "high", check=0)
    sandbox.run("rr.py", "new", "--title", "b", "--severity", "low", check=0)
    sandbox.run("rr.py", "set", "RR-0001", "done", "--note", "수정함", check=0)
    st = yaml.safe_load(open(os.path.join(sandbox.ws, "state.yaml"), encoding="utf-8"))
    assert st["refactor_requests"]["done"] == 1 and st["refactor_requests"]["open"] == 1
    rr = yaml.safe_load(open(os.path.join(sandbox.ws, "refactor-requests", "RR-0002.yaml"), encoding="utf-8"))
    assert rr["iteration"] == 3
