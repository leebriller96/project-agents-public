# runtime_config.py — AS-IS 실행 자원 설정 추출·판정·검사
import os
import sys

from conftest import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import runtime_config as rc  # noqa: E402

SCHED = """<beans>
  <!-- <task:scheduler id="old" pool-size="99"/> -->
  <task:scheduler id="common" pool-size="10"/>
  <bean id="ds" class="org.apache.commons.dbcp.BasicDataSource">
    <property name="maxActive" value="5"/>
    <property name="url" value="jdbc:x"/>
  </bean>
  <bean id="mr" class="CommonsMultipartResolver"><property name="maxInMemorySize" value="500000000"/></bean>
</beans>
"""


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def make_asis(tmp_path):
    a = tmp_path / "asis"
    write(str(a / "WEB-INF" / "scheduler.xml"), SCHED)
    write(str(a / "WEB-INF" / "web.xml"), "<web-app><session-config><session-timeout>30</session-timeout></session-config></web-app>\n")
    write(str(a / "conf" / "db.properties"), "# jdbc.maxWait=1\njdbc.maxWait=10000\njdbc.url=jdbc:x\n")
    write(str(a / "profile" / "dev" / "scheduler.xml"), SCHED)
    return str(a)


def test_scan_finds_runtime_keys_and_skips_comments(tmp_path):
    out = str(tmp_path / "k" / "rc.yaml")
    assert rc.main(["scan", "--asis", make_asis(tmp_path), "--exclude", "profile/*", "--out", out]) == 0
    items = rc.load(out)
    got = {(i["key"], i["value"], i["category"]) for i in items}
    assert ("pool-size", "10", "thread") in got
    assert ("maxActive", "5", "db-pool") in got
    assert ("maxInMemorySize", "500000000", "upload") in got
    assert ("session-timeout", "30", "session") in got
    assert ("jdbc.maxWait", "10000", "db-pool") in got
    assert not any(i["value"] == "99" for i in items)               # 주석 안 설정
    assert not any(i["file"].startswith("profile/") for i in items)   # 제외 glob
    assert os.path.isfile(str(tmp_path / "k" / "rc.md"))


def test_check_requires_verdicts_and_evidence(tmp_path):
    out = str(tmp_path / "rc.yaml")
    rc.main(["scan", "--asis", make_asis(tmp_path), "--exclude", "profile/*", "--out", out])
    assert rc.main(["check", "--out", out]) == 1                       # 전부 미판정
    # 프레임워크 기본값(1)이 AS-IS(10)와 다른데 JD 없이 default-ok -> 여전히 실패
    rc.main(["set", "--key", "pool-size", "--verdict", "default-ok", "--default", "1", "--out", out])
    rc.main(["set", "--key", "*", "--file", "WEB-INF/web.xml", "--verdict", "same",
             "--tobe", "application.yml:server.servlet.session.timeout=30m", "--out", out])
    rc.main(["set", "--key", "maxActive", "--verdict", "changed", "--tobe", "application.yml:maximum-pool-size=10",
             "--out", out])
    rc.main(["set", "--key", "maxInMemorySize", "--verdict", "n/a", "--note", "업로드는 공통 첨부로 대체", "--out", out])
    rc.main(["set", "--key", "jdbc.maxWait", "--verdict", "default-ok", "--default", "10000", "--out", out])
    bad = dict(rc.problems(rc.load(out)))
    assert len(bad) == 2
    assert any("JD-" in why and "기본값" in why for why in bad.values())   # pool-size
    assert any("changed" in why for why in bad.values())                    # maxActive
    rc.main(["set", "--key", "pool-size", "--verdict", "changed", "--tobe", "application.yml:pool.size=10",
             "--note", "JD-0001", "--out", out])
    rc.main(["set", "--key", "maxActive", "--verdict", "changed", "--note", "JD-0002", "--out", out])
    assert rc.main(["check", "--out", out]) == 0


def test_rescan_keeps_verdicts(tmp_path):
    out = str(tmp_path / "rc.yaml")
    asis = make_asis(tmp_path)
    rc.main(["scan", "--asis", asis, "--exclude", "profile/*", "--out", out])
    rc.main(["set", "--key", "pool-size", "--verdict", "same", "--tobe", "x.yml:a=10", "--out", out])
    write(os.path.join(asis, "WEB-INF", "a_first.xml"), '<task:executor id="e" pool-size="4"/>\n')
    rc.main(["scan", "--asis", asis, "--exclude", "profile/*", "--out", out])
    items = rc.load(out)
    old = [i for i in items if i["file"] == "WEB-INF/scheduler.xml" and i["key"] == "pool-size"][0]
    new = [i for i in items if i["file"] == "WEB-INF/a_first.xml"][0]
    assert old["verdict"] == "same" and new["verdict"] == "pending"
