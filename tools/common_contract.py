#!/usr/bin/env python3
# common_contract.py — 공통 계약(common contract): 공통 코드의 소유·결정·TO-BE 대응을 업무 변환 전에 한 번 확정한다
#
# 흐름: common_usage.py(사용 행렬) → init(계약 초안) → 사람이 owner·decision 검토 → approve(사람만)
#       → common-porter 가 공통을 먼저 변환(tobe·status 기입) → 업무 slice 는 계약을 소비만 한다.
#       업무 slice 가 필요한 공통이 계약에 없으면 request(공통 요청 CR) 로 올리고, 직접 만들거나 복제하지 않는다.
#
# 사용법:
#   python tools/common_contract.py init [--usage <COMMON_USAGE.yaml>] [--out <계약 파일>]   # 초안 생성·병합(사람 결정 보존)
#   python tools/common_contract.py validate                          # 결정 누락·모순 검사 (종료 코드 1 = 문제)
#   python tools/common_contract.py status                            # owner·decision·status 집계
#   python tools/common_contract.py approve --by <이름>              # 승인 — 사람이 직접 터미널에서 실행 (훅이 에이전트 실행을 막는다)
#   python tools/common_contract.py request --slice <id> --asis "<클래스#메서드/인자수>" --reason "…"   # 공통 요청(CR)
#   python tools/common_contract.py check --slice <id> --files <변경 파일…>  # 공통 복제·소유 침범 검사 (gate 가 같은 함수를 쓴다)
#
# owner 값: common(공통 모듈이 소유) | slice:<id>(그 업무로 내림 — 사람 결정) | discard(폐기) | review(사람 판단 대기)
#           | none(이관 안 함 — 어느 slice 도 도달하지 않는 항목의 일괄 판정, status: not_migrated)
# decision 값(owner=common 일 때): 계승 | 대체 | 개선 (stage3-common §3-1 의 4분류와 같다. 폐기는 owner=discard)
#
# 미사용 일괄 규칙: 어느 slice 에서도 도달 경로가 없는 공통 메서드·공통 namespace statement 는 개별 review 로 올리지 않고
#   owner: none · status: not_migrated 로 일괄 판정해 계약 옆 목록 파일(<계약>-not-migrated.yaml)에만 남긴다.
#   단, slice 소유 namespace 의 미사용 statement 와 slice 소유 클래스의 미사용 public 메서드는 개별 review 로 남긴다.
#   목록 파일에서 사람이 owner 를 none 이 아닌 값(common·discard·slice:<id>)으로 바꾸면 다음 init 이 계약 항목으로 올린다.
# 모듈(config project.modules 가 있고 행렬이 modules 를 계산했을 때): owner=common 항목에 module 을 붙인다.
#   한 모듈의 slice 들만 쓰면 module: <모듈>, 여러 모듈이 쓰면 module: [모듈...] · copy: true(모듈별 복사본이 기본).
#   인증·권한처럼 전 모듈 기반으로 올릴 항목은 사람이 module: <project.common_module> 로 바꾼다(copy 없음).
# 의존성: pyyaml

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (ROOT, config, create_numbered_file, dump_yaml, file_lock, fix_console_encoding,  # noqa: E402
                     load_yaml, safe_relpath, target_dir, workspace)
import _javasrc as js  # noqa: E402

fix_console_encoding()

KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")
OWNERS_FIXED = ("common", "discard", "review", "none")
DECISIONS = ("계승", "대체", "개선")
STATUSES = ("pending", "ported", "verified", "not_migrated")
DUP_SIMILARITY_FAIL = 0.6    # 본문 유사도(3-gram Jaccard) 이 이상이면 복제로 본다
DUP_MIN_TOKENS = 12          # 이보다 짧은 본문(단순 위임·getter)은 유사도 판정에서 뺀다


def now():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def contract_path():
    return os.path.join(workspace(), "contracts", "common-contract.yaml")


def usage_path():
    return os.path.join(workspace(), "knowledge", "COMMON_USAGE.yaml")


def not_migrated_path(contract_file):
    return os.path.splitext(contract_file)[0] + "-not-migrated.yaml"


def as_list(v):
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def tobe_values(it):
    """tobe 는 문자열 하나 또는 모듈별 복사본이면 {모듈: TO-BE} 이다."""
    t = it.get("tobe")
    if isinstance(t, dict):
        return [str(v).strip() for v in t.values() if str(v or "").strip()]
    return [str(t).strip()] if str(t or "").strip() else []


# decision=대체 인데 TO-BE 아키텍처에서 기능 자체가 필요 없는 경우(예: 서버 렌더링 화면 전환·팝업 리다이렉트를
# REST 로 바꿔 대응 메서드가 없다)의 표기. 사유가 있어야 하고 대체에만 쓴다 — 실측: 대응이 없는 대체 35건을
# 표현할 방법이 없어 이행 검사가 FAIL 하거나, 폐기(discard)로 바꾸면 '사용처 있는데 폐기' 로 거부됐다.
NOT_NEEDED_PREFIX = "불필요:"


def is_not_needed(value):
    v = str(value or "").strip()
    return v.startswith(NOT_NEEDED_PREFIX) and len(v) > len(NOT_NEEDED_PREFIX) + 1


def load_contract(path=None):
    p = path or contract_path()
    if not os.path.exists(p):
        return None
    return load_yaml(p)


# ---------------------------------------------------------------- 초안

def suggest_method(m, dynamic_calls, class_used=False):
    """(owner, decision, note) 제안. owner=none 은 미사용 일괄 규칙(개별 review 아님)."""
    n = len(m["used_by"])
    if n >= 2:
        return "common", "계승", f"{n}개 업무 공유"
    if n == 1:
        only = next(iter(m["used_by"]))
        return "common", "계승", (f"단일 업무({only}) 사용 — 공통 유지가 기본(업무별 분해 방지). "
                                  f"업무로 내리려면 사람이 owner: slice:{only} 로 결정")
    entry = m.get("entry")
    # 접근자는 그 클래스를 어느 slice 가 쓸 때만 진입점으로 본다 (아무도 쓰지 않는 VO 의 접근자는 미사용)
    if entry and (entry != "accessor" or class_used):
        return "common", "계승", f"프레임워크 진입점({entry}) — 정적 호출 없음"
    return "none", "", unused_note(m, dynamic_calls, "동적 호출")


def unused_note(row, dynamic_calls, what):
    note = "어느 slice 도 도달하지 않음 — 이관 안 함(일괄)"
    ex = sorted(row.get("excluded_use") or {})
    if ex:
        note += f". 범위 제외 코드({', '.join(ex)})만 사용"
    if dynamic_calls:
        note += f". 프로젝트에 {what} {dynamic_calls}건 — 문자열·리플렉션 호출 대상이면 목록 파일에서 owner 를 바꾼다"
    return note


def suggest_statement(st, dynamic_calls):
    users = sorted(st["used_by"])
    ns_owner = st.get("namespace_owner")
    if not users:
        if ns_owner:
            return "review", "", (f"업무({ns_owner}) 소유 namespace 의 미사용 statement — 업무 변환에 넣을지 결정한다 "
                                  f"(slice:{ns_owner}·discard·none)")
        return "none", "", unused_note(st, dynamic_calls, "동적 SQL id")
    if len(users) >= 2:
        return "common", "계승", f"{len(users)}개 업무 공유 — 공유 Mapper 로 한 번만 변환"
    only = users[0]
    if ns_owner == only:
        return f"slice:{only}", "계승", "소유 업무만 사용"
    if ns_owner and ns_owner != only:
        return "common", "계승", (f"업무 간 교차: {ns_owner} 소유 namespace 를 {only} 가 사용 — "
                                  f"공유 Mapper 로 승격(기본) 또는 {ns_owner} 서비스 경유로 사람 결정")
    return "common", "계승", f"공통 namespace — 단일 업무({only}) 사용이어도 공통 유지가 기본"


def old_rule_review(usage):
    """미사용 일괄 규칙이 없던 종전 규칙이었다면 review 였을 건수 (전후 비교용).

    범위 제외 클래스의 메서드는 행렬에 목록이 없어 넣지 않는다 — 실제 종전 건수는 이보다 크다.
    """
    n = 0
    for c in usage.get("common_classes") or []:
        for m in c["methods"]:
            if not m["id"].startswith("<init>") and not m["used_by"] and not m.get("entry"):
                n += 1
    for st in (usage.get("statements") or []) + (usage.get("fragments") or []):
        if not st["used_by"]:
            n += 1
    return n


def module_suggestion(owner, used_modules, all_modules, common_module, slice_modules):
    """(module, copy) 제안. 행렬에 modules 가 없으면 (None, None) — 종전 동작."""
    if not all_modules:
        return None, None
    if owner == "common":
        if len(used_modules) == 1:
            return used_modules[0], False
        if len(used_modules) >= 2:
            return sorted(used_modules), True
        # 사용 모듈을 모르는 항목(프레임워크 진입점): 전 모듈 공통이 정해져 있으면 그곳, 아니면 모듈별 복사
        if common_module:
            return common_module, False
        return sorted(all_modules), True
    if str(owner).startswith("slice:"):
        return (slice_modules.get(owner.split(":", 1)[1]) or ""), False
    return "", False


def build_items(usage, common_module=None):
    """(계약 항목, 이관 안 함 항목, 범위 제외 집계)."""
    dyn = len(usage.get("unresolved") or [])
    all_modules = usage.get("modules") or []
    slice_modules = usage.get("slice_modules") or {}
    items, none_items = [], []
    excluded = {}

    def add(it, used_modules):
        if it["owner"] == "none":
            it["status"] = "not_migrated"
            none_items.append(it)
            return
        mod, copy = module_suggestion(it["owner"], used_modules, all_modules, common_module, slice_modules)
        if mod is not None:
            it["modules"] = list(used_modules)
            it["module"] = mod
            it["suggested_module"] = mod
            if copy:
                it["copy"] = True
                it["note"] += (f". 여러 모듈 사용 — 모듈별 복사본(copy)이 기본. 전 모듈 기반(인증·권한 등)이면 "
                               f"module: {common_module or '<project.common_module>'} 로 바꾸고 copy 를 지운다")
        items.append(it)

    for c in usage.get("common_classes") or []:
        cls = c["class"]
        for m in c["methods"]:
            if m["id"].startswith("<init>"):
                continue
            owner, decision, note = suggest_method(m, dyn, bool(c.get("used_by")))
            used_mods = m.get("modules") or []
            if not m["used_by"] and m.get("entry"):
                used_mods = c.get("modules") or []
            add({"kind": "method", "asis": f"{cls}#{m['id']}", "file": c["file"], "line": m["line"],
                 "signature": m["signature"], "used_by": sorted(m["used_by"]), "usage": m["used_by"],
                 "suggestion": owner, "owner": owner, "decision": decision, "note": note}, used_mods)
    for u in usage.get("slice_unused_methods") or []:
        add({"kind": "method", "asis": f"{u['class']}#{u['method']}", "file": u["file"], "line": u["line"],
             "signature": u["signature"], "used_by": [], "usage": {}, "suggestion": "review", "owner": "review",
             "decision": "",
             "note": (f"업무({u['slice']}) 소유 클래스의 미사용 public 메서드 — 업무 변환에 넣을지 결정한다 "
                      f"(slice:{u['slice']}·discard·none)")}, [])
    for kind, rows in (("statement", usage.get("statements") or []), ("fragment", usage.get("fragments") or [])):
        for st in rows:
            if st.get("scope"):
                key = f"{kind}_{st['scope']}"
                excluded[key] = excluded.get(key, 0) + 1
                continue
            owner, decision, note = suggest_statement(st, dyn)
            add({"kind": kind, "asis": st["id"], "file": st["file"], "line": st["line"],
                 "used_by": sorted(st["used_by"]), "usage": st["used_by"],
                 "suggestion": owner, "owner": owner, "decision": decision, "note": note}, st.get("modules") or [])
    for c in usage.get("excluded_classes") or []:
        key = f"class_{c['scope']}"
        excluded[key] = excluded.get(key, 0) + 1
    disambiguate_overloads(items + none_items)
    return items, none_items, excluded


def param_types(signature):
    """시그니처 문자열의 인자 타입 목록. 'Map getMap(String a, Map<String, Object> b)' → ['String', 'Map<String,Object>']."""
    s = str(signature or "")
    if "(" not in s:
        return []
    inner = s[s.index("(") + 1:s.rindex(")")] if ")" in s else s[s.index("(") + 1:]
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    out = []
    for p in parts:
        toks = [t for t in re.sub(r"@\w+(\([^)]*\))?", "", p).replace("final ", " ").split() if t]
        typ = "".join(toks[:-1]) if len(toks) > 1 else "".join(toks)
        out.append(re.sub(r"\s+", "", typ))
    return out


def disambiguate_overloads(items):
    """같은 이름·같은 인자 수 오버로드는 `Class#name/N` 이 겹친다 — init 마다 id 가 흔들려 사람 결정이 엉뚱한 항목에 붙는다.
    겹치는 항목만 `Class#name(타입,타입)` 으로 바꾼다(겹치지 않는 항목의 asis 는 그대로라 기존 계약과 계속 맞는다).
    타입까지 같으면(같은 FQN 이 두 파일에 있는 경우) 파일 경로를 덧붙인다."""
    groups = {}
    for it in items:
        if it.get("kind") == "method":
            groups.setdefault(it["asis"], []).append(it)
    for asis, grp in groups.items():
        if len(grp) < 2:
            continue
        cls, _, rest = asis.partition("#")
        name = rest.split("/", 1)[0]
        seen = {}
        for it in grp:
            it["asis"] = f"{cls}#{name}({','.join(param_types(it.get('signature')))})"
            seen.setdefault(it["asis"], []).append(it)
        for same in seen.values():
            if len(same) > 1:
                for it in same:
                    it["asis"] = f"{it['asis']}@{it.get('file', '')}"


HUMAN_KEYS = ("owner", "decision", "tobe", "tobe_signature", "status", "note", "decided_by")
AUTO_KEYS = ("owner", "decision", "status", "note")


def human_decided(prev):
    """사람이 제안과 다르게 정했거나 decided_by 를 남긴 항목."""
    return prev.get("owner") != prev.get("suggestion") or bool(prev.get("decided_by"))


def merge_prev(it, prev):
    """새 초안 항목 it 에 이전 항목 prev 의 사람 결정을 얹는다. 반환: 사람 결정 없이 제안이 바뀌어 새 제안을 반영했는가."""
    auto = not human_decided(prev) and prev.get("suggestion") != it["suggestion"]
    for k in HUMAN_KEYS:
        if k in prev and not (auto and k in AUTO_KEYS):
            it[k] = prev[k]
    if auto:
        it["note"] = (it.get("note") or "") + (f" [행렬 변경: 제안 {prev.get('suggestion')}→{it['suggestion']}, "
                                               f"사람 결정이 없어 새 제안 반영]")
        if it.get("status") != "not_migrated":
            it["status"] = prev.get("status") if prev.get("status") in ("ported", "verified") else "pending"
    elif prev.get("suggestion") != it["suggestion"] and prev.get("owner") != prev.get("suggestion"):
        it["note"] = (it.get("note") or "") + f" [행렬 변경: 제안 {prev.get('suggestion')}→{it['suggestion']}]"
    # 모듈: 사람이 제안과 다르게 바꿨으면(예: module: common) 보존, 아니면 새 제안
    if "suggested_module" in prev and prev.get("module") != prev.get("suggested_module"):
        it["module"] = prev.get("module")
        if prev.get("copy"):
            it["copy"] = True
        else:
            it.pop("copy", None)
    it["id"] = prev["id"]
    return auto


def cmd_init(args):
    usage_file = args.usage or usage_path()
    if not os.path.exists(usage_file):
        sys.exit(f"[contract] 사용 행렬이 없다: {usage_file} (python tools/common_usage.py 먼저)")
    usage = load_yaml(usage_file)
    out = args.out or contract_path()
    nm_path = not_migrated_path(out)
    common_module = args.common_module or (config().get("project") or {}).get("common_module") or None
    with file_lock(out):
        old = load_contract(out) or {}
        old_items = {i["asis"]: i for i in old.get("items") or [] if isinstance(i, dict)}
        old_nm = load_yaml(nm_path) if os.path.exists(nm_path) else {}
        rescued = {e["asis"]: e for e in old_nm.get("items") or []
                   if isinstance(e, dict) and e.get("asis") and str(e.get("owner") or "none") != "none"}
        next_no = max([int(i["id"][3:]) for i in old_items.values() if str(i.get("id", "")).startswith("CC-")] or [0]) + 1
        cand, none_cand, excluded = build_items(usage, common_module)
        items, nm_rows = [], []
        cnt = {"added": 0, "kept": 0, "auto": 0, "moved": 0, "promoted": 0}

        def new_id(it):
            nonlocal next_no
            it["id"] = f"CC-{next_no:04d}"
            next_no += 1
            it.setdefault("tobe", "")
            it.setdefault("tobe_signature", "")
            it.setdefault("status", "pending")

        for it in cand:
            prev = old_items.pop(it["asis"], None)
            if prev:
                cnt["auto"] += 1 if merge_prev(it, prev) else 0
                cnt["kept"] += 1
            else:
                new_id(it)
                cnt["added"] += 1
            items.append(it)
        for it in none_cand:
            prev = old_items.pop(it["asis"], None)
            if prev and human_decided(prev):
                # 사람이 정한 항목은 사용처가 사라져도 계약에 남긴다
                merge_prev(it, prev)
                it["note"] = (it.get("note") or "") + " [행렬: 도달 slice 없음 — 이관 안 함 제안]"
                items.append(it)
                cnt["kept"] += 1
            elif it["asis"] in rescued:
                r = rescued[it["asis"]]
                it.update({"owner": r["owner"], "decision": r.get("decision") or "", "decided_by": r.get("decided_by") or "",
                           "status": "pending"})
                it["note"] = (it.get("note") or "") + " [이관 안 함 목록에서 사람 결정으로 올림]"
                new_id(it)
                items.append(it)
                cnt["promoted"] += 1
            else:
                cnt["moved"] += 1 if prev else 0
                nm_rows.append({"asis": it["asis"], "kind": it["kind"], "file": it["file"], "line": it["line"],
                                "owner": "none", "status": "not_migrated", "note": it["note"]})
        stale = []
        for prev in old_items.values():
            prev["stale"] = True
            prev["note"] = (prev.get("note") or "") + " [행렬에서 사라짐 — AS-IS 변경 확인]"
            stale.append(prev)
        # 사람이 읽기 쉽게 id 를 맨 앞에 둔다
        items = [dict([("id", i["id"])] + [(k, v) for k, v in i.items() if k != "id"])
                 for i in sorted(items + stale, key=lambda i: i["id"])]
        tobe_cfg = old.get("tobe") or {
            "common_module": "backend/common",
            "common_package": ((config().get("project") or {}).get("base_package") or "com.example") + ".common",
            "shared_mapper_dir": "backend/common/src/main/resources/mapper/common",
        }
        changed = bool(cnt["added"] or stale or cnt["auto"] or cnt["moved"] or cnt["promoted"])
        by_kind = {}
        for r in nm_rows:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
        review_now = sum(1 for i in items if i.get("owner") == "review" and not i.get("stale"))
        review_old = old_rule_review(usage)
        data = {
            "schema": 1,
            "approved": bool(old.get("approved")) and not changed,
            "approved_by": old.get("approved_by", "") if not changed else "",
            "approved_at": old.get("approved_at", "") if not changed else "",
            "generated_at": now(),
            "source": safe_relpath(usage_file, ROOT),
            "tobe": tobe_cfg,
        }
        if usage.get("modules"):
            data["modules"] = list(usage["modules"])
            data["common_module"] = common_module or ""
        data["summary"] = {
            "items": len(items), "review": review_now, "review_old_rule": review_old,
            "not_migrated": len(nm_rows), "not_migrated_by_kind": dict(sorted(by_kind.items())),
            "not_migrated_list": os.path.basename(nm_path),
            "excluded": dict(sorted(excluded.items())),
        }
        data["items"] = items
        dump_yaml(out, data)
        dump_yaml(nm_path, {
            "schema": 1, "generated_at": now(), "source": safe_relpath(usage_file, ROOT),
            "rule": ("어느 slice 도 도달하지 않는 공통 메서드·공통 namespace statement — 이관 안 함(owner: none). "
                     "살려야 하는 항목은 owner 를 common·discard·slice:<id> 로 바꾸고 decided_by 를 적은 뒤 init 을 다시 돌린다"),
            "count": len(nm_rows), "by_kind": dict(sorted(by_kind.items())), "items": nm_rows})
    print(f"공통 계약: 항목 {len(items)} (신규 {cnt['added']} · 유지 {cnt['kept']} · 사라짐 {len(stale)}"
          f" · 제안 자동 반영 {cnt['auto']} · 목록에서 올림 {cnt['promoted']}) → {out}")
    print(f"사람 판단(review): {review_now}건 (미사용 일괄 규칙 전 기준 {review_old}건)")
    print(f"이관 안 함(owner: none) 일괄: {len(nm_rows)}건 {dict(sorted(by_kind.items()))} → {nm_path}")
    if excluded:
        print(f"범위 제외(공통 아님): {dict(sorted(excluded.items()))}")
    if changed and old.get("approved"):
        print("항목이 바뀌어 승인이 해제됐다. 검토 후 다시 승인한다.")
    return 0


# ---------------------------------------------------------------- 검증

def validate(data):
    errs = []
    if not data:
        return ["계약 파일이 없다"]
    seen = set()
    for it in data.get("items") or []:
        iid = it.get("id", "?")
        if it.get("asis") in seen:
            errs.append(f"{iid}: asis 중복 {it.get('asis')}")
        seen.add(it.get("asis"))
        owner = str(it.get("owner", ""))
        if owner not in OWNERS_FIXED and not owner.startswith("slice:"):
            errs.append(f"{iid}: owner 값이 잘못됐다 ({owner})")
        if owner == "review" and not it.get("stale"):
            errs.append(f"{iid}: 사람 판단 대기(review) — common·slice:<id>·discard 중 하나로 결정한다 ({it.get('asis')})")
        if owner == "common" and it.get("decision") not in DECISIONS:
            errs.append(f"{iid}: owner=common 이면 decision(계승·대체·개선)이 필요하다")
        if owner.startswith("slice:"):
            sl = owner.split(":", 1)[1]
            if it.get("used_by") and set(it["used_by"]) - {sl}:
                errs.append(f"{iid}: {sl} 로 내렸지만 다른 업무도 쓴다 ({', '.join(it['used_by'])}) — 공통이어야 한다")
            if it.get("suggestion") == "common" and not it.get("decided_by"):
                errs.append(f"{iid}: 공통 제안을 업무로 내렸다 — decided_by(사람)를 적는다")
        if owner == "discard" and it.get("used_by"):
            errs.append(f"{iid}: 사용처가 있는데 폐기로 결정했다 ({', '.join(it['used_by'])})")
        if owner == "none":
            if it.get("used_by"):
                errs.append(f"{iid}: 사용처가 있는데 이관 안 함(none)으로 두었다 ({', '.join(it['used_by'])})")
            if it.get("status") != "not_migrated":
                errs.append(f"{iid}: owner=none 이면 status 는 not_migrated")
        elif it.get("status") == "not_migrated":
            errs.append(f"{iid}: status=not_migrated 는 owner=none 에만 쓴다")
        if it.get("status") not in STATUSES:
            errs.append(f"{iid}: status 는 {'|'.join(STATUSES)}")
        for v in tobe_values(it):
            if str(v).startswith(NOT_NEEDED_PREFIX) and (it.get("decision") != "대체" or not is_not_needed(v)):
                errs.append(f"{iid}: '{NOT_NEEDED_PREFIX} <사유>' 는 decision=대체 에만, 사유와 함께 쓴다")
        if it.get("status") in ("ported", "verified") and owner == "common" and not tobe_values(it):
            errs.append(f"{iid}: 이관 완료(status={it.get('status')})인데 tobe 대응이 비었다")
        if it.get("stale") and owner == "common" and it.get("status") == "pending":
            errs.append(f"{iid}: 행렬에서 사라진 항목 — 삭제 또는 근거를 note 에 적는다")
        if owner == "common" and data.get("modules") and not it.get("stale"):
            errs.extend(validate_module(it, data))
    return errs


def validate_module(it, data):
    """모듈 차원(project.modules): 한 모듈 공통 · 여러 모듈 복사(copy) · 전 모듈 공통(common_module) 중 하나여야 한다."""
    iid = it.get("id", "?")
    mods = [str(m) for m in data.get("modules") or []]
    cm = str(data.get("common_module") or "")
    used = {str(m) for m in it.get("modules") or []}
    mod = it.get("module")
    errs = []
    if isinstance(mod, list):
        bad = [m for m in mod if str(m) not in mods]
        if bad:
            errs.append(f"{iid}: module 에 없는 모듈 {', '.join(map(str, bad))} (project.modules: {', '.join(mods)})")
        if not it.get("copy"):
            errs.append(f"{iid}: module 이 여러 개면 copy: true(모듈별 복사본)여야 한다 — 하나로 올리려면 module: {cm or '<common_module>'}")
        missing = used - {str(m) for m in mod}
        if missing:
            errs.append(f"{iid}: 쓰는 모듈 {', '.join(sorted(missing))} 에 복사본이 없다 — module 목록에 넣는다")
    elif mod in (None, ""):
        errs.append(f"{iid}: owner=common 인데 module 이 비었다 ({'|'.join(mods + ([cm] if cm else []))})")
    else:
        mod = str(mod)
        if it.get("copy"):
            errs.append(f"{iid}: copy: true 인데 module 이 하나({mod})다 — 여러 모듈 목록으로 두거나 copy 를 지운다")
        if mod != cm and mod not in mods:
            errs.append(f"{iid}: module {mod} 가 project.modules·common_module 에 없다")
        elif mod != cm and used - {mod}:
            errs.append(f"{iid}: module {mod} 공통인데 다른 모듈({', '.join(sorted(used - {mod}))})도 쓴다 — "
                        f"module 을 여러 모듈 목록 + copy: true 로 두거나 {cm or '<common_module>'} 로 올린다")
    return errs


def cmd_validate(args):
    data = load_contract(args.contract)
    errs = validate(data)
    for e in errs:
        print("- " + e)
    print(f"검사 완료: 문제 {len(errs)}건")
    return 1 if errs else 0


def cmd_status(args):
    data = load_contract(args.contract)
    if not data:
        sys.exit("[contract] 계약 파일이 없다")
    cnt = {}
    for it in data.get("items") or []:
        owner = str(it.get("owner"))
        key = (it.get("kind"), "slice" if owner.startswith("slice:") else owner, it.get("status"))
        cnt[key] = cnt.get(key, 0) + 1
    print(f"승인: {'예 (' + str(data.get('approved_by')) + ')' if data.get('approved') else '아니오'}")
    print(f"{'종류':<10} {'owner':<8} {'status':<9} 건수")
    for (k, o, s), n in sorted(cnt.items(), key=lambda x: tuple(str(v) for v in x[0])):
        print(f"{str(k):<10} {str(o):<8} {str(s):<9} {n}")
    sm = data.get("summary") or {}
    if sm:
        print(f"이관 안 함(owner: none, 목록 파일 {sm.get('not_migrated_list')}): {sm.get('not_migrated', 0)}건"
              f" · 사람 판단(review) {sm.get('review', 0)}건 (일괄 규칙 전 기준 {sm.get('review_old_rule', 0)}건)"
              f" · 범위 제외 {sm.get('excluded') or {}}")
    return 0


def cmd_approve(args):
    path = args.contract or contract_path()
    with file_lock(path):
        data = load_contract(path)
        errs = validate(data)
        if errs:
            for e in errs:
                print("- " + e)
            sys.exit(f"[contract] 문제 {len(errs)}건 — 승인할 수 없다")
        data["approved"] = True
        data["approved_by"] = args.by
        data["approved_at"] = now()
        dump_yaml(path, data)
    print(f"공통 계약 승인: {args.by} ({data['approved_at']})")
    return 0


def cmd_request(args):
    d = os.path.join(workspace(), "common-requests")
    rid, path = create_numbered_file(d, "CR")
    data = {"id": rid, "slice": args.slice, "asis": args.asis or "", "need": args.need or "",
            "reason": args.reason, "requested_at": now(), "status": "open", "contract_item": "", "resolution": ""}
    dump_yaml(path, data)
    print(rid)
    print(path)
    return 0


# ---------------------------------------------------------------- 복제·소유 침범 검사

TOKEN_RE = re.compile(r"[A-Za-z_$][\w$]*|\d+|==|!=|<=|>=|&&|\|\||[^\s\w]")
JAVA_KW = set("""abstract assert boolean break byte case catch char class const continue default do double else enum
extends final finally float for goto if implements import instanceof int interface long native new package private
protected public return short static strictfp super switch synchronized this throw throws transient try void volatile
while null true false var""".split())


def norm_tokens(body):
    """식별자 이름 차이(변수명 변경)에 둔감한 토큰열: 지역 이름은 v, 호출·타입·키워드·연산자는 유지."""
    toks = TOKEN_RE.findall(body)
    out = []
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if t in JAVA_KW or not re.match(r"[A-Za-z_$]", t):
            out.append(t)
        elif nxt == "(" or t[:1].isupper():
            out.append(t)          # 메서드 호출·타입 이름은 의미가 있다
        else:
            out.append("v")
    return out


def shingles(toks, n=3):
    return {tuple(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def similarity(a, b):
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def method_bodies(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    out = []
    for c in js.parse_file(path, text):
        for m in c.methods:
            if m.body_start is None:
                continue
            body = c.masked[m.body_start + 1:m.body_end]
            out.append((c, m, norm_tokens(body)))
    return out


def asis_common_bodies(data, asis_src):
    """owner=common 인 메서드 항목의 AS-IS 본문 토큰."""
    by_file = {}
    for it in data.get("items") or []:
        if it.get("kind") == "method" and it.get("owner") == "common" and not it.get("stale"):
            by_file.setdefault(it["file"], []).append(it)
    out = []
    for f, items in by_file.items():
        bodies = {(c.fqn, m.key): toks for c, m, toks in method_bodies(os.path.join(asis_src, f))}
        for it in items:
            cls, key = it["asis"].split("#", 1)
            toks = bodies.get((cls, key))
            if toks is not None:
                out.append((it, toks))
    return out


SQL_STMT_RE = re.compile(r"<(select|insert|update|delete)\b[^>]*\bid\s*=\s*\"([^\"]+)\"[^>]*>(.*?)</\1>", re.S)


def sql_tokens(sql):
    sql = re.sub(r"<!--.*?-->", " ", sql, flags=re.S)
    sql = re.sub(r"[#$]\{[^}]*\}", "?", sql)
    sql = re.sub(r"<[^>]+>", " ", sql)
    return re.findall(r"[A-Za-z_]\w*|\d+|\S", sql.upper())


def xml_statements(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    return [(m.group(2), sql_tokens(m.group(3)), text.count("\n", 0, m.start()) + 1) for m in SQL_STMT_RE.finditer(text)]


def under(path, roots):
    fr = path.replace(os.sep, "/").strip("/")
    for r in roots:
        r = str(r or "").replace(os.sep, "/").strip("/")
        if r and (fr == r or fr.startswith(r + "/")):
            return r
    return None


def module_copy_elsewhere(item_toks, td, module_dirs, exclude):
    """같은 모듈 경로 안(exclude 밖)에 이미 같은 공통의 복사본이 있으면 그 위치."""
    for d in module_dirs:
        root = os.path.join(td, str(d))
        if not os.path.isdir(root):
            continue
        for dp, dns, fns in os.walk(root):
            dns[:] = sorted(x for x in dns if x not in (".git", "node_modules", "build", "target", "dist", "test"))
            for fn in sorted(fns):
                if not fn.endswith(".java"):
                    continue
                full = os.path.join(dp, fn)
                relp = os.path.relpath(full, td).replace(os.sep, "/")
                if relp in exclude or "/src/test/" in "/" + relp:
                    continue
                for c, m, toks in method_bodies(full):
                    if len(toks) >= DUP_MIN_TOKENS and similarity(toks, item_toks) >= DUP_SIMILARITY_FAIL:
                        return f"{relp}:{js.line_of(c.text, m.start)} {c.name}.{m.name}()"
    return None


def copy_in_other_changed(item_toks, td, files, current):
    """이번 변경 파일 중 다른 파일에 같은 공통의 복사본이 있으면 그 위치 (모듈 경로 매핑이 없을 때의 대조 범위)."""
    for g in files:
        if g == current or not g.endswith(".java"):
            continue
        for c, m, toks in method_bodies(os.path.join(td, g)):
            if len(toks) >= DUP_MIN_TOKENS and similarity(toks, item_toks) >= DUP_SIMILARITY_FAIL:
                return f"{g}:{js.line_of(c.text, m.start)} {c.name}.{m.name}()"
    return None


def integrity_findings(slice_id, files, td, data, asis_src, module=None, module_paths=None):
    """slice 변경 파일의 공통 복제·소유 침범. [(severity, where, message, action)] (severity: FAIL|WARN).

    module      : slice 의 소유 모듈 (slices.yaml module). 있으면 계약에서 copy: true 로 승인된 공통의
                  그 모듈 복사본은 복제로 보지 않는다 — 단, 같은 모듈 안에 복사본이 이미 있으면(업무 slice 간 복제) 차단한다.
    module_paths: config project.module_paths ({모듈: [경로...]}). 같은 모듈 안의 기존 복사본을 찾는 범위다.
                  없으면 이번 변경 파일끼리만 대조한다.
    """
    out = []
    tobe = data.get("tobe") or {}
    mod = str(tobe.get("common_module") or "").strip("/")
    pkg_path = str(tobe.get("common_package") or "").replace(".", "/")
    module_common = tobe.get("module_common") if isinstance(tobe.get("module_common"), dict) else {}
    privileged = slice_id in ("common-port", "scaffold", None, "") or str(slice_id).startswith("common")
    for f in files:
        fr = f.replace(os.sep, "/")
        # DB 마이그레이션 폴더는 공통 모듈 안에 있어도 공통 코드가 아니다 — 모든 slice 가 자기 DDL 을 새 파일로 더하는
        # 공유 자리다(실측: brownfield 에서 migration 이 server/common 아래라 DDL 이 있는 slice 가 전부 FAIL).
        # 이미 적용된 마이그레이션을 고치지 않는 규칙은 target 지침·리뷰가 지킨다.
        if "/db/migration/" in "/" + fr:
            continue
        inside = ((mod and (fr == mod or fr.startswith(mod + "/"))) or (pkg_path and f"/{pkg_path}/" in "/" + fr)
                  or under(fr, [p for v in module_common.values() for p in as_list(v)]))
        if inside and not privileged:
            out.append(("FAIL", f, "공통 영역을 업무 slice 가 수정했다 — 공통은 common-porter 만 수정한다",
                        "되돌리고 python tools/common_contract.py request 로 공통 요청(CR)을 남긴다"))
    if privileged:
        return out
    # 1) 메서드 복제: 계약상 공통 메서드와 본문이 비슷한 메서드를 slice 가 새로 만들었는가
    commons = asis_common_bodies(data, asis_src) if asis_src and os.path.isdir(asis_src) else []
    for f in files:
        if not f.endswith(".java"):
            continue
        for c, m, toks in method_bodies(os.path.join(td, f)):
            if len(toks) < DUP_MIN_TOKENS:
                continue
            best, best_it = 0.0, None
            for it, ctoks in commons:
                if len(ctoks) < DUP_MIN_TOKENS:
                    continue
                s = similarity(toks, ctoks)
                if s > best:
                    best, best_it = s, it
            if (best_it and best >= DUP_SIMILARITY_FAIL and module and best_it.get("copy")
                    and str(module) in [str(x) for x in as_list(best_it.get("module"))]):
                # 계약이 승인한 모듈별 복사본 — 그 모듈 안에 복사본이 이미 있으면 같은 모듈 안 복제다
                ctoks = next(t for i, t in commons if i is best_it)
                mdirs = as_list((module_paths or {}).get(module))
                other = (module_copy_elsewhere(ctoks, td, mdirs, {f.replace(os.sep, "/")}) if mdirs
                         else copy_in_other_changed(ctoks, td, files, f))
                if other:
                    out.append(("FAIL", f"{f}:{js.line_of(c.text, m.start)}",
                                f"{c.name}.{m.name}() 가 공통 계약 {best_it['id']}({best_it['asis']}) 의 {module} 모듈 복사본인데 "
                                f"같은 모듈 안에 이미 복사본이 있다: {other} — 같은 모듈 안 복제",
                                "같은 모듈의 기존 복사본을 호출한다"))
                continue
            if best_it and best >= DUP_SIMILARITY_FAIL:
                out.append(("FAIL", f"{f}:{js.line_of(c.text, m.start)}",
                            f"{c.name}.{m.name}() 가 공통 계약 {best_it['id']}({best_it['asis']}) 와 본문 유사도 {best:.2f} — 공통 복제",
                            f"공통 {best_it.get('tobe') or '(TO-BE 대응)'} 를 호출한다. 계약에 없거나 동작이 달라야 하면 공통 요청(CR)"))
            elif best_it:
                cls_name, key = best_it["asis"].split("#", 1)
                if key.split("/")[0] == m.name and best >= 0.3:
                    out.append(("WARN", f"{f}:{js.line_of(c.text, m.start)}",
                                f"{c.name}.{m.name}() 가 공통 {best_it['asis']} 와 이름이 같고 유사도 {best:.2f}",
                                "의도한 업무 전용 구현인지 레포트에 근거를 적는다"))
    # 2) Mapper statement 복제: slice XML statement 가 공통(공유) Mapper statement 와 같은가
    shared_dir = str(tobe.get("shared_mapper_dir") or "").strip("/")
    common_stmts = []
    if shared_dir and os.path.isdir(os.path.join(td, shared_dir)):
        for dp, _dns, fns in os.walk(os.path.join(td, shared_dir)):
            for fn in fns:
                if fn.endswith(".xml"):
                    for sid, toks, _ln in xml_statements(os.path.join(dp, fn)):
                        common_stmts.append((f"{fn}:{sid}", toks))
    for f in files:
        if not f.endswith(".xml"):
            continue
        for sid, toks, ln in xml_statements(os.path.join(td, f)):
            for cid, ctoks in common_stmts:
                s = similarity(toks, ctoks)
                if s >= 0.8:
                    out.append(("FAIL", f"{f}:{ln}", f"statement {sid} 가 공유 Mapper {cid} 와 유사도 {s:.2f} — SQL 복제",
                                "공유 Mapper 를 호출한다 (다르게 필요하면 공통 요청 CR)"))
                    break
    return out


def fulfillment_findings(td, data):
    """common-port 완료 시: owner=common 항목이 TO-BE 에 실제로 있는가."""
    out = []
    java_names, stmt_ids = set(), set()
    for dp, dns, fns in os.walk(td):
        dns[:] = [d for d in dns if d not in (".git", "node_modules", "build", "target", "dist")]
        for fn in fns:
            p = os.path.join(dp, fn)
            if fn.endswith(".java") and "/src/main/" in p.replace(os.sep, "/"):
                try:
                    text = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                for c in js.parse_file(p, text):
                    for m in c.methods:
                        java_names.add(f"{c.fqn}#{m.name}")
            elif fn.endswith(".xml"):
                try:
                    text = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                ns = re.search(r"<mapper\b[^>]*\bnamespace\s*=\s*\"([^\"]+)\"", text)
                if ns:
                    for m in re.finditer(r"<(?:select|insert|update|delete|sql)\b[^>]*\bid\s*=\s*\"([^\"]+)\"", text):
                        stmt_ids.add(f"{ns.group(1)}.{m.group(1)}")
    for it in data.get("items") or []:
        if it.get("owner") != "common" or it.get("stale"):
            continue
        values = tobe_values(it)
        if not values:
            out.append(("FAIL", it["id"], f"공통 항목 {it['asis']} 의 TO-BE 대응(tobe)이 비었다", "이관 후 tobe 를 기입한다"))
            continue
        if isinstance(it.get("tobe"), dict):
            # 모듈별 tobe 는 복사본(copy)뿐 아니라 모듈마다 대응이 다른 대체 항목에도 쓴다 — 쓰는 모듈의 몫이 비면 미이행
            # (실측: copy 가 아닌 대체 항목의 빈 user 몫 8건이 검사를 통과했다)
            want = as_list(it.get("module")) if it.get("copy") else (it.get("modules") or list((it["tobe"] or {}).keys()))
            lacking = [str(m) for m in want if not str((it["tobe"] or {}).get(m) or "").strip()]
            if lacking:
                out.append(("FAIL", it["id"], f"모듈별 복사본 {it['asis']} 의 {', '.join(lacking)} 모듈 tobe 가 비었다",
                            "각 모듈에 복사본을 만들고 tobe 에 모듈별로 적는다"))
        for tobe in values:
            if is_not_needed(tobe) and it.get("decision") == "대체":
                continue
            if it["kind"] == "method":
                name = tobe.split("(")[0]
                if name not in java_names:
                    out.append(("FAIL", it["id"], f"tobe {tobe} 를 target 에서 찾지 못했다 (계약 미이행)", "공통 모듈에 구현한다"))
            elif tobe not in stmt_ids:
                out.append(("FAIL", it["id"], f"tobe statement {tobe} 를 target Mapper 에서 찾지 못했다", "공유 Mapper 에 변환한다"))
    return out


def slice_module(slice_id):
    """(slice 의 module, config project.module_paths). 없으면 None."""
    paths = (config().get("project") or {}).get("module_paths")
    paths = paths if isinstance(paths, dict) else None
    try:
        doc = load_yaml(os.path.join(workspace(), "slices", "slices.yaml"))
    except OSError:
        return None, paths
    for s in doc.get("slices") or []:
        if isinstance(s, dict) and s.get("id") == slice_id:
            return s.get("module"), paths
    return None, paths


def cmd_check(args):
    data = load_contract(args.contract)
    if not data:
        sys.exit("[contract] 계약 파일이 없다")
    td = args.target or target_dir()
    asis = args.asis or (config().get("asis") or {}).get("source_dir")
    if asis and not os.path.isabs(asis):
        asis = os.path.normpath(os.path.join(ROOT, asis))
    module, module_paths = slice_module(args.slice)
    f = (fulfillment_findings(td, data) if args.slice == "common-port"
         else integrity_findings(args.slice, args.files or [], td, data, asis, module, module_paths))
    for sev, where, msg, act in f:
        print(f"- [{sev}] {where}: {msg}\n    → {act}")
    fails = sum(1 for x in f if x[0] == "FAIL")
    print(f"결과: FAIL {fails} · WARN {len(f) - fails}")
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="공통 계약 관리")
    ap.add_argument("--contract", help="계약 파일 (기본: workspace/<project>/contracts/common-contract.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--usage")
    p.add_argument("--out")
    p.add_argument("--common-module", help="전 모듈 공통 모듈 이름 (기본: config project.common_module)")
    p.set_defaults(fn=cmd_init)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("approve")
    p.add_argument("--by", required=True)
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("request")
    p.add_argument("--slice", required=True)
    p.add_argument("--asis", help="AS-IS 공통 항목 (클래스#메서드/인자수 또는 namespace.id)")
    p.add_argument("--need", help="계약에 없는 새 공통 기능이면 필요한 동작")
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_request)
    p = sub.add_parser("check")
    p.add_argument("--slice", required=True)
    p.add_argument("--files", nargs="*")
    p.add_argument("--target")
    p.add_argument("--asis")
    p.set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
