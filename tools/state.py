#!/usr/bin/env python3
"""state.yaml 을 도구로만 고친다 - 완료(done)는 gate.py check 를 통과할 때만 기록한다.

사용:
  python tools/state.py get  --stage 2 --slice <id> [--unit <unit>]
  python tools/state.py set  --stage 2 --slice <id> [--unit <unit>] --value in_progress
  python tools/state.py set  --stage 2 --slice <id> --value done [--report <레포트>]
  python tools/state.py set  --stage 5 --slice <id> --value blocked --reason "<사유>"
  python tools/state.py set  --stage stage3_common --value in_progress      # 단계 전체 값(stages.*)
  python tools/state.py set  --stage 2 --slice common-port --value done      # stages.stage2_common_port
  python tools/state.py show [--slice <id>]

--stage 는 번호 또는 키 이름이다.
  - slice 를 주면: 2 -> stage2_backend, 4 -> stage4_frontend, 5 -> stage5_integration (unit 은 2·4 만)
  - slice 를 주지 않으면: 0·1·3·5·6·7·8·9 -> stages 의 해당 키. 2·4 는 뜻이 둘이라 키 이름
    (stage2_scaffold·stage2_common_port·stage4_scaffold)이나 가짜 slice(scaffold·common-port·scaffold-fe)로 준다.

규칙
- done: 내부에서 `gate.py check --stage N [--slice id] [--unit u]` 를 돌린다. 판정은 기록하려는 새 state 로 한다
  (PA_STATE_FILE - 쓰기 훅 guard.py 와 같은 방식). 통과할 때만 기록하고, FAIL 이면 아무것도 바꾸지 않고 1 로 끝난다.
  state-consistency 훅은 빼지 않는다 - result 가 blocked·failed 인 레포트로 done 을 쓰는 것을 막는다.
- done_elsewhere: state.yaml 의 elsewhere.<키> 사람 선언이 있어야 한다(선언은 사람만 한다).
- blocked: --reason 이 필수이고 slice 의 blocked_reason 에 `[<라벨>] <사유>` 조각으로 쓴다(여럿이면 ' | ' 로 잇는다).
  라벨은 slice 단계면 단계 키(stage5_integration), unit 이면 'unit <id>.<단계 키>'. 같은 라벨 조각만 바꾸므로
  다른 단계·unit 의 사유와 라벨 없는 글(사람이 적은 hold 사유 등)은 남는다.
  blocked 를 다른 값(done·in_progress 등)으로 바꾸면 그 라벨 조각을 지우고, 남는 것이 없으면 null 로 되돌린다.
  사유 안의 ' | ' 는 구분자와 겹치므로 ' / ' 로 바꿔 저장한다(겹친 공백은 먼저 하나로 모은다).
  단계 전체 값(stages.*)에는 blocked_reason 칸이 없으므로 사유는 이력에만 남는다.
- 값 없이 적힌 키(`blocked_reason:` - 템플릿 형식)는 null 로 보고 고친다.
- 고치는 방식: 대상 키 한 줄(과 그 값의 이어지는 줄)만 바꾼다. 주석·키 순서·다른 블록은 그대로다.
  고친 뒤 YAML 을 다시 읽어 "대상 값만 바뀌었는지"(의미)와 "달라진 줄이 변경한 줄뿐이고 나머지 줄은
  바이트 단위로 같은지"(형식)를 대조하고, 하나라도 다르면 쓰지 않는다.
- 동시성: 잠금 없이 읽기 -> 편집 -> 게이트를 돌린 뒤, 잠금 안에서 다시 읽어 원문과 바이트 단위로 같을 때만
  쓰고 이력을 남긴다. 그 사이 바뀌었으면 쓰지 않고 3 으로 끝난다(같은 명령을 다시 실행한다).
  대상 slice·unit·stage 키가 없으면 거부한다(구조 추가는 사람이 Edit 로 한다 - done 전환이 없으면 훅이 막지 않는다).
- 바꿀 때마다 state.yaml 옆의 state-history.jsonl 에 한 줄(시각 KST·키·이전값·새값·사유·게이트)을 덧붙이고,
  최상위 updated_at 이 있으면 같은 시각으로 고친다.

기본 경로는 workspace/<project>/state.yaml 이고 --file 이나 환경 변수 PA_STATE_TOOL_FILE 로 바꾼다.
(gate.py 의 PA_STATE_FILE 은 "판정용 새 state" 라는 다른 뜻이라 state.py 는 따르지 않는다.)

종료 코드: 0 성공 · 1 게이트 FAIL(기록 안 함) · 2 사용법 오류·대상 없음·거부 · 3 판정 중 state.yaml 이 바뀜(다시 실행)

배경(실측): 오케스트레이터가 state.yaml 을 파이썬 정규식으로 직접 고쳤다. 완료 기록이 게이트를 거치는지는
Claude Code 훅만 지키고 있어 하네스 밖에서는 게이트 없이 done 을 쓸 수 있었고, 직접 수정은 블록 경계를 깨뜨릴 위험도 있었다.
"""
import argparse
import copy
import datetime
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, atomic_write_text, file_lock, fix_console_encoding, workspace  # noqa: E402
from _emoji import find_emoji  # noqa: E402

import yaml  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))
KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")

VALUES = ("pending", "in_progress", "done", "blocked", "skipped", "done_elsewhere")

# stages 키 -> (gate 단계 번호, gate --slice). guard.py 의 STAGE_KEYS 와 같다
STAGE_KEYS = {
    "stage0_ingest": (0, None), "stage1_slicing": (1, None), "stage2_scaffold": (2, "scaffold"),
    "stage2_common_port": (2, "common-port"),
    "stage3_common": (3, None), "stage4_scaffold": (4, "scaffold-fe"), "stage5_integration": (5, None),
    "stage6_security": (6, None), "stage7_qa": (7, None), "stage8_deliverables": (8, None),
    "stage9_packaging": (9, None),
}
STAGE_BY_NUM = {0: "stage0_ingest", 1: "stage1_slicing", 3: "stage3_common", 5: "stage5_integration",
                6: "stage6_security", 7: "stage7_qa", 8: "stage8_deliverables", 9: "stage9_packaging"}
# 단계 단위 항목을 가리키는 가짜 slice (gate.py 의 레포트 slice 와 같은 이름)
PSEUDO_SLICES = {"scaffold": "stage2_scaffold", "common-port": "stage2_common_port", "scaffold-fe": "stage4_scaffold"}
SLICE_KEYS = {"stage2_backend": 2, "stage4_frontend": 4, "stage5_integration": 5}
SLICE_BY_NUM = {v: k for k, v in SLICE_KEYS.items()}
UNIT_KEYS = {"stage2_backend": 2, "stage4_frontend": 4}


class StateError(Exception):
    """대상이 없거나 고칠 수 없는 경우. 종료 코드 2."""


def kst_full(now=None):
    return (now or datetime.datetime.now(KST)).strftime("%Y-%m-%d %H:%M")


# 기본 경로를 바꾸는 환경 변수. gate.py 의 PA_STATE_FILE("판정용 새 state")과 뜻이 달라 이름을 나눈다 -
# state.py 가 PA_STATE_FILE 을 따르면 그 변수가 남아 있는 환경에서 엉뚱한 파일에 쓴다.
STATE_PATH_ENV = "PA_STATE_TOOL_FILE"


def default_state_path():
    return os.environ.get(STATE_PATH_ENV) or os.path.join(workspace(), "state.yaml")


def history_path(state_path):
    return os.path.join(os.path.dirname(os.path.abspath(state_path)), "state-history.jsonl")


# ---------------------------------------------------------------- 대상 해석

def resolve(stage, slice_id=None, unit=None):
    """(--stage, --slice, --unit) -> state 안의 경로 튜플."""
    s = str(stage).strip()
    num = int(s) if s.isdigit() else None
    if slice_id in PSEUDO_SLICES:
        key = PSEUDO_SLICES[slice_id]
        if unit:
            raise StateError(f"{slice_id} 에는 unit 이 없다")
        if not (s == key or num == STAGE_KEYS[key][0]):
            raise StateError(f"--slice {slice_id} 는 {key}(단계 {STAGE_KEYS[key][0]})만 가리킨다")
        return ("stages", key)
    if slice_id:
        key = SLICE_BY_NUM.get(num) if num is not None else (s if s in SLICE_KEYS else None)
        if not key:
            raise StateError(f"slice 단계는 {', '.join(f'{v}({k})' for k, v in SLICE_BY_NUM.items())} 중 하나다: {s}")
        if unit:
            if key not in UNIT_KEYS:
                raise StateError(f"unit 에는 {key} 가 없다 (unit 은 stage2_backend·stage4_frontend 만)")
            return ("slices", slice_id, "units", unit, key)
        return ("slices", slice_id, key)
    if unit:
        raise StateError("--unit 은 --slice 와 함께 준다")
    if num is not None:
        if num in (2, 4):
            raise StateError("단계 2·4 의 단계 전체 값은 키 이름(stage2_scaffold·stage2_common_port·stage4_scaffold)"
                             "이나 --slice scaffold·common-port·scaffold-fe 로 준다")
        key = STAGE_BY_NUM.get(num)
    else:
        key = s if s in STAGE_KEYS else None
    if not key:
        raise StateError(f"알 수 없는 단계: {s} (stages 키: {', '.join(STAGE_KEYS)})")
    return ("stages", key)


def dotted(path):
    return ".".join(path)


def gate_args(path):
    """경로 -> (gate 단계 번호, --slice, --unit)."""
    if path[0] == "stages":
        stage, sl = STAGE_KEYS[path[1]]
        return stage, sl, None
    if len(path) == 5:
        return UNIT_KEYS[path[4]], path[1], path[3]
    return SLICE_KEYS[path[2]], path[1], None


def get_in(data, path):
    node = data
    for k in path:
        if not isinstance(node, dict) or k not in node:
            raise StateError(f"state.yaml 에 {dotted(path)} 가 없다 (없는 slice·unit·단계는 고치지 않는다)")
        node = node[k]
    return node


def set_in(data, path, value):
    node = data
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value


# ---------------------------------------------------------------- 줄 단위 편집

KEY_RE = re.compile(r"""^(?P<ind>[ ]*)(?P<key>"[^"]*"|'[^']*'|[^\s#:{}\[\],'"&*!|>%@`-][^:#]*?|-[^\s:#][^:#]*?):(?P<rest>(?:[ \t].*)?)$""")


def split_comment(rest):
    """'값  # 주석' -> ('값', '  # 주석'). 따옴표 안의 # 은 주석이 아니다."""
    q = None
    for i, ch in enumerate(rest):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or rest[i - 1] in " \t"):
            j = i
            while j > 0 and rest[j - 1] in " \t":
                j -= 1
            return rest[:j], rest[j:]
    return rest.rstrip(), rest[len(rest.rstrip()):]


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _meaningful(line):
    s = line.strip()
    return bool(s) and not s.startswith("#")


def scan(lines):
    """블록 매핑 키를 경로로 색인한다: {경로: (줄 번호, 들여쓰기, 값 부분, 노드 끝 줄 번호)}.

    값이 있는 스칼라의 이어지는 줄·블록 스칼라(| >) 본문·목록 항목은 키로 보지 않는다.
    """
    index = {}
    stack = []          # [(indent, key)]
    skip_deeper = None  # 이 들여쓰기보다 깊은 줄은 앞 키의 값(이어지는 줄)이다
    for i, line in enumerate(lines):
        if not _meaningful(line):
            continue
        ind = _indent(line)
        if skip_deeper is not None:
            if ind > skip_deeper:
                continue
            skip_deeper = None
        m = KEY_RE.match(line)
        if not m or line.lstrip().startswith("- "):
            continue
        key = m.group("key")
        if key[:1] in "\"'":
            key = key[1:-1]
        while stack and stack[-1][0] >= ind:
            stack.pop()
        path = tuple(k for _, k in stack) + (key,)
        value, _c = split_comment(m.group("rest").strip())
        index.setdefault(path, (i, ind, value, None))
        stack.append((ind, key))
        if value:
            skip_deeper = ind
    # 노드 끝: 다음 의미 있는 줄 중 들여쓰기가 더 얕거나, 같은데 목록 항목이 아닌 줄의 앞
    out = {}
    for path, (i, ind, value, _) in index.items():
        end = i
        for j in range(i + 1, len(lines)):
            if not _meaningful(lines[j]):
                continue
            jind = _indent(lines[j])
            if jind < ind or (jind == ind and not lines[j].lstrip().startswith("- ")):
                break
            end = j
        out[path] = (i, ind, value, end)
    return out


def scalar(value):
    """한 줄 YAML 스칼라 표기. 필요하면 따옴표를 붙인다."""
    if value is None:
        return "null"
    text = yaml.safe_dump({"k": value}, allow_unicode=True, width=1 << 30, default_flow_style=False)
    body = text[len("k: "):].rstrip("\n")
    if "\n" in body:
        raise StateError("값은 한 줄이어야 한다")
    return body


def replace_scalar_line(lines, idx, path, new_value):
    """경로의 스칼라 값을 바꾼다 -> (새 줄 목록, 새로 달라진 줄 수, 원래 줄 중 없어진 줄 수).

    값 없이 적힌 키(`blocked_reason:` 처럼 하위 줄도 없는 것)는 null 스칼라로 보고 고친다
    (templates/state.yaml 이 이 형식이다). 값의 이어지는 줄은 지운다.
    """
    if path not in idx:
        raise StateError(f"{dotted(path)} 줄을 찾지 못했다")
    i, ind, value, end = idx[path]
    if (not value and end != i) or (value and value[0] in "{[|>"):
        raise StateError(f"{dotted(path)} 는 한 줄 스칼라가 아니다 - 도구로 고치지 않는다")
    m = KEY_RE.match(lines[i])
    _v, comment = split_comment(m.group("rest"))
    keytext = lines[i][:m.start("rest") - 1]
    new_line = f"{keytext}: {scalar(new_value)}{comment}"
    if new_line == lines[i] and end == i:
        return lines, 0, 0
    # 이어지는 줄 사이의 주석·빈 줄은 값이 아니므로 남긴다 (지우는 것은 값의 이어지는 줄뿐)
    rng = lines[i + 1:end + 1]
    kept = [ln for ln in rng if not _meaningful(ln)]
    return lines[:i] + [new_line] + kept + lines[end + 1:], 1, 1 + (len(rng) - len(kept))


def replace_in_flow(lines, idx, parent, key, new_value):
    """`uid: {k: v, k2: v2}` 한 줄 흐름 매핑 안의 값을 바꾼다 -> (새 줄 목록, 달라진 줄 수, 없어진 줄 수)."""
    if parent not in idx:
        raise StateError(f"{dotted(parent)} 줄을 찾지 못했다")
    i = idx[parent][0]
    line = lines[i]
    m = KEY_RE.match(line)
    rest = m.group("rest")
    if "{" not in rest or "}" not in rest:
        raise StateError(f"{dotted(parent)} 는 한 줄 흐름 매핑이 아니다 - 도구로 고치지 않는다")
    pat = re.compile(r"([{,]\s*" + re.escape(key) + r"\s*:\s*)([^,}]*?)(\s*[,}])")
    hits = pat.findall(line)
    if len(hits) != 1:
        raise StateError(f"{dotted(parent)} 안에서 {key} 를 하나로 찾지 못했다")
    new_line = pat.sub(lambda mm: mm.group(1) + scalar(new_value) + mm.group(3), line, count=1)
    if new_line == line:
        return lines, 0, 0
    return lines[:i] + [new_line] + lines[i + 1:], 1, 1


def insert_child(lines, idx, parent, key, new_value):
    """블록 매핑 parent 에 `key: value` 줄을 넣는다. units 가 있으면 그 앞에, 없으면 노드 끝에.
    -> (새 줄 목록, 달라진 줄 수 1, 없어진 줄 수 0)"""
    i, ind, value, end = idx[parent]
    if value:
        raise StateError(f"{dotted(parent)} 가 블록 매핑이 아니다")
    kids = [(p, v) for p, v in idx.items() if len(p) == len(parent) + 1 and p[:-1] == parent]
    child_ind = min((v[1] for _, v in kids), default=ind + 2)
    units = idx.get(parent + ("units",))
    pos = units[0] if units else end + 1
    return lines[:pos] + [" " * child_ind + f"{key}: {scalar(new_value)}"] + lines[pos:], 1, 0


def check_line_diff(before, after, new_diff, old_removed):
    """형식 대조: 새 본문에서 달라진 줄 수가 변경 수와 같고, 원래 본문에서 없어진 줄 수가
    대상 줄(과 그 이어지는 줄) 수와 같아야 한다. 나머지 줄은 바이트 단위로 같아야 한다."""
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    got_new = got_old = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            got_old += i2 - i1
            got_new += j2 - j1
    if (got_new, got_old) != (new_diff, old_removed):
        raise StateError(f"고친 결과의 줄 변화가 예상과 다르다(새 줄 {got_new}/{new_diff}, 없어진 줄 {got_old}/{old_removed})"
                         " - 쓰지 않는다 (주석·빈 줄 손실 방지)")


def edit_text(text, data, changes):
    """changes = [(경로, 새값)] 를 줄 단위로 반영한 새 본문.

    반영 뒤 두 가지를 대조해 하나라도 어긋나면 StateError 로 쓰지 않는다.
      - 의미: 다시 읽은 dict 가 기대(원래 dict 에 같은 변경을 한 것)와 같다.
      - 형식: 달라진 줄은 변경한 줄뿐이고 나머지 줄은 바이트 단위로 같다.
    """
    nl = "\r\n" if "\r\n" in text else "\n"
    before = text.replace("\r\n", "\n").split("\n")
    lines = list(before)
    expect = copy.deepcopy(data)
    new_diff = old_removed = 0
    for path, value in changes:
        idx = scan(lines)
        parent = path[:-1]
        if path in idx:
            lines, nd, orm = replace_scalar_line(lines, idx, path, value)
        elif parent in idx and idx[parent][2][:1] == "{":
            lines, nd, orm = replace_in_flow(lines, idx, parent, path[-1], value)
        elif parent in idx and path[-1] in ("blocked_reason",):
            lines, nd, orm = insert_child(lines, idx, parent, path[-1], value)
        else:
            raise StateError(f"{dotted(path)} 를 줄에서 찾지 못했다")
        new_diff += nd
        old_removed += orm
        set_in(expect, path, value)
    out = "\n".join(lines)
    try:
        got = yaml.safe_load(out) or {}
    except yaml.YAMLError as ex:
        raise StateError(f"고친 결과가 YAML 로 읽히지 않는다 - 쓰지 않는다: {ex}")
    if got != expect:
        raise StateError("고친 결과가 대상 값 말고 다른 곳도 바꿨다 - 쓰지 않는다 (블록 구조를 사람이 확인한다)")
    check_line_diff(before, lines, new_diff, old_removed)
    return out.replace("\n", nl)


# ---------------------------------------------------------------- 게이트

def run_gate(stage, slice_id, unit, state_text, report=None):
    """새 state 로 gate.py check 를 돌려 (종료 코드, 요약 줄 목록) 을 돌려준다."""
    fd, tmp = tempfile.mkstemp(suffix=".yaml", prefix="pa-state-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(state_text)
    try:
        cmd = [sys.executable, os.path.join(TOOLS, "gate.py"), "check", "--stage", str(stage), "--format", "json"]
        if slice_id:
            cmd += ["--slice", slice_id]
        if unit:
            cmd += ["--unit", unit]
        if report:   # gate.py 는 저장소 루트에서 돌므로 호출한 위치 기준 절대 경로로 넘긴다
            cmd += ["--report", os.path.abspath(report)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PA_STATE_FILE=tmp)
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    try:
        res = json.loads(p.stdout)
        rep = os.path.basename(res.get("report") or "")
        fails = [f"{r['hook']}: {it['field']} {it['message']}" for r in res.get("results", [])
                 for it in r.get("findings", []) if it.get("severity") in ("FAIL", "CRITICAL")]
        lines = [f"레포트 {rep}"] + fails
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        lines = [((p.stderr or "") + (p.stdout or "")).strip()[:600] or f"gate.py 종료 코드 {p.returncode}"]
    return p.returncode, lines


def gate_command(stage, sl, unit):
    return (f"gate.py check --stage {stage}" + (f" --slice {sl}" if sl else "")
            + (f" --unit {unit}" if unit else ""))


# ---------------------------------------------------------------- 명령

def read_bytes(path):
    if not os.path.exists(path):
        raise StateError(f"state.yaml 이 없다: {path} (templates/state.yaml 로 먼저 만든다)")
    with open(path, "rb") as f:
        return f.read()


def load_state(path, raw=None):
    raw = read_bytes(path) if raw is None else raw
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as ex:
        raise StateError(f"state.yaml 이 UTF-8 이 아니다: {ex}")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as ex:
        raise StateError(f"state.yaml 을 읽지 못했다: {ex}")
    return text, data


# blocked_reason 안의 도구 소유 사유 조각: `[<라벨>] <사유>` 를 ' | ' 로 잇는다.
# 라벨은 slice 단계면 단계 키(stage5_integration), unit 이면 'unit <id>.<단계 키>'.
# 라벨 없는 글(사람이 적은 hold 사유 등)은 도구가 건드리지 않는다.
REASON_SEP = " | "


def reason_label(path):
    return path[2] if len(path) == 3 else f"unit {path[3]}.{path[4]}"


def merge_reason(current, label, reason):
    """current 에서 label 조각을 빼고(reason 이 있으면 새 조각을 붙여) 돌려준다. 남는 것이 없으면 None."""
    # 사람이 여러 줄로 적은 사유는 한 줄로 모은다(도구는 한 줄 스칼라만 쓴다)
    flat = " ".join(str(current).split()) if current not in (None, "") else ""
    parts = [p for p in flat.split(REASON_SEP) if p.strip()]
    tag = f"[{label}] "
    parts = [p for p in parts if not p.startswith(tag)]
    if reason:
        parts.append(tag + reason)
    return REASON_SEP.join(parts) if parts else None


def elsewhere_declared(data, path):
    ew = data.get("elsewhere") if isinstance(data.get("elsewhere"), dict) else {}
    key = path[1] if path[0] == "stages" else dotted(path)
    rec = ew.get(key)
    return isinstance(rec, dict) and str(rec.get("declared_by") or "").startswith("사람:")


def cmd_get(a):
    path = resolve(a.stage, a.slice, a.unit)
    _text, data = load_state(a.file)
    print(get_in(data, path))
    return 0


def cmd_set(a):
    path = resolve(a.stage, a.slice, a.unit)
    value = a.value
    reason = (a.reason or "").strip() or None
    if value == "blocked" and not reason:
        raise StateError("blocked 는 --reason 이 필수다 (blocked_reason 에 쓴다)")
    if reason and ("\n" in reason or "\r" in reason):
        raise StateError("--reason 은 한 줄로 쓴다")
    if reason and find_emoji(reason):
        raise StateError("--reason 에 이모지를 넣지 않는다 - 텍스트로 고친다 (pipeline-core §15)")
    if reason:
        reason = " ".join(reason.split())   # 'a  |  b' 처럼 공백이 겹쳐도 나중에 모아지면 구분자가 되므로 먼저 모은다
    if reason and REASON_SEP in reason:
        # 조각 구분자가 사유 안에 있으면 풀 때 뒷부분이 라벨 없는 고아 조각으로 남는다 - ' / ' 로 바꿔 저장한다
        reason = reason.replace(REASON_SEP, " / ")
        print(f"[state] 사유의 '{REASON_SEP.strip()}' 구분자는 ' / ' 로 바꿔 저장한다: {reason}", file=sys.stderr)
    # 낙관적 동시성: 잠금 없이 읽기 -> 편집 -> 게이트, 그 뒤 잠금 안에서 다시 읽어 원문과 바이트 단위로 같을 때만 쓴다.
    # 게이트가 몇 분 걸려도 잠금을 쥐지 않으므로 rr.py 등 다른 쓰기가 대기 시간 초과로 실패하지 않고,
    # 그 사이 다른 쓰기(Edit 도구 포함)가 있었으면 예전 본문으로 덮어쓰지 않는다.
    raw = read_bytes(a.file)
    text, data = load_state(a.file, raw)
    old = get_in(data, path)
    if isinstance(old, dict):
        raise StateError(f"{dotted(path)} 는 값이 아니라 블록이다")
    if value == "done_elsewhere" and not elsewhere_declared(data, path):
        raise StateError(f"done_elsewhere 는 state.yaml 의 elsewhere 선언(declared_by '사람:<이름>')이 있어야 한다 "
                         f"- 선언은 사람만 한다 (templates/state.yaml)")
    stamp = kst_full()
    changes = [(path, value)]
    old_reason = new_reason = None
    if path[0] == "slices":
        old_reason = (data["slices"][path[1]] or {}).get("blocked_reason")
        if value == "blocked":
            new_reason = merge_reason(old_reason, reason_label(path), reason)
        elif old == "blocked":   # 풀면 이 항목의 사유 조각만 지운다 (다른 단계·unit·사람이 적은 사유는 남는다)
            new_reason = merge_reason(old_reason, reason_label(path), None)
        else:
            new_reason = old_reason
        if new_reason != old_reason:
            changes.append((("slices", path[1], "blocked_reason"), new_reason))
    if old == value and old_reason == new_reason:
        print(f"[state] {dotted(path)} 는 이미 {value} 다 - 바꾸지 않았다")
        return 0
    if "updated_at" in data and not isinstance(data.get("updated_at"), dict):
        changes.append((("updated_at",), stamp))
    new_text = edit_text(text, data, changes)
    gate_note = None
    if value == "done":
        stage, sl, unit = gate_args(path)
        rc, lines = run_gate(stage, sl, unit, new_text, a.report)
        gate_note = f"{gate_command(stage, sl, unit)} -> {'통과' if rc == 0 else 'FAIL'}"
        if rc != 0:
            print(f"[state] 거부: {dotted(path)} = done - {gate_command(stage, sl, unit)} 차단(FAIL). 아무것도 바꾸지 않았다",
                  file=sys.stderr)
            for ln in lines[:10]:
                print(f"    {ln}", file=sys.stderr)
            print("    레포트·pa-meta 를 고쳐 게이트를 통과시키거나, --value blocked --reason 으로 기록한다", file=sys.stderr)
            return 1
        gate_note += f" ({lines[0]})" if lines else ""
    if a.dry_run:
        print(f"[state] (미리보기) {dotted(path)}: {old} -> {value}" + (f" | 게이트 {gate_note}" if gate_note else ""))
        return 0
    with file_lock(a.file):
        if read_bytes(a.file) != raw:
            print(f"[state] 거부: 판정하는 동안 state.yaml 이 바뀌었다 - 아무것도 바꾸지 않았다. 같은 명령을 다시 실행한다 "
                  f"({dotted(path)} = {value})", file=sys.stderr)
            return 3
        atomic_write_text(a.file, new_text)
        rec = {"at": stamp, "key": dotted(path), "from": old, "to": value, "reason": reason}
        if new_reason != old_reason:
            rec["blocked_reason_from"] = old_reason
            rec["blocked_reason_to"] = new_reason
        if gate_note:
            rec["gate"] = gate_note
        if a.by:
            rec["by"] = a.by
        with open(history_path(a.file), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[state] {stamp} {dotted(path)}: {old} -> {value}" + (f" | 게이트 {gate_note}" if gate_note else ""))
    return 0


def _short(node, keys):
    return " ".join(f"s{k[5]}={node.get(k)}" for k in keys if k in node)


def cmd_show(a):
    _text, data = load_state(a.file)
    if not a.slice:
        st = data.get("stages") or {}
        print(f"project: {data.get('project')} · iteration: {data.get('iteration')} · updated_at: {data.get('updated_at')}")
        print("stages: " + " ".join(f"{k}={v}" for k, v in st.items()))
    slices = data.get("slices") or {}
    if a.slice and a.slice not in slices:
        raise StateError(f"state.yaml 에 slices.{a.slice} 가 없다")
    items = [(a.slice, slices[a.slice])] if a.slice else list(slices.items())
    if not a.slice:
        cnt = {}
        for _sid, node in items:
            for k in SLICE_KEYS:
                v = (node or {}).get(k)
                if v:
                    cnt.setdefault(k, {}).setdefault(v, 0)
                    cnt[k][v] += 1
        print(f"slices: {len(items)}개")
        for k, c in cnt.items():
            print(f"  {k}: " + " ".join(f"{v}={n}" for v, n in sorted(c.items())))
    for sid, node in items:
        node = node or {}
        line = f"  {sid}: {_short(node, SLICE_KEYS)}"
        if node.get("blocked_reason"):
            line += f" | blocked_reason: {node['blocked_reason']}"
        print(line)
        units = node.get("units") if isinstance(node.get("units"), dict) else {}
        if units:
            print("    units: " + " ".join(f"{u}({_short(un or {}, UNIT_KEYS)})" for u, un in units.items()))
    rr = data.get("refactor_requests")
    if rr and not a.slice:
        print("refactor_requests: " + " ".join(f"{k}={v}" for k, v in rr.items()))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description="state.yaml 을 도구로 고친다 (done 은 gate.py check 통과 시에만)")
    ap.add_argument("--file", help="state.yaml 경로(기본: workspace/<project>/state.yaml, 환경 변수 PA_STATE_TOOL_FILE)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def target(p, need_stage=True):
        p.add_argument("--stage", required=need_stage, help="단계 번호 또는 키 이름(stage2_backend·stage3_common 등)")
        p.add_argument("--slice")
        p.add_argument("--unit")
        p.add_argument("--file", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    g = sub.add_parser("get", help="값 하나 출력")
    target(g)
    g.set_defaults(fn=cmd_get)

    s = sub.add_parser("set", help="값 바꾸기 (done 은 게이트 통과 시에만, blocked 는 --reason 필수)")
    target(s)
    s.add_argument("--value", required=True, choices=VALUES)
    s.add_argument("--reason", help="사유 (blocked 는 필수 - blocked_reason 에 쓴다, 그 밖에는 이력에만)")
    s.add_argument("--report", help="done 판정에 쓸 레포트(기본: gate.py 가 이름 규칙으로 찾는다)")
    s.add_argument("--by", help="기록자(이력에 남긴다)")
    s.add_argument("--dry-run", action="store_true", help="판정·편집만 해 보고 쓰지 않는다")
    s.set_defaults(fn=cmd_set)

    sh = sub.add_parser("show", help="요약 출력")
    sh.add_argument("--slice")
    sh.add_argument("--file", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sh.set_defaults(fn=cmd_show)
    return ap


def main(argv=None):
    fix_console_encoding()
    a = build_parser().parse_args(argv)
    a.file = os.path.abspath(a.file or default_state_path())
    try:
        return a.fn(a)
    except StateError as ex:
        print(f"[state] {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
