#!/usr/bin/env python3
# pre_commit.py — git pre-commit 훅의 검사 본체 (tools/hooks/pre-commit 이 부른다)
#
# 목적: 이모지 금지·workspace 커밋 금지는 Claude Code 훅(guard.py)에서만 강제됐다. 다른 에이전트·사람이
#       커밋할 때도 같은 기준이 걸리도록 커밋 시점에 한 번 더 막는다. 기준은 쓰기 시점 훅과 같은 것을 쓴다.
#
# 검사(스테이지된 파일만, 작업 트리가 아니라 **스테이지된 내용**으로 본다)
#   1) 커밋 금지 경로 — workspace/·docs/samples/·config/project.yaml 이 추가·수정으로 스테이지되면 거부한다.
#      삭제(git rm --cached 로 추적 해제)는 허용한다 - 잘못 올라간 파일을 빼는 정상 경로다.
#   2) 이모지 — quality.py 의 NO-EMOJI(critical) 규칙. quality.py 가 보지 않는 확장자(.py 등)도
#      같은 판정 모듈(_emoji.py)로 본다. external/(subtree 로 편입한 외부 도구)는 selfcheck 와 같이 제외한다.
#      gitlink(하위 모듈, mode 160000)는 파일 내용이 없어 이모지 검사만 제외한다(커밋 금지 경로 검사는 그대로).
#
# 사용법: python tools/hooks/pre_commit.py        (git 저장소 안에서)
# 종료 코드: 0 통과 · 1 거부 (검사 본체 오류·스테이지 내용을 꺼내지 못함도 거부 - 통과로 보지 않는다)
# 우회(--no-verify·core.hooksPath 덮어쓰기)는 지침과 guard.py 가 금지한다.

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

FORBIDDEN_PREFIXES = ("workspace/", "docs/samples/")   # 소문자로 비교한다
FORBIDDEN_FILES = ("config/project.yaml",)
SKIP_PREFIXES = ("external/",)


def git(args, cwd, **kw):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, **kw)


def repo_root(cwd=None):
    p = git(["rev-parse", "--show-toplevel"], cwd or os.getcwd(), text=True, encoding="utf-8")
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def staged_files(root):
    """추가·복사·수정·이름 변경·형식 변경으로 스테이지된 파일 (삭제 제외). 저장소 기준 상대경로."""
    p = git(["diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z"], root)
    if p.returncode != 0:
        return []
    return [x for x in p.stdout.decode("utf-8", "replace").split("\0") if x]


class CheckError(Exception):
    """검사를 끝까지 할 수 없다 - 통과로 보지 않고 커밋을 막는다."""


def gitlinks(root):
    """스테이지(인덱스)의 gitlink(하위 모듈, mode 160000) 경로. 내용이 없어 꺼내도 읽을 파일이 없다."""
    p = git(["ls-files", "--stage", "-z"], root)
    if p.returncode != 0:
        raise CheckError(f"스테이지 목록을 읽지 못했다(git ls-files 종료 코드 {p.returncode})")
    entries = p.stdout.decode("utf-8", "replace").split("\0")
    return {e.split("\t", 1)[1] for e in entries if e.startswith("160000 ") and "\t" in e}


def forbidden(paths):
    """커밋 금지 경로. 대소문자를 가리지 않는다 - Windows(core.ignorecase)에서는 `Workspace/…` 도 같은 실제 폴더다."""
    return sorted(p for p in paths
                  if p.lower().startswith(FORBIDDEN_PREFIXES) or p.lower() in FORBIDDEN_FILES)


def export_staged(root, paths, dest):
    """스테이지된 내용을 dest 아래에 같은 상대경로로 꺼낸다 (작업 트리의 미스테이지 변경은 섞지 않는다).
    꺼내기가 실패하면 이모지 검사가 통째로 비므로 CheckError 로 막는다."""
    if not paths:
        return
    data = ("\0".join(paths) + "\0").encode("utf-8")
    p = subprocess.run(["git", "checkout-index", "--prefix=" + dest.replace(os.sep, "/") + "/", "-z", "--stdin"],
                       cwd=root, input=data, capture_output=True)
    if p.returncode != 0:
        raise CheckError("스테이지 내용을 꺼내지 못했다(git checkout-index 종료 코드 "
                         f"{p.returncode}): {p.stderr.decode('utf-8', 'replace').strip()[:300]}")


def quality_covers(rel):
    """quality.py 의 이모지 검사가 이 파일을 읽는가 (확장자·건너뛰는 폴더 기준)."""
    import quality
    s = "/" + rel
    if any(f"/{d}/" in s for d in quality.SKIP_DIRS):
        return False
    return s.lower().endswith(quality.EMOJI_EXTS) or os.path.basename(s).startswith(".env")


def emoji_findings(root, paths):
    """[(상대경로, 줄, 상세)] - quality.py NO-EMOJI 와, quality.py 가 보지 않는 파일은 같은 판정 모듈로.

    판정 모듈은 여기서 불러온다 - 모듈 최상위에서 불러오면 깨졌을 때 run() 의 안내 없이 traceback 만 나온다."""
    import quality
    from _emoji import find_emoji
    links = gitlinks(root)
    targets = [p for p in paths if not p.startswith(SKIP_PREFIXES) and p not in links]
    if not targets:
        return []
    tmp = tempfile.mkdtemp(prefix="pa-precommit-")
    try:
        export_staged(root, targets, tmp)
        out = []
        covered = [p for p in targets if quality_covers(p)]
        if covered:
            res = quality.scan(tmp, covered)
            out += [(f["file"], f["line"], f["detail"]) for f in res["findings"] if f["rule"] == "NO-EMOJI"]
        for p in targets:
            if p in covered:
                continue
            fp = os.path.join(tmp, p)
            if os.path.islink(fp):
                continue   # 심볼릭 링크는 내용이 대상 경로 문자열뿐이다
            try:
                with open(fp, encoding="utf-8") as fh:
                    text = fh.read()
            except UnicodeDecodeError:
                continue   # 바이너리·다른 인코딩은 이모지 판정 대상이 아니다
            except OSError as ex:
                raise CheckError(f"꺼낸 파일을 읽지 못했다: {p} ({ex})")
            lines = text.split("\n")
            for no, col, _ch, cp in find_emoji(text):
                out.append((p, no, f"{cp} ({col}열): {lines[no - 1].strip()[:80]}"))
        return sorted(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    root = repo_root()
    if not root:
        print("[pre-commit] git 저장소를 찾지 못했다 - 검사하지 않는다", file=sys.stderr)
        return 0
    paths = staged_files(root)
    problems = []
    bad = forbidden(paths)
    if bad:
        problems.append("커밋 금지 경로가 스테이지됐다 (workspace/·docs/samples/·config/project.yaml 은 git 에 올리지 않는다):")
        problems += [f"  - {p}" for p in bad[:20]]
        if len(bad) > 20:
            problems.append(f"  ... 외 {len(bad) - 20}건")
        problems.append("  조치: git restore --staged <경로> 로 스테이지에서 뺀다 (.gitignore 를 확인한다)")
    try:
        hits = emoji_findings(root, [p for p in paths if p not in bad])
    except CheckError as ex:
        hits = []
        problems.append(f"이모지 검사를 끝내지 못했다 - 통과로 보지 않는다: {ex}")
    if hits:
        problems.append("이모지가 있다 (quality.py NO-EMOJI, critical - 예외 없음):")
        problems += [f"  - {f}:{ln}  {d}" for f, ln, d in hits[:30]]
        if len(hits) > 30:
            problems.append(f"  ... 외 {len(hits) - 30}건")
        problems.append("  조치: 텍스트로 바꾼다 (완료·주의·[의미차이:태그명]). 시험에서 문자가 필요하면 escape(\\uXXXX)로 쓴다")
    if problems:
        print("[pre-commit] 커밋을 거부한다.\n" + "\n".join(problems)
              + "\n훅을 끄는 옵션(--no-verify·core.hooksPath)은 쓰지 않는다 - 원인을 고쳐 다시 커밋한다.", file=sys.stderr)
        return 1
    return 0


def run():
    """본체 예외는 커밋을 막는다(종료 1). python 을 못 찾는 경우(sh 훅)만 통과시킨다 - 16-hooks.md 의 git 훅 정책."""
    try:
        return main()
    except Exception as ex:  # noqa: BLE001
        print(f"[pre-commit] 검사 본체 오류로 커밋을 막는다: {type(ex).__name__}: {ex}\n"
              "원인을 고친 뒤 다시 커밋한다(훅을 끄지 않는다).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
