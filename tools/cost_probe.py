#!/usr/bin/env python3
# cost_probe.py — Claude Code 대화 기록(jsonl)에서 토큰 사용을 집계해 "어디서 캐시 읽기가 쌓이는가" 를 보여준다.
#
# 배경: 파이프라인 비용의 대부분은 입력·출력이 아니라 캐시 읽기다. 캐시 읽기는 "매 API 호출마다 그때까지 쌓인 문맥 전체" 를
#       다시 읽는 양의 합이라, 한 번 문맥에 들어간 큰 출력(빌드 로그·통째 읽은 파일·보고 전문)은 그 뒤 모든 호출에서 다시 비용이 된다.
#       그래서 단순 합계가 아니라 "들어간 크기 × 그 뒤 남은 호출 수" (누적 기여)로 원인을 줄 세운다.
#
# 사용법:
#   python tools/cost_probe.py <기록 디렉토리 또는 jsonl>...  [--top 20] [--format human|json] [--since 2026-09-01]
#   예) python tools/cost_probe.py "C:\Users\<사용자>\.claude\projects\C--Users-...-project-agents"
#
# 읽는 것: <세션>.jsonl(메인)과 <세션>/subagents/agent-*.jsonl(서브에이전트, 종류는 같은 이름의 .meta.json).
#          옛 형식처럼 서브에이전트가 메인 파일 안에 isSidechain 으로 섞여 있으면 그것도 따로 센다.
# 주의: 한 API 응답이 블록마다 여러 줄로 기록되며 같은 usage 가 반복된다 — message.id 로 중복을 제거한다.
#       토큰 수는 기록의 usage 값이고, 출력 크기의 토큰 환산(누적 기여)만 문자 수 기반 추정이다.
# 의존성: 없음(표준 라이브러리)

import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
CACHE_GAP_SEC = 300          # 5분 캐시 유지 시간
BIG_RESULT_CHARS = 2000      # 이보다 작은 출력은 개별 목록에 올리지 않는다


def est_tokens(text):
    """문자 수 기반 토큰 추정(한글 약 0.9토큰/자, 그 밖 약 3.3자/토큰). 정확한 값이 아니라 순위용이다."""
    if not text:
        return 0
    h = len(HANGUL_RE.findall(text))
    return int(h * 0.9 + (len(text) - h) / 3.3)


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def content_text(c):
    """tool_result 의 content(문자열 또는 블록 목록)를 문자열로."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = []
        for b in c:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    out.append(b.get("text", ""))
                elif b.get("type") == "image":
                    out.append("[image]" + "x" * 5000)   # 이미지는 약 1.5천 토큰 — 문자 수로 근사
        return "\n".join(out)
    return ""


SEG_SKIP = {"cd", "pushd", "export", "set", "source", "echo", "sleep"}   # 이 명령으로 시작하는 구간은 건너뛴다
PREFIX_SKIP = {"env", "sudo", "time", "timeout", "nice"}               # 앞에 붙는 실행 보조 명령


def bash_key(cmd):
    """Bash 명령을 분류 키로 줄인다: mvn·gradlew·pnpm·python <도구>.py 등."""
    cmd = (cmd or "").strip()
    first = re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd)
    for seg in first:
        toks = seg.split()
        while toks and (toks[0] in PREFIX_SKIP or "=" in toks[0] or toks[0].startswith("-") or toks[0].isdigit()):
            toks = toks[1:]
        if not toks or toks[0] in SEG_SKIP:
            continue
        exe = os.path.basename(toks[0].strip("\"'"))
        if exe.startswith("python") or exe in ("py",):
            for t in toks[1:]:
                if t.endswith(".py"):
                    return "python " + t.replace("\\", "/").split("/")[-1]
                if t == "-m" and len(toks) > toks.index(t) + 1:
                    return "python -m " + toks[toks.index(t) + 1]
            return "python"
        if exe in ("npm", "pnpm", "npx", "yarn", "git", "docker") and len(toks) > 1:
            sub = next((t for t in toks[1:] if not t.startswith("-")), "")
            return f"{exe} {sub}".strip()
        return exe
    return "(빈 명령)"


def read_key(path):
    p = (path or "").replace("\\", "/")
    m = re.search(r"\.claude/(skills|agents|commands)/(.+)$", p)
    if m:
        return "지침 " + m.group(2)
    if "/workspace/" in p:
        tail = p.split("/workspace/", 1)[1].split("/", 1)
        return "workspace " + (tail[1].split("/")[0] if len(tail) > 1 else "")
    ext = os.path.splitext(p)[1] or "(확장자 없음)"
    return "파일 " + ext


def tool_key(name, inp):
    inp = inp or {}
    if name == "Bash":
        return "Bash " + bash_key(inp.get("command"))
    if name == "Read":
        return "Read " + read_key(inp.get("file_path"))
    if name in ("Agent", "Task"):
        return "Agent " + str(inp.get("subagent_type") or "general")
    if name == "Skill":
        return "Skill " + str(inp.get("skill"))
    return name


def tool_hint(name, inp):
    inp = inp or {}
    if name == "Bash":
        return (inp.get("command") or "").replace("\n", " ")[:140]
    for k in ("file_path", "pattern", "skill", "description", "query"):
        if inp.get(k):
            return str(inp[k])[:140]
    return ""


class Stream:
    """한 문맥(메인 세션 또는 서브에이전트 하나)의 집계."""

    def __init__(self, sid, kind, agent_type, path):
        self.sid, self.kind, self.agent_type, self.path = sid, kind, agent_type, path
        self.calls = []        # [(ts, usage)] — message.id 중복 제거 후 순서대로
        self.seen = set()
        self.items = []        # 문맥에 들어간 큰 덩어리: dict(call_idx, kind, key, hint, chars, tokens)
        self.tool_uses = {}    # tool_use_id → (name, input)
        self.tool_calls = 0
        self.read_paths = collections.Counter()
        self.compactions = 0
        self.model = None

    # --- 수집 ---
    def add_assistant(self, rec):
        msg = rec.get("message") or {}
        mid = msg.get("id") or rec.get("requestId") or rec.get("uuid")
        self.model = self.model or msg.get("model")
        if mid not in self.seen and isinstance(msg.get("usage"), dict):
            self.seen.add(mid)
            self.calls.append((parse_ts(rec.get("timestamp")), msg["usage"]))
        for b in msg.get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name, inp = b.get("name"), b.get("input") or {}
            self.tool_uses[b.get("id")] = (name, inp)
            self.tool_calls += 1
            if name == "Read" and inp.get("file_path"):
                self.read_paths[inp["file_path"].replace("\\", "/")] += 1
            body = "".join(str(inp.get(k) or "") for k in ("content", "new_string", "prompt"))
            if len(body) >= BIG_RESULT_CHARS:
                self.items.append(dict(call_idx=len(self.calls), kind="입력", key=tool_key(name, inp) + " (입력)",
                                       hint=tool_hint(name, inp), chars=len(body), tokens=est_tokens(body)))

    def add_user(self, rec):
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            if isinstance(content, str) and len(content) >= BIG_RESULT_CHARS:
                self.items.append(dict(call_idx=len(self.calls), kind="프롬프트", key="프롬프트·첨부", hint=content[:140],
                                       chars=len(content), tokens=est_tokens(content)))
            return
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_result":
                text = content_text(b.get("content"))
                name, inp = self.tool_uses.get(b.get("tool_use_id"), ("?", {}))
                self.items.append(dict(call_idx=len(self.calls), kind="결과", key=tool_key(name, inp),
                                       hint=tool_hint(name, inp), chars=len(text), tokens=est_tokens(text)))
            elif b.get("type") == "text" and len(b.get("text", "")) >= BIG_RESULT_CHARS:
                t = b["text"]
                self.items.append(dict(call_idx=len(self.calls), kind="프롬프트", key="프롬프트·첨부", hint=t[:140],
                                       chars=len(t), tokens=est_tokens(t)))

    def add_attachment(self, rec):
        a = rec.get("attachment") or {}
        if not isinstance(a, dict) or a.get("type") in ("prompt_snapshot",):   # 시스템 프롬프트 사본은 시작 문맥에 이미 포함
            return
        if a.get("type") == "instructions" and isinstance(a.get("files"), list):
            # CLAUDE.md 등 지침 파일 — 어느 파일이 얼마나 들어오는지가 원인 분석의 핵심이라 파일별로 나눈다
            for f in a["files"]:
                if not isinstance(f, dict):
                    continue
                body = str(f.get("content") or "")
                path = str(f.get("path") or "?").replace("\\", "/")
                self.items.append(dict(call_idx=len(self.calls), kind="첨부", key="지침파일 " + path,
                                       hint=str(f.get("type") or ""), chars=len(body), tokens=est_tokens(body)))
            return
        text = json.dumps(a, ensure_ascii=False)
        self.items.append(dict(call_idx=len(self.calls), kind="첨부", key="첨부 " + str(a.get("type")), hint="",
                               chars=len(text), tokens=est_tokens(text)))

    def add_compaction(self):
        self.compactions += 1
        # 압축 이전 덩어리는 압축 뒤 호출에서 다시 읽히지 않는다 — 경계를 표시한다
        self.items.append(dict(call_idx=len(self.calls), kind="압축", key="(compact)", hint="", chars=0, tokens=0))

    # --- 계산 ---
    def totals(self):
        t = dict(calls=len(self.calls), input=0, cache_read=0, cache_write=0, cache_write_1h=0, output=0,
                 max_context=0, first_context=0, expiry_rewrites=0, expiry_tokens=0)
        prev_ts = None
        for i, (ts, u) in enumerate(self.calls):
            inp = int(u.get("input_tokens") or 0)
            cr = int(u.get("cache_read_input_tokens") or 0)
            cw = int(u.get("cache_creation_input_tokens") or 0)
            ctx = inp + cr + cw
            t["input"] += inp
            t["cache_read"] += cr
            t["cache_write"] += cw
            t["cache_write_1h"] += int(((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens")) or 0)
            t["output"] += int(u.get("output_tokens") or 0)
            t["max_context"] = max(t["max_context"], ctx)
            if i == 0:
                t["first_context"] = ctx
            # 캐시 만료 추정: 앞 호출과 5분 넘게 떨어졌고 문맥 대부분을 다시 썼다
            if ts and prev_ts and (ts - prev_ts).total_seconds() > CACHE_GAP_SEC and ctx and cw > 0.5 * ctx:
                t["expiry_rewrites"] += 1
                t["expiry_tokens"] += cw
            prev_ts = ts or prev_ts
        if self.calls and self.calls[0][0] and self.calls[-1][0]:
            t["minutes"] = round((self.calls[-1][0] - self.calls[0][0]).total_seconds() / 60, 1)
        else:
            t["minutes"] = None
        return t

    def contributions(self):
        """덩어리마다 '추정 토큰 × 그 뒤 같은 문맥에서 일어난 호출 수' — 캐시 읽기에 기여한 양의 근사."""
        n = len(self.calls)
        out = []
        for pos, it in enumerate(self.items):
            if it["kind"] == "압축":
                continue
            # 이 덩어리보다 뒤에 기록된 첫 압축 경계까지만 다시 읽힌다
            end = next((c["call_idx"] for c in self.items[pos + 1:] if c["kind"] == "압축"), n)
            remain = max(0, end - it["call_idx"])
            out.append(dict(it, remain=remain, contrib=it["tokens"] * remain))
        return out


def stream_files(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(glob.glob(os.path.join(p, "**", "*.jsonl"), recursive=True))
        elif os.path.isfile(p):
            files.append(p)
        else:
            sys.stderr.write(f"[cost_probe] 경로가 없다: {p}\n")
    return sorted(set(files))


def meta_agent_type(jsonl_path):
    meta = os.path.splitext(jsonl_path)[0] + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as f:
            return json.load(f).get("agentType")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def load_streams(files, since=None):
    streams = []
    for path in files:
        is_sub = os.path.basename(os.path.dirname(path)) == "subagents"
        sid = os.path.splitext(os.path.basename(path))[0]
        main = Stream(sid, "subagent" if is_sub else "main",
                      (meta_agent_type(path) or "unknown") if is_sub else "(메인)", path)
        side = {}   # 옛 형식: 메인 파일 안의 sidechain(agentId 별)
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError as ex:
            sys.stderr.write(f"[cost_probe] 읽기 실패 {path}: {ex}\n")
            continue
        with fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if since and (rec.get("timestamp") or "") and rec["timestamp"][:10] < since:
                    continue
                target = main
                if rec.get("isSidechain") and not is_sub:
                    aid = rec.get("agentId") or "sidechain"
                    if aid not in side:
                        side[aid] = Stream(f"{sid}:{aid}", "subagent", "sidechain", path)
                    target = side[aid]
                t = rec.get("type")
                if t == "assistant":
                    target.add_assistant(rec)
                elif t == "user":
                    target.add_user(rec)
                elif t == "attachment":
                    target.add_attachment(rec)
                elif t == "system" and rec.get("subtype") == "compact_boundary":
                    target.add_compaction()
        for s in [main] + list(side.values()):
            if s.calls:
                streams.append(s)
    return streams


def analyze(streams, top=20):
    rows = []
    by_type = collections.defaultdict(lambda: collections.Counter())
    cat = collections.Counter()
    cat_chars = collections.Counter()
    cat_n = collections.Counter()
    big = []
    reread = []
    grand = collections.Counter()
    for s in streams:
        t = s.totals()
        for k in ("calls", "input", "cache_read", "cache_write", "cache_write_1h", "output",
                  "expiry_rewrites", "expiry_tokens"):
            grand[k] += t[k]
        grand["tool_calls"] += s.tool_calls
        contrib = s.contributions()
        contrib_sum = sum(c["contrib"] for c in contrib)
        base_part = t["first_context"] * max(0, t["calls"] - 1)
        rows.append(dict(id=s.sid, kind=s.kind, agent=s.agent_type, model=s.model, tool_calls=s.tool_calls,
                         compactions=s.compactions, base_part=base_part, contrib_part=contrib_sum, **t))
        bt = by_type[s.agent_type]
        bt["n"] += 1
        for k in ("calls", "cache_read", "cache_write", "output"):
            bt[k] += t[k]
        bt["tool_calls"] += s.tool_calls
        bt["max_context_sum"] += t["max_context"]
        bt["first_context_sum"] += t["first_context"]
        bt["base_part"] += base_part
        for c in contrib:
            cat[c["key"]] += c["contrib"]
            cat_chars[c["key"]] += c["chars"]
            cat_n[c["key"]] += 1
            if c["chars"] >= BIG_RESULT_CHARS:
                big.append(dict(stream=s.sid, agent=s.agent_type, key=c["key"], hint=c["hint"], chars=c["chars"],
                                tokens=c["tokens"], remain=c["remain"], contrib=c["contrib"]))
        for p, n in s.read_paths.items():
            if n >= 3:
                reread.append(dict(stream=s.sid, agent=s.agent_type, path=p, count=n))
    total_cr = grand["cache_read"] or 1
    grand["base_part"] = sum(r["base_part"] for r in rows)
    grand["contrib_part"] = sum(r["contrib_part"] for r in rows)
    types = []
    for a, bt in by_type.items():
        types.append(dict(agent=a, n=bt["n"], calls=bt["calls"], tool_calls=bt["tool_calls"],
                          cache_read=bt["cache_read"], share=round(100.0 * bt["cache_read"] / total_cr, 1),
                          avg_calls=round(bt["calls"] / bt["n"], 1),
                          avg_first_context=int(bt["first_context_sum"] / bt["n"]),
                          avg_max_context=int(bt["max_context_sum"] / bt["n"]),
                          base_share=round(100.0 * bt["base_part"] / (bt["cache_read"] or 1), 1)))
    types.sort(key=lambda r: -r["cache_read"])
    rows.sort(key=lambda r: -r["cache_read"])
    big.sort(key=lambda r: -r["contrib"])
    reread.sort(key=lambda r: -r["count"])
    cats = [dict(key=k, contrib=v, items=cat_n[k], chars=cat_chars[k],
                 share=round(100.0 * v / total_cr, 1)) for k, v in cat.most_common(top)]
    instr = [dict(path=k[len("지침파일 "):], contrib=v, loads=cat_n[k], avg_chars=int(cat_chars[k] / max(cat_n[k], 1)),
                  share=round(100.0 * v / total_cr, 1))
             for k, v in cat.most_common() if k.startswith("지침파일 ")][:top]
    return dict(totals=dict(grand), streams=rows[:top], agent_types=types, categories=cats, instruction_files=instr,
                big_items=big[:top], reread=reread[:top], stream_count=len(streams),
                advice=advice(grand, types, cats))


def advice(grand, types, cats):
    out = []
    cr, cw = grand["cache_read"], grand["cache_write"]
    if cr and cw:
        out.append(f"캐시 읽기:쓰기 = {cr / max(cw, 1):.1f}:1")
    if grand["expiry_rewrites"]:
        out.append(f"5분 넘는 공백 뒤 문맥 재작성 {grand['expiry_rewrites']}회·{grand['expiry_tokens']:,} 토큰 — "
                   "긴 빌드 대기 뒤 캐시가 만료된 흔적이다. 비중이 크면 subagentPromptCacheTtl: \"1h\" 를 검토한다")
    bash = sum(c["contrib"] for c in cats if c["key"].startswith("Bash "))
    if cr and bash / cr > 0.15:
        out.append(f"Bash 출력의 누적 기여가 캐시 읽기의 약 {100 * bash / cr:.0f}% — 출력 축약 훅의 효과가 큰 구간이다")
    for t in types:
        if t["agent"] != "(메인)" and t["base_share"] > 40:
            out.append(f"{t['agent']}: 시작 문맥(지침 등)이 캐시 읽기의 {t['base_share']}% — 읽는 지침 범위를 줄일 대상")
    return out


def fmt_k(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def print_human(res):
    g = res["totals"]
    print(f"문맥 {res['stream_count']}개 · API 호출 {g.get('calls', 0):,} · tool call {g.get('tool_calls', 0):,}")
    print(f"캐시 읽기 {fmt_k(g.get('cache_read', 0))} · 캐시 쓰기 {fmt_k(g.get('cache_write', 0))}"
          f"(1h {fmt_k(g.get('cache_write_1h', 0))}) · 입력 {fmt_k(g.get('input', 0))} · 출력 {fmt_k(g.get('output', 0))}")
    print("\n[에이전트 종류별] 캐시 읽기 순")
    print("  종류                     개수  평균호출  시작문맥  평균최대문맥  캐시읽기    비중  시작문맥몫")
    for t in res["agent_types"]:
        print(f"  {t['agent'][:24]:<24} {t['n']:>4} {t['avg_calls']:>9} {fmt_k(t['avg_first_context']):>9}"
              f" {fmt_k(t['avg_max_context']):>12} {fmt_k(t['cache_read']):>9} {t['share']:>6}% {t['base_share']:>8}%")
    cr = g.get("cache_read", 0) or 1
    rest = max(0, cr - g.get("base_part", 0) - g.get("contrib_part", 0))
    print(f"\n[캐시 읽기 분해(추정)] 시작 문맥 {100 * g.get('base_part', 0) / cr:.0f}% · 작업 중 들어간 것 "
          f"{100 * g.get('contrib_part', 0) / cr:.0f}% · 그 밖(모델의 사고·응답 문장·짧은 입력 등) {100 * rest / cr:.0f}%")
    print("\n[문맥에 들어간 것의 누적 기여] 추정 토큰 × 그 뒤 호출 수")
    for c in res["categories"]:
        print(f"  {c['share']:>5}%  {fmt_k(c['contrib']):>8}  {c['items']:>5}건  {c['key']}")
    if res.get("instruction_files"):
        print("\n[자동으로 올라오는 지침 파일(CLAUDE.md 등)] 누적 기여 순 — 크기 × 올라온 뒤 호출 수")
        for f in res["instruction_files"]:
            print(f"  {f['share']:>5}%  {fmt_k(f['contrib']):>8}  평균 {f['avg_chars']:>7,}자 × {f['loads']:>4}회  {f['path']}")
    print("\n[가장 비싼 개별 덩어리]")
    for b in res["big_items"]:
        print(f"  {fmt_k(b['contrib']):>8}  {b['chars']:>7,}자 × {b['remain']:>3}호출  [{b['agent']}] {b['key']}  {b['hint'][:80]}")
    if res["reread"]:
        print("\n[같은 파일 3회 이상 읽기]")
        for r in res["reread"]:
            print(f"  {r['count']:>3}회  [{r['agent']}] {r['path']}")
    print("\n[캐시 읽기가 큰 문맥]")
    for r in res["streams"]:
        print(f"  {fmt_k(r['cache_read']):>8}  호출 {r['calls']:>4}  최대 {fmt_k(r['max_context']):>6}"
              f"  {r['minutes'] if r['minutes'] is not None else '-':>6}분  [{r['agent']}] {r['id']}")
    if res["advice"]:
        print("\n[판단]")
        for a in res["advice"]:
            print("  - " + a)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Claude Code 기록의 토큰 사용 집계 (캐시 읽기 원인 분석)")
    ap.add_argument("paths", nargs="+", help="~/.claude/projects/<프로젝트> 디렉토리 또는 jsonl 파일")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--since", help="YYYY-MM-DD 이후 기록만")
    ap.add_argument("--format", choices=["human", "json"], default="human")
    ap.add_argument("--out", help="결과를 이 파일에 UTF-8 로 쓴다 (Windows PowerShell 의 > 리다이렉션은 한글을 깨뜨린다)")
    args = ap.parse_args(argv)
    files = stream_files(args.paths)
    if not files:
        sys.stderr.write("[cost_probe] jsonl 기록을 찾지 못했다\n")
        return 1
    res = analyze(load_streams(files, args.since), args.top)
    out = open(args.out, "w", encoding="utf-8", newline="\n") if args.out else None
    try:
        if out:
            sys.stdout = out
        if args.format == "json":
            print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        else:
            print_human(res)
    finally:
        if out:
            sys.stdout = sys.__stdout__
            out.close()
            print(f"결과 저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
