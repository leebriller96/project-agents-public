# slice_units.py · gate.py unit-scope · guard.py — 큰 slice 를 업무 프로세스 기준 unit 으로 나눌 때
# 분할이 안전한지(공유 클래스는 core, 전이·API 는 한 번씩, 흐름으로 이음매 검증)와 누락 없이 완료되는지를 확인한다.
# 예제(tests/fixtures/claim): 보험금 청구(claim)는 접수·심사·지급·조회 unit 으로 나눈 큰 slice, 이벤트(event)는 작은 slice.
import copy
import json
import os
import shutil
import subprocess
import sys

import yaml

from conftest import FIXTURES, REPO, dev_meta

sys.path.insert(0, os.path.join(REPO, "tools"))
import slice_units as su  # noqa: E402

CLAIM = os.path.join(FIXTURES, "claim")


def fixture_slices():
    with open(os.path.join(CLAIM, "slices.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["slices"]


def claim_entry(slices=None):
    return copy.deepcopy(su.find_slice(slices or fixture_slices(), "claim"))


def source(slices=None):
    return su.Source(CLAIM, slices or fixture_slices())


def fails(findings):
    return [f for f in findings if f["severity"] == "FAIL"]


def unit(entry, uid):
    return next(u for u in entry["units"] if u["id"] == uid)


# ---------------------------------------------------------------- 측정

def test_measure_reports_metrics_and_verdicts():
    res = su.measure(fixture_slices(), CLAIM, cfg={})
    rows = {r["slice"]: r for r in res["slices"]}
    m = rows["claim"]["metrics"]
    assert (m["apis"], m["screens"], m["transitions"], m["statements"], m["programs"]) == (5, 4, 4, 8, 8)
    assert m["asis_tokens"] > 0
    assert rows["claim"]["units"] == 5 and len(rows["claim"]["unit_rows"]) == 5
    assert rows["event"]["verdict"] == "merge"      # 작은 slice 는 묶기 후보


def test_threshold_from_config_makes_split_candidate():
    res = su.measure(fixture_slices(), CLAIM, cfg={"slicing": {"size": {"apis": 4}}})
    claim = next(r for r in res["slices"] if r["slice"] == "claim")
    assert claim["verdict"] == "split"
    assert any("API 5 > 4" in why for why in claim["reasons"])


def test_measure_without_source_uses_declarations_only():
    res = su.measure(fixture_slices(), None, cfg={})
    claim = next(r for r in res["slices"] if r["slice"] == "claim")
    assert "asis_tokens" not in claim["metrics"] and claim["metrics"]["apis"] == 5


# ---------------------------------------------------------------- 행렬 (slice 내부 공유)

def test_matrix_assigns_shared_code_to_core_and_rest_to_single_unit():
    res = su.derive(source(), claim_entry())
    assert fails(res["findings"]) == []
    a = res["assignment"]
    assert a["core"]["programs"] == ["ClaimDocHelper.java", "ClaimService.java"]
    # 심사만 쓰는 규칙 클래스는 선언하지 않아도 심사 unit 으로 따라간다
    assert a["review"]["programs"] == ["ClaimReviewAction.java", "ReviewRuleUtil.java"]
    # core 클래스가 부르는 statement 는 한 unit 만 써도 core (공유 Mapper 는 core 가 먼저 만든다)
    assert a["core"]["statements"] == ["claim.selectClaim", "claim.selectDupReceipt",
                                       "claim.selectRequiredDocs", "claim.updateStatus"]
    assert a["intake"]["statements"] == ["claim.insertClaim"]
    assert a["review"]["statements"] == ["claim.selectReviewDocs"]
    assert a["payment"]["statements"] == ["claim.insertPayment"]
    assert a["inquiry"]["statements"] == ["claim.selectClaimList"]
    assert res["discard"] == ["ClaimLegacyBatch.java"]


def test_shared_class_missing_from_core_is_blocked():
    """공통 클래스 분해 문제의 slice 내부판: 접수·심사가 함께 쓰는 도우미를 core 에 두지 않으면 각자 부분 이관한다."""
    e = claim_entry()
    unit(e, "core")["asis"]["programs"] = ["ClaimService.java"]
    f = fails(su.derive(source(), e)["findings"])
    assert any(x["field"] == "class.ClaimDocHelper.java" and "intake, review" in x["message"] for x in f)


def test_shared_class_owned_by_one_step_unit_is_blocked():
    e = claim_entry()
    unit(e, "core")["asis"]["programs"] = ["ClaimService.java"]
    unit(e, "intake")["asis"]["programs"].append("ClaimDocHelper.java")
    f = fails(su.derive(source(), e)["findings"])
    assert any(x["field"] == "class.ClaimDocHelper.java" and "review" in x["message"] for x in f)


def test_unassigned_unused_class_is_blocked_unless_discarded():
    e = claim_entry()
    e["asis"].pop("discard")
    f = fails(su.derive(source(), e)["findings"])
    assert any(x["field"] == "class.ClaimLegacyBatch.java" for x in f)


def test_statement_declared_in_wrong_unit_is_blocked():
    e = claim_entry()
    unit(e, "payment")["asis"]["statements"] = ["claim.selectClaim"]
    f = fails(su.derive(source(), e)["findings"])
    assert any(x["field"] == "statement.claim.selectClaim" and "core" in x["message"] for x in f)


def test_program_declared_in_two_units_is_blocked():
    e = claim_entry()
    unit(e, "inquiry")["asis"]["programs"].append("ClaimPayAction.java")
    assert any("중복" in x["message"] for x in fails(su.derive(source(), e)["findings"]))


# ---------------------------------------------------------------- 구조 (업무 프로세스 기준)

def test_fixture_structure_is_valid():
    assert fails(su.validate_structure(claim_entry())) == []


def structure_fail(mutate):
    e = claim_entry()
    mutate(e)
    return [x["field"] + " " + x["message"] for x in fails(su.validate_structure(e))]


def test_core_is_required_and_first():
    assert any("core unit 은 정확히 1개" in m for m in structure_fail(lambda e: e["units"].pop(0)))

    def move(e):
        e["units"].append(e["units"].pop(0))
    assert any("첫 번째" in m for m in structure_fail(move))


def test_every_unit_must_sit_on_core():
    def cut(e):
        unit(e, "inquiry")["depends_on"] = []
    assert any("core(core) 에 의존하지 않는다" in m for m in structure_fail(cut))


def test_core_carries_no_api_or_transition():
    def fat(e):
        unit(e, "core")["apis"] = ["GET /claims"]
    assert any("core 는 apis" in m for m in structure_fail(fat))


def test_units_require_process_transitions():
    assert any("process.transitions 가 없다" in m for m in structure_fail(lambda e: e.pop("process")))


def test_each_transition_owned_by_exactly_one_step():
    def drop(e):
        unit(e, "review")["transitions"] = ["접수 -> 심사완료"]
    assert any("접수 -> 보류 를 소유한 unit 이 없다" in m for m in structure_fail(drop))

    def dup(e):
        unit(e, "payment")["transitions"].append("접수 -> 보류")
    assert any("함께 소유" in m for m in structure_fail(dup))

    def query_owns(e):
        unit(e, "inquiry")["transitions"] = ["접수 -> 보류"]
    assert any("query unit 은 상태 전이를 가지지 않는다" in m for m in structure_fail(query_owns))

    def step_without(e):
        unit(e, "payment")["transitions"] = []
    assert any("소유한 상태 전이가 없다" in m for m in structure_fail(step_without))


def test_api_screen_requirement_partition():
    def missing(e):
        unit(e, "inquiry")["apis"] = ["GET /claims"]
    assert any("GET /claims/{no} 가 어느 unit 에도" in m for m in structure_fail(missing))

    def twice(e):
        unit(e, "review")["apis"].append("POST /claims")
    assert any("함께 가진다" in m for m in structure_fail(twice))

    def invented(e):
        unit(e, "payment")["screens"].append("SCR-999 없음")
    assert any("slice 에 없는 screens" in m for m in structure_fail(invented))

    def req(e):
        unit(e, "inquiry")["requirements"] = []
    assert any("REQ-204 가 어느 unit·flow 에도 없다" in m for m in structure_fail(req))


def test_flows_cover_every_unit_seam():
    assert any("flows 가 없다" in m for m in structure_fail(lambda e: e.pop("flows")))

    def drop(e):
        e["flows"] = e["flows"][:1]
    assert any("unit inquiry 가 어느 flow 에도 없다" in m for m in structure_fail(drop))

    def with_core(e):
        e["flows"][0]["units"].insert(0, "core")
    assert any("core 를 넣지 않는다" in m for m in structure_fail(with_core))


def test_unit_dependency_cycle_is_blocked():
    def cyc(e):
        unit(e, "intake")["depends_on"] = ["core", "payment"]
    assert any("순환" in m for m in structure_fail(cyc))


def test_order_puts_core_first_and_follows_process():
    waves, cyc = su.unit_waves(claim_entry()["units"])
    assert cyc == []
    assert [u for w in waves for u in w] == ["core", "intake", "inquiry", "review", "payment"]


def test_validate_warns_on_oversize_without_units_and_on_overuse():
    th = su.thresholds({"slicing": {"size": {"apis": 4}}})
    e = claim_entry()
    e.pop("units"), e.pop("flows")
    f, _m, v, _x = su.validate(e, None, th)
    assert v == "split" and any(x["field"] == "size" and x["severity"] == "WARN" for x in f)
    f2, _m, v2, _x = su.validate(claim_entry(), None, su.thresholds({}))
    assert v2 == "ok" and any("과분할" in x["message"] for x in f2)


def test_cli_validate_exit_codes(tmp_path):
    good = subprocess.run([sys.executable, os.path.join(REPO, "tools", "slice_units.py"), "--slices",
                           os.path.join(CLAIM, "slices.yaml"), "--source", CLAIM, "validate", "--format", "json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert good.returncode == 0, good.stdout + good.stderr
    data = yaml.safe_load(open(os.path.join(CLAIM, "slices.yaml"), encoding="utf-8"))
    next(s for s in data["slices"] if s["id"] == "claim")["units"][0]["asis"]["programs"] = ["ClaimService.java"]
    bad = tmp_path / "slices.yaml"
    bad.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    p = subprocess.run([sys.executable, os.path.join(REPO, "tools", "slice_units.py"), "--slices", str(bad),
                        "--source", CLAIM, "validate", "--slice", "claim", "--format", "json"],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 1 and json.loads(p.stdout)["blocked"] is True


# ---------------------------------------------------------------- 게이트 (unit-scope)

UNIT_ITEMS = {
    "core": ["ClaimDocHelper.java", "ClaimService.java", "claim.selectClaim", "claim.selectDupReceipt",
             "claim.selectRequiredDocs", "claim.updateStatus"],
    "intake": ["ClaimReceiptAction.java", "claim.insertClaim"],
    "review": ["ClaimReviewAction.java", "ReviewRuleUtil.java", "claim.selectReviewDocs"],
    "payment": ["ClaimPayAction.java", "claim.insertPayment"],
    "inquiry": ["ClaimQueryAction.java", "claim.selectClaimList"],
}
SEQ = ["core", "intake", "inquiry", "review", "payment"]


def setup_claim(sandbox, done_units=(), slice_backend="in_progress"):
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(CLAIM, "slices.yaml"), os.path.join(sandbox.ws, "slices", "slices.yaml"))
    sandbox.run("slice_units.py", "--source", CLAIM, "matrix", "--slice", "claim", check=0)
    write_state(sandbox, done_units, slice_backend)


def state_text(done_units, slice_backend="in_progress"):
    units = "".join(f"      {u}: {{stage2_backend: {'done' if u in done_units else 'pending'}}}\n" for u in SEQ)
    return ("iteration: 1\nstages:\n  stage3_common: pending\nslices:\n  claim:\n"
            f"    stage2_backend: {slice_backend}\n    units:\n" + units)


def write_state(sandbox, done_units, slice_backend="in_progress"):
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        f.write(state_text(done_units, slice_backend))


def unit_report(sandbox, uid, covered=None, ts="2609291000"):
    meta = dev_meta(slice="claim", unit=uid, asis_covered=UNIT_ITEMS[uid] if covered is None else covered)
    return sandbox.write_report(f"{ts}_stage2_claim_unit-{uid}_backend.md", meta)


def scope(p):
    return next(r for r in json.loads(p.stdout)["results"] if r["hook"] == "unit-scope")


def test_unit_report_must_cover_its_assigned_asis(sandbox):
    setup_claim(sandbox, done_units=["core"])
    unit_report(sandbox, "intake", covered=["ClaimReceiptAction.java"])
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--unit", "intake", "--format", "json")
    r = scope(p)
    assert p.returncode == 1 and r["result"] == "FAIL"
    assert any("claim.insertClaim" in x["message"] for x in r["findings"])
    unit_report(sandbox, "intake", ts="2609291100")
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--unit", "intake", "--format", "json")
    assert scope(p)["result"] == "PASS", p.stdout


def test_unit_cannot_finish_before_its_predecessor(sandbox):
    setup_claim(sandbox, done_units=["core"])
    unit_report(sandbox, "review")
    r = scope(sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--unit", "review", "--format", "json"))
    assert any(x["field"] == "depends_on.intake" for x in r["findings"])


def test_touching_another_units_asis_is_warned(sandbox):
    setup_claim(sandbox, done_units=["core"])
    unit_report(sandbox, "intake", covered=UNIT_ITEMS["intake"] + ["ClaimPayAction.java"])
    r = scope(sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--unit", "intake", "--format", "json"))
    assert r["result"] == "WARN" and any("payment 소유" in x["message"] for x in r["findings"])


def test_slice_report_is_not_picked_as_unit_report(sandbox):
    setup_claim(sandbox, done_units=SEQ)
    u = unit_report(sandbox, "payment", ts="2609291300")
    s = sandbox.write_report("2609291200_stage2_claim_backend.md", dev_meta(slice="claim"))
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--format", "json")
    assert json.loads(p.stdout)["report"] == s
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--unit", "payment", "--format", "json")
    assert json.loads(p.stdout)["report"] == u


def slice_meta(flow=True):
    meta = dev_meta(slice="claim")
    if flow:
        meta["gates"].append({"kind": "test", "suite": "flow", "command": "./gradlew test --tests '*Flow*'",
                              "exit_code": 0, "executed_at": "2026-09-28 10:58", "axis": "unit",
                              "test_count": 2, "failures": 0, "skipped": 0})
    return meta


def flow_tests(sandbox, ids=("FLOW-claim-01", "FLOW-claim-02")):
    d = os.path.join(sandbox.target, "backend", "src", "test", "java", "claim")
    os.makedirs(d, exist_ok=True)
    body = "\n".join(f'    @DisplayName("{i} 흐름") void f{n}() {{}}' for n, i in enumerate(ids))
    with open(os.path.join(d, "ClaimFlowTest.java"), "w", encoding="utf-8") as f:
        f.write("class ClaimFlowTest {\n" + body + "\n}\n")


def test_slice_done_requires_all_units_flows_and_full_coverage(sandbox):
    setup_claim(sandbox, done_units=["core", "intake", "inquiry", "review"])
    for u in ["core", "intake", "inquiry", "review"]:
        unit_report(sandbox, u)
    rpt = sandbox.write_report("2609291400_stage2_claim_backend.md", slice_meta(flow=False))
    r = scope(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json"))
    msgs = " ".join(x["message"] for x in r["findings"])
    assert "unit payment 가 끝나지 않았다" in msgs
    assert "ClaimPayAction.java" in msgs          # 전수 대조: 지급 unit 의 AS-IS 가 어느 레포트에도 없다
    assert "suite: flow" in msgs
    assert "FLOW-claim-01" in msgs                  # 흐름 id 를 인용한 테스트가 없다

    write_state(sandbox, SEQ)
    unit_report(sandbox, "payment")
    flow_tests(sandbox)
    rpt = sandbox.write_report("2609291500_stage2_claim_backend.md", slice_meta())
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    assert scope(p)["result"] == "PASS", p.stdout
    assert p.returncode == 0, p.stdout


def test_unit_report_for_slice_without_units_is_blocked(sandbox):
    setup_claim(sandbox)
    rpt = sandbox.write_report("2609291000_stage2_event_unit-x_backend.md", dev_meta(slice="event", unit="x"))
    r = scope(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json"))
    assert r["result"] == "FAIL"


def test_template_for_unit_and_split_slice(sandbox):
    setup_claim(sandbox)
    out = sandbox.run("gate.py", "template", "--stage", "2", "--slice", "claim", "--unit", "intake", check=0).stdout
    meta = json.loads(out.split("<!-- pa-meta:start", 1)[1].split("pa-meta:end -->", 1)[0])
    assert meta["unit"] == "intake" and meta["asis_covered"] == []
    out = sandbox.run("gate.py", "template", "--stage", "2", "--slice", "claim", check=0).stdout
    meta = json.loads(out.split("<!-- pa-meta:start", 1)[1].split("pa-meta:end -->", 1)[0])
    assert any(g.get("suite") == "flow" for g in meta["gates"]) and "unit" not in meta


def test_state_consistency_reads_unit_state(sandbox):
    setup_claim(sandbox, done_units=["core"])
    rpt = unit_report(sandbox, "intake")

    def consistency(intake_state):
        with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
            f.write(state_text(["core"]).replace("intake: {stage2_backend: pending}",
                                                 f"intake: {{stage2_backend: {intake_state}}}"))
        res = json.loads(sandbox.run("gate.py", "check", "--report", rpt, "--format", "json").stdout)["results"]
        return next(x for x in res if x["hook"] == "state-consistency")["result"]
    assert consistency("in_progress") == "PASS"    # slice 가 아니라 slices.claim.units.intake 를 본다
    assert consistency("blocked") == "FAIL"


# ---------------------------------------------------------------- 훅·계획·상태

def guard_edit(sandbox, new_text):
    path = os.path.join(sandbox.ws, "state.yaml")
    payload = {"tool_name": "Write", "tool_input": {"file_path": path, "content": new_text}}
    return subprocess.run([sys.executable, os.path.join(sandbox.root, "tools", "hooks", "guard.py"), "pre-tool-use"],
                          input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True,
                          encoding="utf-8", cwd=sandbox.root, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def test_hook_gates_unit_done_transition(sandbox):
    setup_claim(sandbox, done_units=["core"])
    unit_report(sandbox, "intake", covered=[])
    p = guard_edit(sandbox, state_text(["core", "intake"]))
    assert p.returncode == 2 and "units.intake" in p.stderr and "--unit intake" in p.stderr
    unit_report(sandbox, "intake", ts="2609291100")
    assert guard_edit(sandbox, state_text(["core", "intake"])).returncode == 0


def test_hook_judges_slice_done_with_the_new_state(sandbox):
    """마지막 unit 과 slice 완료를 한 번에 기록해도, 훅은 기록하려는 새 state 로 판정한다."""
    setup_claim(sandbox, done_units=["core", "intake", "inquiry", "review"])
    for u in SEQ:
        unit_report(sandbox, u)
    flow_tests(sandbox)
    sandbox.write_report("2609291500_stage2_claim_backend.md", slice_meta())
    p = guard_edit(sandbox, state_text(SEQ, slice_backend="done"))
    assert p.returncode == 0, p.stderr
    p = guard_edit(sandbox, state_text(["core", "intake", "inquiry", "review"], slice_backend="done"))
    assert p.returncode == 2 and "unit payment 가 끝나지 않았다" in p.stderr


def test_plan_lists_units_and_stops_on_broken_split(sandbox):
    setup_claim(sandbox, done_units=["core"])
    p = sandbox.run("gate.py", "plan", "--format", "json", check=0)
    plan = json.loads(p.stdout)
    assert plan["units"]["claim"]["sequence"] == SEQ and plan["units"]["claim"]["stage2_done"] == 1
    path = os.path.join(sandbox.ws, "slices", "slices.yaml")
    data = yaml.safe_load(open(path, encoding="utf-8"))
    next(s for s in data["slices"] if s["id"] == "claim")["flows"] = []
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)
    plan = json.loads(sandbox.run("gate.py", "plan", "--format", "json", check=0).stdout)
    assert any("unit 분할 구조 오류" in s for s in plan["stops"])


def test_status_shows_unit_progress(sandbox):
    setup_claim(sandbox, done_units=["core", "intake"])
    out = sandbox.run("status.py", check=0).stdout
    assert "5개 (2/0)" in out and "### claim — unit 진행" in out


# ---------------------------------------------------------------- 메서드 단위 배정 (거대 컨트롤러·서비스 구현체)
# 예제(tests/fixtures/bigctl): 주문(order) slice 의 진입점이 컨트롤러 하나·서비스 구현체 하나에 몰려 있다.
# unit 은 core·접수(receive)·승인(approve). 접수·승인은 요청 경로(apis)로 컨트롤러 메서드를 소유한다.

BIGCTL = os.path.join(FIXTURES, "bigctl")


def order_slices():
    with open(os.path.join(BIGCTL, "slices.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["slices"]


def order_entry(slices=None):
    return copy.deepcopy(su.find_slice(slices or order_slices(), "order"))


def order_source(slices=None):
    return su.Source(BIGCTL, slices or order_slices())


def test_order_fixture_is_valid():
    e = order_entry()
    assert fails(su.validate_structure(e)) == []
    assert fails(su.derive(order_source(), e)["findings"]) == []


def test_single_unit_methods_of_controller_and_service_go_to_that_unit():
    """(1) 컨트롤러·서비스 구현체의 한 unit 전용 메서드는 그 unit 에 배정된다 (클래스 통째로 core 에 올라가지 않는다)."""
    res = su.derive(order_source(), order_entry())
    a = res["assignment"]
    assert a["receive"]["methods"] == ["OrderController.java#insert", "OrderServiceImpl.java#insertOrder"]
    # 요청 경로 대조: /api 접두어·.do 확장자·메서드 접두어를 무시하고, 경로 없는 cancel 은 asis.methods 선언으로
    assert a["approve"]["methods"] == ["OrderController.java#approve", "OrderController.java#cancel",
                                       "OrderServiceImpl.java#approveOrder"]
    assert a["receive"]["programs"] == [] and a["approve"]["programs"] == []
    apis = {r["api"]: r["methods"] for r in res["apis"]}
    assert apis["POST /api/order/approve.do"] == ["OrderController.java#approve"]
    # 인터페이스(OrderService) 호출이 구현체 메서드에 닿는다
    rows = {r["id"]: r for r in res["methods"]}
    assert rows["OrderServiceImpl.java#insertOrder"]["used_by"] == ["receive"]
    assert res["discard"] == ["OrderController.java#legacyPrint"]


def test_shared_helper_and_util_go_to_core_util_as_whole_class():
    """(2) 두 unit 이 쓰는 private 헬퍼·공용 조회는 core 로, 공용 유틸은 클래스 통째로 core 에."""
    res = su.derive(order_source(), order_entry())
    core = res["assignment"]["core"]
    assert "OrderController.java#checkParam" in core["methods"]
    assert "OrderServiceImpl.java#writeHistory" in core["methods"]
    assert "OrderServiceImpl.java#getOrder" in core["methods"]
    # 선언부(필드·생성자)는 메서드가 두 unit 에 걸치므로 core 에 한 번
    assert "OrderController.java#<decl>" in core["methods"] and "OrderServiceImpl.java#<decl>" in core["methods"]
    # 유틸·인터페이스는 메서드 단위로 나누지 않는다
    assert core["programs"] == ["OrderService.java", "OrderUtil.java"]
    assert not any(m.startswith("OrderUtil") for u in res["assignment"].values() for m in u["methods"])
    util = next(r for r in res["classes"] if r["program"] == "OrderUtil.java")
    assert util["assigned"] == "core" and util["used_by"] == ["approve", "receive"] and not util.get("split")


def test_shared_util_not_declared_in_core_is_still_blocked():
    """공용 유틸은 종전 규칙 그대로 — 여러 unit 이 쓰면 core 선언이 필요하다(분해 금지)."""
    e = order_entry()
    unit(e, "core")["asis"]["programs"] = ["OrderService.java"]
    f = fails(su.derive(order_source(), e)["findings"])
    assert any(x["field"] == "class.OrderUtil.java" and "core 에 없다" in x["message"] for x in f)


def test_statement_follows_calling_method():
    """(3) statement 는 호출 메서드를 따라간다 — 같은 서비스 구현체 안이라도 메서드마다 다르다."""
    res = su.derive(order_source(), order_entry())
    a = res["assignment"]
    assert a["receive"]["statements"] == ["order.insertOrder"]
    assert a["approve"]["statements"] == ["order.updateApprove"]
    assert a["core"]["statements"] == ["order.insertHistory", "order.orderCols", "order.selectOrder"]
    st = {r["id"]: r for r in res["statements"]}
    assert st["order.updateApprove"]["callers"] == ["OrderServiceImpl.java#approveOrder"]


def test_unit_tokens_count_assigned_methods_not_whole_class():
    """(4) 토큰 추정은 배정 메서드 기준 — core 가 클래스 통째일 때보다 작고, 큰 접수 메서드는 접수 unit 에 잡힌다."""
    slices = order_slices()
    src, e = order_source(slices), order_entry(slices)
    res = su.derive(src, e)
    um = {u["id"]: su.unit_metrics(e, u, res["assignment"], src) for u in e["units"]}
    files = {os.path.basename(c.file): len(src.file_text[c.file]) for c in src.slice_classes("order")}
    whole_core = int((files["OrderController.java"] + files["OrderServiceImpl.java"] + files["OrderUtil.java"]
                      + files["OrderService.java"]) / 4)
    assert um["core"]["asis_tokens"] < whole_core * 0.6
    sizes = src.item_sizes("order")
    assert sizes["OrderController.java#insert"] > sizes["OrderController.java#approve"] * 3
    assert um["receive"]["asis_tokens"] >= int(sizes["OrderController.java#insert"] / 4)
    assert um["receive"]["methods"] == 2 and um["core"]["methods"] == 3


def test_core_over_limit_warns_with_largest_core_methods():
    th = su.thresholds({"slicing": {"size": {"apis": 1}, "unit_max": {"asis_tokens": 50}}})
    f, _m, _v, _x = su.validate(order_entry(), order_source(), th)
    w = next(x for x in f if x["field"] == "units.core.size" and "AS-IS 입력 토큰" in x["message"])
    assert w["severity"] == "WARN" and "크기 상위" in w["message"]
    assert "OrderServiceImpl.java#getOrder" in w["message"] and "OrderController.java#insert" not in w["message"]
    res = su.measure(order_slices(), BIGCTL, cfg={"slicing": {"unit_max": {"asis_tokens": 50}}})
    core = next(u for u in res["slices"][0]["unit_rows"] if u["unit"] == "core")
    assert core["top"] and all("#" in t["item"] for t in core["top"])


def test_unmatched_api_warns_and_unowned_controller_method_is_blocked():
    e = order_entry()
    e["apis"].append("GET /order/export")
    unit(e, "approve")["apis"].append("GET /order/export")
    unit(e, "approve")["asis"]["methods"] = []           # cancel 은 경로가 없어 어느 unit 도 소유하지 않는다
    f = su.derive(order_source(), e)["findings"]
    assert any(x["severity"] == "WARN" and "GET /order/export" in x["message"] for x in f)
    assert any(x["field"] == "method.OrderController.java#cancel" for x in fails(f))


def test_method_declared_in_one_unit_but_shared_is_blocked():
    e = order_entry()
    unit(e, "receive")["asis"] = {"methods": ["OrderServiceImpl#getOrder"]}
    f = fails(su.derive(order_source(), e)["findings"])
    assert any(x["field"] == "method.OrderServiceImpl.java#getOrder" and "approve" in x["message"] for x in f)
    e = order_entry()
    unit(e, "receive")["asis"] = {"methods": ["OrderController#nothing"]}
    assert any("찾지 못했다" in x["message"] for x in fails(su.derive(order_source(), e)["findings"]))


def test_old_matrix_without_methods_is_still_read():
    """(5) methods 키가 없는 옛 행렬(schema 1)도 validate·unit_items 가 읽는다."""
    old = {"core": {"programs": ["ClaimDocHelper.java", "ClaimService.java"], "statements": ["claim.selectClaim"]},
           "intake": {"programs": ["ClaimReceiptAction.java"], "statements": ["claim.insertClaim"]},
           "review": {"programs": ["ClaimReviewAction.java"], "statements": []},
           "payment": {"programs": ["ClaimPayAction.java"], "statements": []},
           "inquiry": {"programs": ["ClaimQueryAction.java"], "statements": []}}
    assert su.unit_items(old, "intake") == {"ClaimReceiptAction.java", "claim.insertClaim"}
    assert su.validate_assignment(claim_entry(), old) == []
    f, _m, _v, _x = su.validate(claim_entry(), None, su.thresholds({}), assignment=old)
    assert fails(f) == []
    # 소스가 있으면 지금 계산과 달라 재생성을 권하는 경고만 낸다
    f, _m, _v, _x = su.validate(claim_entry(), source(), su.thresholds({}), assignment=old)
    assert fails(f) == [] and any(x["field"] == "matrix" and x["severity"] == "WARN" for x in f)
    dup = copy.deepcopy(old)
    dup["review"]["programs"].append("ClaimReceiptAction.java")
    assert any("함께 배정" in x["message"] for x in fails(su.validate_assignment(claim_entry(), dup)))


def test_gate_reads_old_matrix_without_methods(sandbox):
    setup_claim(sandbox, done_units=["core"])
    path = os.path.join(sandbox.ws, "knowledge", "units", "claim.yaml")
    data = yaml.safe_load(open(path, encoding="utf-8"))
    for a in data["assignment"].values():
        a.pop("methods", None)
    data["schema"] = 1
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)
    unit_report(sandbox, "intake")
    p = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "claim", "--unit", "intake", "--format", "json")
    assert scope(p)["result"] == "PASS", p.stdout


def test_gate_requires_assigned_methods_in_unit_report(sandbox):
    os.makedirs(os.path.join(sandbox.ws, "slices"), exist_ok=True)
    shutil.copy(os.path.join(BIGCTL, "slices.yaml"), os.path.join(sandbox.ws, "slices", "slices.yaml"))
    sandbox.run("slice_units.py", "--source", BIGCTL, "matrix", "--slice", "order", check=0)
    with open(os.path.join(sandbox.ws, "state.yaml"), "w", encoding="utf-8") as f:
        f.write("iteration: 1\nstages:\n  stage3_common: pending\nslices:\n  order:\n    stage2_backend: in_progress\n"
                "    units:\n      core: {stage2_backend: done}\n      receive: {stage2_backend: pending}\n"
                "      approve: {stage2_backend: pending}\n")

    def check(covered, ts):
        sandbox.write_report(f"{ts}_stage2_order_unit-receive_backend.md",
                             dev_meta(slice="order", unit="receive", asis_covered=covered))
        return scope(sandbox.run("gate.py", "check", "--stage", "2", "--slice", "order", "--unit", "receive",
                                 "--format", "json"))
    r = check(["OrderController.java#insert", "order.insertOrder"], "2609291000")
    assert r["result"] == "FAIL" and any("OrderServiceImpl#insertOrder" in x["message"] for x in r["findings"])
    # 메서드 항목은 .java 유무를 같게 본다
    r = check(["OrderController#insert", "OrderServiceImpl.java#insertOrder", "order.insertOrder"], "2609291100")
    assert r["result"] == "PASS", r
    r = check(["OrderController#insert", "OrderServiceImpl.java#insertOrder", "order.insertOrder",
               "OrderController#approve"], "2609291200")
    assert r["result"] == "WARN" and any("approve 소유" in x["message"] for x in r["findings"])


def test_annotation_array_initializer_does_not_swallow_methods():
    # @RequestMapping(value={"/a.do", "/b.do"}) 의 '{' 를 멤버 본문으로 읽으면 다음 ';' 까지 건너뛰어
    # 뒤따르는 메서드가 통째로 빠졌다(실측: 실전 거대 컨트롤러 48개 중 20개만 인식).
    import _javasrc as js
    text = (
        "package x;\n"
        "@Controller\n"
        "public class OrderController {\n"
        "    @RequestMapping(value={\"/order/list.do\", \"/order/listPopup.do\"})\n"
        "    public String list(String a) { int n = 1; return \"list\"; }\n"
        "    @RequestMapping(\"/order/view.do\")\n"
        "    public String view(String a) { return \"view\"; }\n"
        "}\n")
    cls = js.parse_file("OrderController.java", text)
    names = [m.name for m in cls[0].methods]
    assert names == ["list", "view"]
    m = cls[0].methods[0]
    assert js.request_mappings(text, js.mask(text), m.start, m.body_start) == [([], ["/order/list.do", "/order/listPopup.do"])]


def test_method_split_program_needs_no_unit_programs_entry():
    # 진입점 클래스는 메서드 단위로 배정되므로 slice 의 asis.programs 에만 있고 unit 의 asis.programs 에 없어도 된다.
    # (종전 검사는 이를 FAIL 로 보아 거대 컨트롤러를 core 에 통째로 올리게 만들었다)
    entry = {"id": "order", "apis": [], "screens": [], "requirements": [],
             "asis": {"programs": ["OrderController.java", "OrderHelper.java"]},
             "process": {"states": ["접수"], "transitions": ["START -> 접수"]},
             "units": [{"id": "core", "kind": "core", "depends_on": []},
                       {"id": "a", "kind": "step", "depends_on": ["core"], "transitions": ["START -> 접수"],
                        "asis": {"methods": ["OrderController#cancel"]}},
                       {"id": "b", "kind": "query", "depends_on": ["core"]}],
             "flows": [{"id": "FLOW-order-01", "units": ["a", "b"]}]}
    msgs = [x["message"] for x in fails(su.validate_structure(entry))]
    assert not any("OrderController.java" in m for m in msgs)
    assert any("OrderHelper.java" in m for m in msgs)


def test_record_components_are_accessor_methods():
    # 실측: 대체 대응으로 적은 record 접근자를 파서가 몰라 계약 이행 검사가 '없다' 로 판정했다
    import _javasrc as js
    t = ("package a;\npublic record Meta(String userId, java.util.List<String> roles) implements X {\n"
         "  public String userId() { return userId; }\n  static int z() { return 1; }\n}\n")
    c = js.parse_file("Meta.java", t)[0]
    names = sorted((m.name, m.arity) for m in c.methods)
    assert names == [("roles", 0), ("userId", 0), ("z", 0)]   # 명시 선언한 userId 는 한 번만
