#!/usr/bin/env python3
# selfcheck.py — project-agents 저장소 자체의 정합성 점검 (문서 ↔ 실제 파일)
#
# 목적: 명령·에이전트·스킬·도구·템플릿이 서로를 이름과 경로로 참조하므로, 하나를 바꾸고 다른 곳을 놓치면
#       에이전트가 없는 파일을 찾거나 옛 경로로 쓰게 된다(예: README 의 "서브에이전트 11개" 가 12개가 된 뒤에도 남음,
#       workspace/<project>/ 도입 뒤에도 workspace/state.yaml 경로가 안내문에 남음). 이런 어긋남을 CI 에서 잡는다.
#
# 사용법: python tools/selfcheck.py [--format json]
# 종료 코드: 0 정합 · 1 어긋남 있음
# 의존성: pyyaml

import argparse
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, fix_console_encoding, load_yaml, safe_relpath  # noqa: E402

fix_console_encoding()

AGENT_REF_RE = re.compile(
    r"\b((?:backend|frontend|ingest|slice|common|integration|security|qa|deliverable|sql|behavior-spec|equivalence|ui)-"
    r"(?:developer|reviewer|analyst|planner|refactorer|tester|auditor|runner|writer|migrator|porter|verifier))\b")
SKILL_REF_RE = re.compile(r"\.claude/skills/([a-z0-9-]+)")
TOOL_REF_RE = re.compile(r"\btools/([A-Za-z0-9_-]+\.(?:py|sh))")
TEMPLATE_REF_RE = re.compile(r"\btemplates/([A-Za-z0-9_.-]+\.(?:md|yaml|json))")
# workspace/<project>/ 도입 전의 옛 경로 (workspace/ 바로 아래에 산출물이 있다고 적은 것)
STALE_WS_RE = re.compile(r"workspace/(00_inputs|reports|state\.yaml|slices/|knowledge/|refactor-requests|open-items)")
# 이력 문서는 당시 경로를 그대로 보존한다
HISTORY_FILES = ("docs/LESSONS.md",)
HISTORY_DIRS = ("docs/samples/",)


def rel(p):
    return safe_relpath(p, ROOT)


def frontmatter(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    try:
        return load_yaml_text(text[3:end]), text
    except Exception:
        return None, text


def load_yaml_text(s):
    import yaml
    return yaml.safe_load(s) or {}


def exists_here_or_external(folder, name):
    """이 저장소 또는 external/<도구>/ 아래에 folder/name 이 있는가."""
    if os.path.exists(os.path.join(ROOT, folder, name)):
        return True
    return bool(glob.glob(os.path.join(ROOT, "external", "*", folder, name)))


def doc_files():
    """점검 대상 문서·코드: 이 저장소 소유분만 (external/ subtree·workspace 제외)."""
    pats = ["README.md", "CLAUDE.md", "docs/*.md", "docs/**/*.md", ".claude/**/*.md", "config/*",
            "templates/*", "tools/*.py", "tools/*.sh", ".github/**/*.yml"]
    out = set()
    for p in pats:
        out.update(glob.glob(os.path.join(ROOT, p), recursive=True))
    # .claude/worktrees/ 는 병렬 에이전트의 격리 작업 트리(저장소 복사본)다 — 이중 검사하면 복사본의 어긋남이 섞인다
    wt = os.path.join(ROOT, ".claude", "worktrees") + os.sep
    return sorted(p for p in out if os.path.isfile(p) and not p.startswith(wt))


def main(argv=None):
    ap = argparse.ArgumentParser(description="project-agents 저장소 정합성 점검")
    ap.add_argument("--format", choices=["human", "json"], default="human")
    args = ap.parse_args(argv)
    errors = []

    def err(where, msg):
        errors.append({"where": where, "message": msg})

    agents = {os.path.splitext(os.path.basename(p))[0]: p
              for p in glob.glob(os.path.join(ROOT, ".claude", "agents", "*.md"))}
    skills = {os.path.basename(os.path.dirname(p)): p
              for p in glob.glob(os.path.join(ROOT, ".claude", "skills", "*", "SKILL.md"))}
    ext_skills = {os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(ROOT, "external", "*", ".claude", "skills", "*", "SKILL.md"))}
    commands = sorted(glob.glob(os.path.join(ROOT, ".claude", "commands", "*.md")))

    # 1) frontmatter: 이름 = 파일명, 설명 존재
    for name, p in sorted(agents.items()):
        fm, _ = frontmatter(p)
        if not fm:
            err(rel(p), "frontmatter(---) 가 없거나 YAML 이 깨졌다")
            continue
        if fm.get("name") != name:
            err(rel(p), f"name({fm.get('name')}) 이 파일명({name})과 다르다")
        if not str(fm.get("description", "")).strip():
            err(rel(p), "description 이 없다")
    for name, p in sorted(skills.items()):
        fm, _ = frontmatter(p)
        if not fm:
            err(rel(p), "frontmatter(---) 가 없거나 YAML 이 깨졌다")
            continue
        if fm.get("name") != name:
            err(rel(p), f"name({fm.get('name')}) 이 디렉토리명({name})과 다르다")
        if not str(fm.get("description", "")).strip():
            err(rel(p), "description 이 없다")
    for p in commands:
        fm, _ = frontmatter(p)
        if not fm or not str(fm.get("description", "")).strip():
            err(rel(p), "description frontmatter 가 없다")

    # 2) 문서 안의 참조가 실제로 있는가
    for p in doc_files():
        r = rel(p)
        if r == "tools/selfcheck.py":
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
        history = r in HISTORY_FILES or any(r.startswith(d) for d in HISTORY_DIRS)
        for no, line in enumerate(lines, 1):
            for m in AGENT_REF_RE.finditer(line):
                if m.group(1) not in agents:
                    err(f"{r}:{no}", f"없는 에이전트를 참조한다: {m.group(1)}")
            for m in SKILL_REF_RE.finditer(line):
                if m.group(1) not in skills and m.group(1) not in ext_skills:
                    err(f"{r}:{no}", f"없는 스킬을 참조한다: .claude/skills/{m.group(1)}")
            if history:
                continue
            for m in TOOL_REF_RE.finditer(line):
                # '예정' 표기는 아직 없는 도구다. 6·7단계 문서는 외부 도구 repo 의 tools/ 를 가리키므로 거기도 찾는다
                if "예정" in line or exists_here_or_external("tools", m.group(1)):
                    continue
                err(f"{r}:{no}", f"없는 도구를 참조한다: tools/{m.group(1)}")
            for m in TEMPLATE_REF_RE.finditer(line):
                if exists_here_or_external("templates", m.group(1)):
                    continue
                err(f"{r}:{no}", f"없는 템플릿을 참조한다: templates/{m.group(1)}")
            if STALE_WS_RE.search(line):
                err(f"{r}:{no}", "workspace/<project>/ 가 빠진 옛 경로: " + line.strip()[:90])

    # 2-1) 이모지 금지 — 이 저장소가 소유한 모든 파일(지침·템플릿·도구·문서). 예외 없음.
    #      지침에 이모지가 있으면 에이전트가 산출물에 그대로 옮겨 쓴다(실측: 의미 차이 태그 기호가 Mapper 주석으로 전파).
    from _emoji import find_emoji
    try:
        owned = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8").stdout.split("\n")
    except OSError:
        owned = []
    for t in owned:
        if not t or t.startswith("external/"):
            continue
        fp = os.path.join(ROOT, t)
        try:
            with open(fp, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for no, col, _ch, cp in find_emoji(text):
            err(f"{t}:{no}", f"이모지 {cp} ({col}열) — 텍스트로 바꾼다")

    # 2-2) 전역 규칙(이모지 금지) 조항이 모든 에이전트·스킬·명령 파일에 있는가 — 한 곳이라도 빠지면 그 경로로 새어 나간다
    for p in sorted(list(agents.values()) + list(skills.values()) + commands):
        with open(p, encoding="utf-8") as fh:
            body = fh.read()
        if "공통 금지 — 이모지" not in body and "## 15. 이모지 금지" not in body:
            err(rel(p), "전역 규칙 '공통 금지 — 이모지' 조항이 없다 (pipeline-core §15)")

    # 2-3) 훅 설정이 있고 guard.py 를 가리키는가
    try:
        with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
            settings = json.load(fh)
        cmds = [h.get("command", "") for ev in ("PreToolUse", "SubagentStop")
                for m in (settings.get("hooks") or {}).get(ev, []) for h in m.get("hooks", [])]
        for ev, mode in (("PreToolUse", "pre-tool-use"), ("SubagentStop", "subagent-stop")):
            if not any("tools/hooks/guard.py" in c and mode in c for c in cmds):
                err(".claude/settings.json", f"{ev} 훅이 tools/hooks/guard.py {mode} 를 호출하지 않는다")
    except (OSError, json.JSONDecodeError) as ex:
        err(".claude/settings.json", f"읽기 실패: {ex}")

    # 3) README 의 에이전트 수·목록
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    m = re.search(r"서브에이전트\s*(\d+)\s*개", readme)
    if not m:
        err("README.md", "'서브에이전트 N개' 표기를 찾지 못했다")
    elif int(m.group(1)) != len(agents):
        err("README.md", f"서브에이전트 {m.group(1)}개로 적혀 있으나 실제 {len(agents)}개")
    for name in sorted(agents):
        if name not in readme:
            err("README.md", f"에이전트 {name} 가 README 에 없다")

    # 4) config 예시의 프로필 파일
    try:
        cfg = load_yaml(os.path.join(ROOT, "config", "project.yaml.example"))
        for layer, sk in (("backend", "stage2-backend"), ("frontend", "stage4-frontend")):
            prof = ((cfg.get("stack") or {}).get(layer) or {}).get("profile")
            if prof and not os.path.exists(os.path.join(ROOT, ".claude", "skills", sk, "profiles", f"{prof}.md")):
                err("config/project.yaml.example", f"{layer} 프로필 파일이 없다: {prof}")
    except Exception as ex:
        err("config/project.yaml.example", f"읽기 실패: {ex}")

    # 5) 외부 도구 경로
    try:
        tools_cfg = load_yaml(os.path.join(ROOT, "config", "tools.yaml"))
        for key, node in tools_cfg.items():
            if not isinstance(node, dict) or "path" not in node:
                continue
            base = os.path.join(ROOT, node["path"])
            if not os.path.isdir(base):
                err("config/tools.yaml", f"{key}.path 가 없다: {node['path']}")
                continue
            for k, v in node.items():
                if k in ("skill", "sast_runner", "sast_summarizer", "exporter", "differ", "test_runner",
                         "summarizer", "timestamp", "auditignore_example") and isinstance(v, str):
                    if not os.path.exists(os.path.join(base, v)):
                        err("config/tools.yaml", f"{key}.{k} 가 없다: {node['path']}/{v}")
    except Exception as ex:
        err("config/tools.yaml", f"읽기 실패: {ex}")

    # 6) 커밋 금지 대상 (workspace·실제 설정)
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                                 encoding="utf-8").stdout.split("\n")
        for t in tracked:
            if t.startswith("workspace/") or t == "config/project.yaml":
                err(t, "커밋하면 안 되는 파일이 git 에 올라가 있다")
    except OSError as ex:
        err("git", f"git ls-files 실패: {ex}")

    if args.format == "json":
        print(json.dumps({"errors": errors, "agents": len(agents), "skills": len(skills),
                          "commands": len(commands)}, ensure_ascii=False, indent=2))
    else:
        print(f"에이전트 {len(agents)} · 스킬 {len(skills)} · 명령 {len(commands)}")
        for e in errors:
            print(f"- {e['where']}: {e['message']}")
        print("결과: " + (f"어긋남 {len(errors)}건" if errors else "정합"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
