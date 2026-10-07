# datasources.py — 데이터소스 지도 규격, 두 축 이관 판정, 외부 테이블 CREATE 금지 검사 (pipeline-core §22)
import json
import os
import sys

import yaml

from conftest import REPO, dev_meta

sys.path.insert(0, os.path.join(REPO, "tools"))
import common_contract as cc  # noqa: E402
import datasources as dsm  # noqa: E402

TEMPLATE = os.path.join(REPO, "templates", "DATASOURCES.yaml")


def ds_map(**over):
    """주(ds1, mysql 로 이관)·외부(ds2 mssql)·범위 밖(ds3) 세 데이터소스 지도. ds2 의 USER_INFO 는 주 테이블과 동명."""
    data = {
        "schema": 1, "target_engine": "mysql", "engine_basis": "prd",
        "datasources": [
            {"id": "ds1", "role": "main", "engine": "oracle", "tables": ["USER_INFO", "ORDER_MASTER"],
             "inbound_tables": [{"table": "IF_PERSON_RCV", "from": "인사 시스템", "evidence": "plan.md:10"}],
             "merged_tables": [{"table": "OTHER_CODE", "from": "ds3 계정 스키마", "evidence": "decisions.md:5"}]},
            {"id": "ds2", "role": "external", "engine": "mssql", "tables": ["dbo.User_Info", "PC_INFO", "[dbo].[POLICY_X]"]},
            {"id": "ds3", "role": "out_of_scope", "engine": "oracle", "tables": ["LEGACY_AUDIT", "OTHER_CODE"]},
        ],
        "unresolved_tables": ["IP_POOL"],
    }
    data.update(over)
    return data


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------- 규격

def test_template_is_valid():
    errs, warns = dsm.validate(dsm.load(TEMPLATE), dsm.base_dir(TEMPLATE))
    assert errs == [] and warns == []


def test_connection_keys_and_values_are_rejected(tmp_path):
    data = ds_map()
    data["datasources"][1]["url"] = "***"
    data["datasources"][1]["purpose"] = "jdbc:sqlserver://example"
    data["datasources"][2]["password"] = "***"
    errs, _ = dsm.validate(data, str(tmp_path))
    assert sum("접속 정보" in e for e in errs) == 2
    assert any("접속 문자열" in e for e in errs)


def test_exactly_one_main_and_known_roles(tmp_path):
    data = ds_map()
    data["datasources"][1]["role"] = "main"
    data["datasources"][2]["role"] = "remote"
    errs, _ = dsm.validate(data, str(tmp_path))
    assert any("정확히 하나" in e for e in errs)
    assert any("role 은" in e for e in errs)


def test_tables_from_file_must_exist_and_is_parsed(tmp_path):
    data = ds_map()
    data["datasources"][0]["tables_from"] = ["00_inputs/asis/schema.sql"]
    errs, _ = dsm.validate(data, str(tmp_path))
    assert any("tables_from 파일이 없다" in e for e in errs)
    write(str(tmp_path / "00_inputs" / "asis" / "schema.sql"),
          'CREATE TABLE "APP"."CODE_MASTER" (A NUMBER);\n-- CREATE TABLE NOT_THIS (A NUMBER);\n')
    errs, _ = dsm.validate(data, str(tmp_path))
    assert errs == []
    mains = dsm.main_tables(data, str(tmp_path))
    assert "CODE_MASTER" in mains and "NOT_THIS" not in mains


def test_inbound_and_merged_without_evidence_warn(tmp_path):
    data = ds_map()
    data["datasources"][0]["inbound_tables"] = ["IF_PERSON_RCV"]
    _, warns = dsm.validate(data, str(tmp_path))
    assert any("IF_PERSON_RCV" in w and "근거" in w for w in warns)


# ---------------------------------------------------------------- CREATE 추출

def test_extract_creates_handles_dialect_variants():
    sql = "\n".join([
        "CREATE TABLE IF NOT EXISTS `a_tab` (id int);",
        "create or replace view SCH.B_VIEW as select 1 from dual;",
        "CREATE PUBLIC SYNONYM C_SYN FOR OTHER.C_TAB;",
        "CREATE ALGORITHM=UNDEFINED DEFINER=`app`@`%` SQL SECURITY DEFINER VIEW `d_view` AS SELECT 1;",
        "CREATE TABLE [dbo].[E_TAB] (id int);",
        "CREATE GLOBAL TEMPORARY TABLE F_TMP (id int);",
        "/* CREATE TABLE G_COMMENTED (id int); */",
        "-- CREATE TABLE H_COMMENTED (id int);",
        "CREATE INDEX IX_A ON a_tab (id);",
    ])
    got = [(k, dsm.norm(n)) for _ln, k, n in dsm.extract_creates(sql, ".sql")]
    assert got == [("TABLE", "A_TAB"), ("VIEW", "B_VIEW"), ("SYNONYM", "C_SYN"), ("VIEW", "D_VIEW"),
                   ("TABLE", "E_TAB"), ("TABLE", "F_TMP")]


# ---------------------------------------------------------------- 판정

def test_judge_two_axes(tmp_path):
    data, base = ds_map(), str(tmp_path)
    # 외부 실행: 테이블 이름이 주 테이블과 같아도 원래 방언 유지
    r = dsm.judge(data, base, "ds2", ["User_Info"])
    assert r["decision"] == "keep_dialect" and r["dialect"] == "mssql" and "같은 이름" in r["reason"]
    # 주 실행 + 전부 이관 대상: 대상 방언 변환
    assert dsm.judge(data, base, "ds1", ["user_info", "ORDER_MASTER"])["decision"] == "convert"
    # 주 실행인데 이관 대상에 없는 테이블: 이관 안 함 (외부 동명이면 실행 세션 재확인 안내)
    r = dsm.judge(data, base, "ds1", ["ORDER_MASTER", "PC_INFO"])
    assert r["decision"] == "not_migrated" and "PC_INFO" in r["reason"] and "ds2" in r["reason"]
    # 범위 밖 데이터소스
    assert dsm.judge(data, base, "ds3", ["LEGACY_AUDIT"])["decision"] == "out_of_scope"
    assert dsm.judge(data, base, "ds9", ["X"])["decision"] == "error"
    # 수신 테이블 쓰기 주의
    assert "수신 테이블" in dsm.judge(data, base, "ds1", ["IF_PERSON_RCV"], write=True)["reason"]


# ---------------------------------------------------------------- CREATE 금지 검사

def make_target(root):
    mig = os.path.join(root, "server", "common", "src", "main", "resources", "db", "migration")
    write(os.path.join(mig, "V1__ok.sql"),
          "CREATE TABLE ORDER_MASTER (id int);\nCREATE TABLE IF NOT EXISTS `user_info` (id int);\n"
          "CREATE TABLE IF_PERSON_RCV (id int);\nCREATE TABLE OTHER_CODE (id int);\n")
    write(os.path.join(mig, "V2__bad.sql"),
          "-- 외부 테이블을 실수로 만든다\nCREATE TABLE pc_info (id int);\nCREATE OR REPLACE VIEW LEGACY_AUDIT AS SELECT 1;\n"
          "CREATE SYNONYM IP_POOL FOR X.IP_POOL;\n")
    write(os.path.join(mig, "..", "seed", "V3__seed.sql"), "INSERT INTO IF_PERSON_RCV VALUES (1);\n")
    write(os.path.join(root, "server", "user", "src", "main", "resources", "mapper", "PersonMapper.xml"),
          '<mapper namespace="x">\n<update id="u">\n  UPDATE if_person_rcv SET a = 1\n</update>\n</mapper>\n')
    write(os.path.join(root, "server", "user", "src", "test", "java", "PersonTest.java"),
          'class PersonTest { String s = "CREATE TABLE POLICY_X (id int)"; String w = "DELETE FROM IF_PERSON_RCV"; }\n')
    write(os.path.join(root, "server", "user", "target", "classes", "V2__bad.sql"), "CREATE TABLE PC_INFO (id int);\n")


def test_scan_blocks_external_creates_and_allows_owned(tmp_path):
    td = str(tmp_path / "t")
    make_target(td)
    res = dsm.scan_ddl(td, ds_map(), str(tmp_path))
    crit = sorted((f["table"], f["object"]) for f in res["findings"] if f["severity"] == "critical")
    # 외부(ds2)·범위 밖(ds3)·미확정 외부 테이블, 테스트 코드 문자열 안의 DDL 도 금지. 빌드 산출물(target/)은 보지 않는다
    assert crit == [("IP_POOL", "SYNONYM"), ("LEGACY_AUDIT", "VIEW"), ("POLICY_X", "TABLE"), ("pc_info", "TABLE")]
    info = {f["table"]: f["kind"] for f in res["findings"] if f["severity"] == "info"}
    # 동명(주 이관 대상이면서 외부에도 있음)·수신·합침은 허용(정보)
    assert info == {"`user_info`": "overlap", "IF_PERSON_RCV": "inbound", "OTHER_CODE": "overlap"}
    warns = [(f["file"], f["kind"]) for f in res["findings"] if f["severity"] == "warn"]
    # 수신 테이블 쓰기는 src/main 의 Mapper 만 경고 — 시드 SQL·테스트 코드는 대상 아님
    assert warns == [("server/user/src/main/resources/mapper/PersonMapper.xml", "inbound_write")]
    assert res["counts"] == {"critical": 4, "warn": 1, "info": 3}


def test_scan_with_files_checks_changed_code_plus_all_sql(tmp_path):
    td = str(tmp_path / "t")
    make_target(td)
    res = dsm.scan_ddl(td, ds_map(), str(tmp_path), files=["server/user/src/main/resources/mapper/PersonMapper.xml"])
    crit = sorted(f["table"] for f in res["findings"] if f["severity"] == "critical")
    assert crit == ["IP_POOL", "LEGACY_AUDIT", "pc_info"]   # 바뀌지 않은 테스트 Java 는 보지 않지만 SQL 은 항상 본다
    assert res["mode"] == "files+sql"


def test_scan_is_deterministic(tmp_path):
    td = str(tmp_path / "t")
    make_target(td)
    a = json.dumps(dsm.scan_ddl(td, ds_map(), str(tmp_path)), ensure_ascii=False, sort_keys=True)
    b = json.dumps(dsm.scan_ddl(td, ds_map(), str(tmp_path)), ensure_ascii=False, sort_keys=True)
    assert a == b


# ---------------------------------------------------------------- 명령행·게이트

def put_map(sandbox, data):
    p = os.path.join(sandbox.ws, "knowledge", "DATASOURCES.yaml")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return p


def test_cli_check_skips_without_map_and_blocks_with_violation(sandbox):
    p = sandbox.run("datasources.py", "check", check=0)
    assert "[생략]" in p.stdout
    make_target(sandbox.target)
    put_map(sandbox, ds_map())
    p = sandbox.run("datasources.py", "check", check=1)
    assert "critical 4" in p.stdout
    os.remove(os.path.join(sandbox.target, "server", "common", "src", "main", "resources", "db", "migration", "V2__bad.sql"))
    os.remove(os.path.join(sandbox.target, "server", "user", "src", "test", "java", "PersonTest.java"))
    sandbox.run("datasources.py", "check", check=0)


def hook(sandbox, meta):
    rpt = sandbox.write_report("2610021200_stage2_notice_backend.md", meta)
    p = sandbox.run("gate.py", "check", "--report", rpt, "--format", "json")
    return next(r for r in json.loads(p.stdout)["results"] if r["hook"] == "datasource-ddl")


def test_gate_hook_warns_without_map_in_migration(sandbox):
    sandbox.write_config("  mode: migration\n")
    r = hook(sandbox, dev_meta())
    assert r["result"] == "WARN" and "건너뛰었다" in r["findings"][0]["message"]
    sandbox.write_config("")
    assert hook(sandbox, dev_meta())["result"] == "SKIPPED"


def test_gate_hook_blocks_external_create_and_bad_map(sandbox):
    make_target(sandbox.target)
    put_map(sandbox, ds_map())
    r = hook(sandbox, dev_meta())
    assert r["result"] == "FAIL"
    assert sum(f["severity"] == "FAIL" for f in r["findings"]) == 4
    bad = ds_map()
    bad["datasources"][1]["password"] = "***"
    put_map(sandbox, bad)
    r = hook(sandbox, dev_meta(stage=1, slice="all"))
    assert r["result"] == "FAIL" and any("접속 정보" in f["message"] for f in r["findings"])


# ---------------------------------------------------------------- 공통 계약 표시

def test_contract_external_statement_needs_original_dialect():
    m = ds_map()
    base = {"kind": "statement", "owner": "slice:firewall", "decision": "", "status": "pending", "used_by": ["firewall"]}
    ok = dict(base, id="CC-1", asis="nmc.list", datasource="ds2", dialect="mssql")
    wrong = dict(base, id="CC-2", asis="nmc.get", datasource="ds2", dialect="mysql")
    missing = dict(base, id="CC-3", asis="nmc.put", datasource="ds2")
    unknown = dict(base, id="CC-4", asis="nmc.del", datasource="ds9", dialect="oracle")
    oos = dict(base, id="CC-5", asis="old.x", datasource="ds3", dialect="oracle")
    errs = cc.validate({"items": [ok, wrong, missing, unknown, oos]}, m)
    assert not any(e.startswith("CC-1") for e in errs)
    assert any(e.startswith("CC-2") and "원래 방언" in e for e in errs)
    assert any(e.startswith("CC-3") and "원래 방언" in e for e in errs)
    assert any(e.startswith("CC-4") and "지도" in e for e in errs)
    assert any(e.startswith("CC-5") and "범위 밖" in e for e in errs)
    # 지도가 없으면 datasource 표시에 dialect 만 요구한다
    assert any("dialect" in e for e in cc.validate({"items": [missing]}, None))
    assert cc.validate({"items": [ok]}, None) == []


def test_contract_init_preserves_datasource_marks():
    prev = {"id": "CC-7", "asis": "nmc.list", "suggestion": "slice:firewall", "owner": "slice:firewall",
            "decision": "", "datasource": "ds2", "dialect": "mssql", "status": "pending"}
    it = {"asis": "nmc.list", "suggestion": "slice:firewall", "owner": "slice:firewall", "decision": "", "status": "pending"}
    cc.merge_prev(it, prev)
    assert it["datasource"] == "ds2" and it["dialect"] == "mssql"


def test_local_stub_exception_is_human_only_and_file_scoped(tmp_path):
    # 실측: 2차가 외부 데이터소스 뷰를 로컬 시험용 테이블로 흉내 낸 기존 파일 - 사람 예외로만 warn, 다른 파일의 같은 CREATE 는 그대로 차단
    td = str(tmp_path / "t")
    mig = os.path.join(td, "server", "common", "src", "main", "resources", "db", "migration")
    write(os.path.join(mig, "600_test_data", "V9__stub.sql"), "CREATE TABLE pc_info (id int);\n")
    write(os.path.join(mig, "V10__real.sql"), "CREATE TABLE pc_info (id int);\n")
    stub = {"table": "PC_INFO", "files": ["server/common/*/600_test_data/V9__stub.sql"],
            "evidence": "local 프로필에서만 migration", "decided_by": "사람:홍길동(2026-10-02)"}
    data = ds_map(local_stubs=[stub])
    errs, _w = dsm.validate(data, str(tmp_path))
    assert errs == []
    res = dsm.scan_ddl(td, data, str(tmp_path))
    sev = sorted((f["file"].rsplit("/", 1)[-1], f["severity"], f["kind"]) for f in res["findings"])
    assert sev == [("V10__real.sql", "critical", "external_create"), ("V9__stub.sql", "warn", "local_stub")]
    # 에이전트 결정·시험 데이터가 아닌 경로·근거 없음은 지도 오류
    bad = ds_map(local_stubs=[dict(stub, decided_by="에이전트:x"), dict(stub, files=["db/migration/V1.sql"]),
                              dict(stub, evidence="")])
    errs, _w = dsm.validate(bad, str(tmp_path))
    assert len(errs) == 3


# ---------------------------------------------------------------- 기존 부채 기준선 (brownfield, BG-02)

def baseline_entry(**over):
    e = {"table": "PC_INFO", "files": ["server/common/src/main/resources/db/migration/V2__bad.sql"],
         "found_at": "2610051544", "evidence": "0단계 지도 최초 작성 회차에 이미 있었다", "decision_oi": "OI-0008"}
    e.update(over)
    return e


def test_pre_existing_violation_becomes_warn_and_new_one_stays_critical(tmp_path):
    """검출 방향과 미검출 방향을 둘 다 본다 (pipeline-core §14-10).

    brownfield 에서 지도를 처음 만들면 기존 코드의 위반이 critical 로 쏟아져 다음 단계의 첫 slice 가
    자기 변경과 무관하게 막힌다. 등록된 부채만 warn 으로 내리고 **새로 생긴 것은 critical 로 남아야** 한다.
    """
    td = str(tmp_path / "t")
    make_target(td)
    res = dsm.scan_ddl(td, ds_map(pre_existing_violations=[baseline_entry()]), str(tmp_path))
    byt = {f["table"]: f["severity"] for f in res["findings"]}
    assert byt["pc_info"] == "warn"                       # 등록된 부채 -> 내려갔다
    assert byt["LEGACY_AUDIT"] == "critical"              # 등록 안 한 것 -> 그대로 막는다
    assert byt["POLICY_X"] == "critical"
    pe = next(f for f in res["findings"] if f["kind"] == "pre_existing")
    assert pe["decision_oi"] == "OI-0008" and "OI-0008" in pe["detail"]
    assert res["counts"]["critical"] == 3                 # 4 -> 3

    # 같은 테이블이라도 등록한 파일 밖이면 내려가지 않는다 (예외가 파일 단위다)
    other = baseline_entry(files=["server/other/**"])
    res2 = dsm.scan_ddl(td, ds_map(pre_existing_violations=[other]), str(tmp_path))
    assert {f["table"]: f["severity"] for f in res2["findings"]}["pc_info"] == "critical"


def test_pre_existing_violation_requires_decision_oi(tmp_path):
    """부채가 영구 면제가 되지 않게 닫을 확인 필요 항목을 반드시 달게 한다."""
    base = str(tmp_path)
    for bad, want in ((baseline_entry(decision_oi=""), "decision_oi"),
                      (baseline_entry(decision_oi="나중에"), "decision_oi"),
                      (baseline_entry(evidence=""), "evidence"),
                      (baseline_entry(found_at=""), "found_at"),
                      (baseline_entry(files=[]), "files")):
        errs, _ = dsm.validate(ds_map(pre_existing_violations=[bad]), base)
        assert any(want in e for e in errs), (bad, errs)
    # 제대로 채운 것은 통과한다 (미검출 방향)
    errs, _ = dsm.validate(ds_map(pre_existing_violations=[baseline_entry()]), base)
    assert errs == []


def test_stale_baseline_entry_is_reported(tmp_path):
    """해소된 부채가 목록에 남아 기준선이 썩는 것을 알린다."""
    td = str(tmp_path / "t")
    make_target(td)
    gone = baseline_entry(table="GONE_TABLE", files=["server/**"])
    res = dsm.scan_ddl(td, ds_map(pre_existing_violations=[baseline_entry(), gone]), str(tmp_path))
    assert any("GONE_TABLE" in s for s in res["stale_baseline"])
    assert not any("PC_INFO" in s for s in res["stale_baseline"])
    # 파일 목록을 준 부분 검사에서는 안 걸리는 것이 정상이므로 보지 않는다
    res2 = dsm.scan_ddl(td, ds_map(pre_existing_violations=[gone]), str(tmp_path), files=[])
    assert res2["stale_baseline"] == []
