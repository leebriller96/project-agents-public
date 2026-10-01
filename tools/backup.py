#!/usr/bin/env python3
# backup.py — 프로젝트별 로컬 자산(config/project.yaml + workspace/<project>/) 백업·검증·복원
#
# 배경: 프로젝트 고유 정보(입력 문서·brief §12 결정·state·slices·open item·RR·레포트)와 config 는 git 에서 제외된다.
#       저장소에는 방법론만 올라가므로, PC 가 고장 나면 이 자산은 되살릴 방법이 없다. 특히 brief §12 의 사용자 결정은
#       다시 만들 수 없다. 이 도구는 그 자산을 저장소 밖 폴더(사내 드라이브·비공개 동기화 폴더 등)에 zip 으로 남긴다.
#
# 사용법:
#   python tools/backup.py create [--dest DIR] [--no-inputs] [--keep N]   # 백업 생성 (오래된 것은 keep 개만 남김)
#   python tools/backup.py list   [--dest DIR]                             # 이 프로젝트의 백업 목록
#   python tools/backup.py verify <zip>                                    # 해시 목록과 대조
#   python tools/backup.py restore <zip> [--force]                         # workspace·config 로 복원
#
# 대상 폴더: --dest > config/project.yaml → backup.dir. 저장소 안은 거부한다(실수로 커밋될 수 있다).
# 백업 파일: <dest>/<project>/<yymmddhhmm>_<project>.zip — 안에 MANIFEST.json(파일별 크기·sha256)을 둔다.
# 주의: 입력(00_inputs)에는 AS-IS 설정 파일의 자격증명이 들어 있을 수 있다. 대상 폴더는 접근이 제한된 곳이어야 한다.
# 종료 코드: 0 성공 · 1 검증 실패·충돌 · 2 사용법·설정 오류
# 의존성: pyyaml

import argparse
import datetime
import hashlib
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, config, fix_console_encoding  # noqa: E402

fix_console_encoding()

KST = datetime.timezone(datetime.timedelta(hours=9))
MANIFEST = "MANIFEST.json"
CONFIG_ARC = "config/project.yaml"
SKIP_SUFFIX = (".lock", ".tmp", ".pyc")
DEFAULT_KEEP = 10


def die(msg, code=2):
    sys.stderr.write(f"[backup] {msg}\n")
    sys.exit(code)


def project_name():
    name = (config().get("project") or {}).get("name")
    if not name:
        die("config/project.yaml 에 project.name 이 없다")
    return name


def backup_conf():
    return config().get("backup") or {}


def is_inside(path, parent):
    path, parent = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(parent))
    try:
        return os.path.commonpath([path, parent]) == parent
    except ValueError:   # Windows 에서 드라이브가 다르면 포함 관계가 아니다
        return False


def resolve_dest(arg):
    dest = arg or backup_conf().get("dir")
    if not dest:
        die("백업 위치가 없다. --dest 로 주거나 config/project.yaml 에 backup.dir 을 적는다")
    dest = os.path.abspath(os.path.expanduser(dest))
    if is_inside(dest, ROOT):
        die(f"백업 위치가 저장소 안이다: {dest}\n저장소 밖 폴더를 쓴다 (저장소 안이면 실수로 커밋될 수 있다)")
    return dest


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(name, include_inputs):
    """(zip 안 경로, 실제 경로) 목록. zip 안 경로는 저장소 루트 기준이라 복원 위치가 그대로 정해진다."""
    items = []
    cfg = os.path.join(ROOT, "config", "project.yaml")
    if os.path.isfile(cfg):
        items.append((CONFIG_ARC, cfg))
    ws = os.path.join(ROOT, "workspace", name)
    if not os.path.isdir(ws):
        die(f"workspace 가 없다: {ws}")
    for d, dirs, files in os.walk(ws):
        rel_d = os.path.relpath(d, ws).replace(os.sep, "/")
        if not include_inputs and (rel_d == "00_inputs" or rel_d.startswith("00_inputs/")):
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for fn in sorted(files):
            if fn.endswith(SKIP_SUFFIX):
                continue
            full = os.path.join(d, fn)
            items.append((f"workspace/{name}/" + os.path.relpath(full, ws).replace(os.sep, "/"), full))
    return items


def backups(dest, name):
    d = os.path.join(dest, name)
    if not os.path.isdir(d):
        return []
    # 이름순이 아니라 만든 순서로 정렬한다 — 같은 분의 두 번째 백업(`<ts>-2_`)은 이름순으로 `<ts>_` 보다 앞선다
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(f"_{name}.zip")]
    return sorted(files, key=lambda p: (os.path.getmtime(p), p))


def cmd_create(args):
    name = project_name()
    dest = resolve_dest(args.dest)
    include_inputs = not args.no_inputs and backup_conf().get("include_inputs", True)
    keep = args.keep if args.keep is not None else int(backup_conf().get("keep", DEFAULT_KEEP))
    items = collect(name, include_inputs)
    out_dir = os.path.join(dest, name)
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now(KST).strftime("%y%m%d%H%M")
    out = os.path.join(out_dir, f"{stamp}_{name}.zip")
    n = 1
    while os.path.exists(out):   # 같은 분에 두 번 만들면 덮어쓰지 않는다
        n += 1
        out = os.path.join(out_dir, f"{stamp}-{n}_{name}.zip")
    tmp = out + ".part"
    manifest = {"project": name, "created_at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                "include_inputs": include_inputs, "files": []}
    total = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, full in items:
            size = os.path.getsize(full)
            manifest["files"].append({"path": arc, "size": size, "sha256": sha256(full)})
            z.write(full, arc)
            total += size
        z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
    os.replace(tmp, out)   # 쓰는 도중 중단되면 .part 만 남고 완성된 백업처럼 보이지 않는다
    bad = verify(out)
    if bad:
        die(f"만든 직후 검증 실패: {out}\n- " + "\n- ".join(bad), 1)
    removed = []
    if keep > 0:
        for old in [p for p in backups(dest, name) if p != out][:-(keep - 1) or None]:
            os.remove(old)
            removed.append(os.path.basename(old))
    print(f"백업: {out}")
    print(f"파일 {len(items)}개 · 원본 {total / 1048576:.1f}MB · 압축 {os.path.getsize(out) / 1048576:.1f}MB"
          f" · 입력(00_inputs) {'포함' if include_inputs else '제외'} · 검증 통과")
    if removed:
        print(f"보관 개수({keep}) 초과로 삭제: {', '.join(removed)}")
    return 0


def read_manifest(z):
    try:
        return json.loads(z.read(MANIFEST).decode("utf-8"))
    except KeyError:
        return None


def verify(path):
    """문제 목록. 비어 있으면 정상."""
    bad = []
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as ex:
        return [f"zip 을 열 수 없다: {ex}"]
    with z:
        m = read_manifest(z)
        if m is None:
            return [f"{MANIFEST} 가 없다"]
        names = set(z.namelist()) - {MANIFEST}
        for f in m.get("files", []):
            if f["path"] not in names:
                bad.append(f"빠진 파일: {f['path']}")
                continue
            names.discard(f["path"])
            if hashlib.sha256(z.read(f["path"])).hexdigest() != f["sha256"]:
                bad.append(f"해시 불일치: {f['path']}")
        bad += [f"목록에 없는 파일: {n}" for n in sorted(names)]
    return bad


def cmd_list(args):
    name = project_name()
    dest = resolve_dest(args.dest)
    rows = backups(dest, name)
    if not rows:
        print(f"백업 없음: {os.path.join(dest, name)}")
        return 0
    for p in rows:
        with zipfile.ZipFile(p) as z:
            m = read_manifest(z) or {}
        print(f"{os.path.basename(p)}  {os.path.getsize(p) / 1048576:7.1f}MB  파일 {len(m.get('files', []))}개"
              f"  입력 {'포함' if m.get('include_inputs') else '제외'}")
    return 0


def cmd_verify(args):
    bad = verify(args.zip)
    if bad:
        print("검증 실패:\n- " + "\n- ".join(bad))
        return 1
    print(f"검증 통과: {args.zip}")
    return 0


def safe_target(arc):
    """zip 안 경로를 저장소 안 실제 경로로. 저장소 밖을 가리키는 경로(../ 등)는 거부한다."""
    full = os.path.abspath(os.path.join(ROOT, *arc.split("/")))
    if not is_inside(full, ROOT) or not (arc == CONFIG_ARC or arc.startswith("workspace/")):
        die(f"복원할 수 없는 경로: {arc}", 1)
    return full


def cmd_restore(args):
    bad = verify(args.zip)
    if bad:
        die("검증 실패로 복원하지 않는다:\n- " + "\n- ".join(bad), 1)
    with zipfile.ZipFile(args.zip) as z:
        m = read_manifest(z)
        plan = [(f["path"], safe_target(f["path"])) for f in m["files"]]
        conflicts = []
        for arc, full in plan:
            if os.path.exists(full):
                with open(full, "rb") as fh:
                    if hashlib.sha256(fh.read()).hexdigest() != next(
                            f["sha256"] for f in m["files"] if f["path"] == arc):
                        conflicts.append(arc)
        if conflicts and not args.force:
            print(f"현재 파일과 내용이 다른 {len(conflicts)}개가 있어 복원하지 않았다 (덮어쓰려면 --force):")
            for c in conflicts[:30]:
                print(f"  {c}")
            if len(conflicts) > 30:
                print(f"  … 외 {len(conflicts) - 30}개")
            return 1
        for arc, full in plan:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(z.read(arc))
    print(f"복원: 파일 {len(plan)}개 (덮어쓴 파일 {len(conflicts)}개) ← {args.zip}")
    print("복원 후 python tools/status.py 로 상태를 확인한다. 백업 이후 생긴 파일은 지우지 않았다.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="프로젝트별 로컬 자산(config + workspace/<project>/) 백업·검증·복원")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="백업 생성")
    c.add_argument("--dest")
    c.add_argument("--no-inputs", action="store_true", help="00_inputs 제외 (입력 원본을 따로 보관할 때)")
    c.add_argument("--keep", type=int, help=f"남길 백업 수 (0 = 무제한, 기본 backup.keep 또는 {DEFAULT_KEEP})")
    ls = sub.add_parser("list", help="백업 목록")
    ls.add_argument("--dest")
    v = sub.add_parser("verify", help="백업 검증")
    v.add_argument("zip")
    r = sub.add_parser("restore", help="백업 복원")
    r.add_argument("zip")
    r.add_argument("--force", action="store_true", help="내용이 다른 현재 파일을 덮어쓴다")
    args = ap.parse_args()
    return {"create": cmd_create, "list": cmd_list, "verify": cmd_verify, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
