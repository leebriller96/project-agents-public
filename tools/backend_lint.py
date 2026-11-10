#!/usr/bin/env python3
"""백엔드 lint 설정 감지 - target_dir 의 빌드 파일에 lint 플러그인이 있으면 실행 명령을 알려 준다.

배경: 프론트엔드는 앱마다 eslint 설정과 `lint` 스크립트가 있어 4단계가 늘 돌리지만,
백엔드는 lint 도구를 지침이 다루지 않아 대상 저장소에 Checkstyle 등이 있어도 2단계가 돌리지 않았다.
이 도구는 **대상 저장소에 이미 있는 설정만** 찾는다. 설정이 없으면 아무것도 요구하지 않는다
(lint 도구를 새로 넣는 것은 대상 저장소 소유자의 결정이다).

감지 대상
- Maven(pom.xml): maven-checkstyle-plugin, spotless-maven-plugin, maven-pmd-plugin, spotbugs-maven-plugin
- Gradle(build.gradle / build.gradle.kts): checkstyle, com.diffplug.spotless, pmd, com.github.spotbugs

사용
  python tools/backend_lint.py detect <target_dir>               # 사람이 읽는 목록
  python tools/backend_lint.py detect <target_dir> --format json # 게이트·에이전트용
"""
import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

SKIP_DIRS = {"node_modules", "target", "build", ".git", ".gradle", ".idea", "dist", ".mvn"}

# (도구 이름, pom artifactId, Maven 목표)
MAVEN = [
    ("checkstyle", "maven-checkstyle-plugin", "checkstyle:check"),
    ("spotless", "spotless-maven-plugin", "spotless:check"),
    ("pmd", "maven-pmd-plugin", "pmd:check"),
    ("spotbugs", "spotbugs-maven-plugin", "spotbugs:check"),
]
# (도구 이름, 플러그인 id 정규식, Gradle 작업)
GRADLE = [
    ("checkstyle", r"""(?:id\s*\(?\s*['"]checkstyle['"]|^\s*checkstyle\s*$|apply\s+plugin:\s*['"]checkstyle['"])""", "checkstyleMain"),
    ("spotless", r"""com\.diffplug\.spotless""", "spotlessCheck"),
    ("pmd", r"""(?:id\s*\(?\s*['"]pmd['"]|^\s*pmd\s*$|apply\s+plugin:\s*['"]pmd['"])""", "pmdMain"),
    ("spotbugs", r"""com\.github\.spotbugs""", "spotbugsMain"),
]


def _strip_xml_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _build_files(target_dir):
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name in ("pom.xml", "build.gradle", "build.gradle.kts"):
                yield os.path.join(root, name)


def detect(target_dir):
    """찾은 lint 도구 목록. 항목: tool·build·file(target_dir 기준)·command."""
    found = []
    seen = set()
    has_mvnw = os.path.isfile(os.path.join(target_dir, "mvnw"))
    has_gradlew = os.path.isfile(os.path.join(target_dir, "gradlew"))
    for path in sorted(_build_files(target_dir)):
        rel = os.path.relpath(path, target_dir).replace("\\", "/")
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if path.endswith("pom.xml"):
            body = _strip_xml_comments(text)
            for tool, artifact, goal in MAVEN:
                if re.search(r"<artifactId>\s*" + re.escape(artifact) + r"\s*</artifactId>", body):
                    if ("maven", tool) in seen:
                        continue
                    seen.add(("maven", tool))
                    mvn = "./mvnw" if has_mvnw else "mvn"
                    pre = "compile " if tool == "spotbugs" else ""
                    found.append({"tool": tool, "build": "maven", "file": rel,
                                  "command": f"{mvn} -q {pre}{goal}"})
        else:
            for tool, pattern, task in GRADLE:
                if re.search(pattern, text, flags=re.M):
                    if ("gradle", tool) in seen:
                        continue
                    seen.add(("gradle", tool))
                    gw = "./gradlew" if has_gradlew else "gradle"
                    found.append({"tool": tool, "build": "gradle", "file": rel, "command": f"{gw} {task}"})
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description="백엔드 lint 설정 감지")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", help="target_dir 의 백엔드 lint 설정을 찾는다")
    d.add_argument("target_dir")
    d.add_argument("--format", choices=["text", "json"], default="text")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.target_dir):
        sys.exit(f"[backend-lint] 폴더가 없다: {a.target_dir}")
    found = detect(a.target_dir)
    if a.format == "json":
        print(json.dumps({"target_dir": a.target_dir, "linters": found}, ensure_ascii=False, indent=2))
        return 0
    if not found:
        print("[backend-lint] 백엔드 lint 설정 없음 - 2단계 lint 게이트를 요구하지 않는다")
        return 0
    print(f"[backend-lint] {len(found)}개 찾음 - 2단계 gates 에 kind=lint 로 실행 결과를 적는다")
    for f in found:
        print(f"  - {f['tool']} ({f['build']}, {f['file']}): {f['command']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
