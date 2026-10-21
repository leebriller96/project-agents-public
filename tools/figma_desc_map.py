#!/usr/bin/env python3
# figma_desc_map.py — 저장해 둔 Figma 화면 정의서(노드 JSON + 프레임 이미지)에서
#   오른쪽 Description 칸의 번호별 설명과 화면 위 번호 배지(Marker)가 가리키는 컴포넌트를 짝지어 남긴다.
#   Figma 를 다시 열지 않고 저장본만으로 만든다(조회 횟수 제한 대응).
#
#   python tools/figma_desc_map.py --dir <저장 폴더> [--page page_<id>.json ...] [--img img] [--no-crop]
#     → <저장 폴더>/desc_map/description_map.md · description_map.json · crops/<프레임>/<번호>.png
#
# 판정 방식
#   - 설명 행: 이름이 Description 인 FRAME 아래 Row 의 첫 칸(번호)과 나머지 글자. 본문 안의 "1-1. 제목" 줄은 하위 항목으로 나눈다.
#   - 배지: 이름이 Marker 인 노드(보통 05_DescriptionMarker 아래). 배지 글자가 번호다.
#   - 대상 컴포넌트: 배지 중심에서 왼쪽 위 모서리가 가장 가까운 노드(설명 칸·배지 제외, 너무 작거나 큰 것 제외).
#     같은 거리면 더 큰 노드. 설명 제목이 대상 안 글자에 있으면 일치, 없으면 확인으로 표시한다(사람·AI 가 crop 이미지로 확인).
import argparse, glob, json, os, re, sys

NUM = re.compile(r"^\d+(?:-\d+)*$")
SUB = re.compile(r"^\s*(\d+(?:-\d+)+)\.\s*(.*)$")
HEAD_LABELS = ("화면 ID", "화면 명", "URL 경로", "화면경로", "화면유형", "사용자 구분")


def bbox(n):
    b = n.get("absoluteBoundingBox") or {}
    return (b.get("x"), b.get("y"), b.get("width"), b.get("height")) if b.get("x") is not None else None


def texts(n):
    out = []
    def w(x):
        if x.get("type") == "TEXT" and x.get("characters", "").strip():
            out.append(x)
        for c in x.get("children", []):
            w(c)
    w(n)
    return out


def find_named(n, name):
    out = []
    def w(x):
        if x.get("name") == name:
            out.append(x)
            return
        for c in x.get("children", []):
            w(c)
    w(n)
    return out


def screen_frames(page):
    """CANVAS·SECTION 바로 아래 FRAME 중 Description 칸이 있는 것."""
    out = []
    def w(n):
        for c in n.get("children", []):
            if c.get("type") == "SECTION":
                w(c)
            elif c.get("type") == "FRAME" and find_named(c, "Description"):
                out.append(c)
    w(page)
    return out


def header(frame):
    ts = texts(frame)
    meta = {}
    for t in ts:
        lab = t["characters"].strip()
        if lab not in HEAD_LABELS or lab in meta:
            continue
        x, y, w, h = bbox(t)
        right = [u for u in ts if u is not t and abs(bbox(u)[1] - y) < 4 and bbox(u)[0] > x]
        if right:
            meta[lab] = min(right, key=lambda u: bbox(u)[0])["characters"].strip()
    return meta


def desc_rows(frame):
    rows = []
    for d in find_named(frame, "Description"):
        for r in d.get("children", []):
            ts = sorted(texts(r), key=lambda t: (bbox(t)[1], bbox(t)[0]))
            if not ts:
                continue
            cols = r.get("children", [])
            first = texts(cols[0]) if cols else []
            key = first[0]["characters"].strip() if first else ""
            body = "\n".join(t["characters"] for t in ts if not first or t is not first[0])
            if key in ("Description",) and not body.strip():
                continue
            rows.append({"no": key, "body": body.strip(), "node": r.get("id")})
    return rows


def split_sub(no, body):
    """본문을 번호 항목으로 나눈다: 머리(no) + '1-1. 제목' 줄마다 하위 항목."""
    items, cur = [], {"no": no, "title": "", "lines": []}
    for line in body.splitlines():
        m = SUB.match(line)
        if m:
            items.append(cur)
            cur = {"no": m.group(1), "title": m.group(2).strip(), "lines": [line.strip()]}
        else:
            cur["lines"].append(line.rstrip())
    items.append(cur)
    head = items[0]
    if head["lines"]:
        first = next((l for l in head["lines"] if l.strip()), "")
        head["title"] = first.strip()
    return [i for i in items if i["lines"] or i is head]


def markers(frame):
    out = []
    for m in find_named_all(frame, "Marker"):
        ts = texts(m)
        lab = ts[0]["characters"].strip() if ts else ""
        if NUM.match(lab):
            out.append({"no": lab, "node": m.get("id"), "bbox": bbox(m)})
    return out


def find_named_all(n, name):
    out = []
    def w(x):
        if x.get("name") == name:
            out.append(x)
        for c in x.get("children", []):
            w(c)
    w(n)
    return out


def candidates(frame):
    skip = set()
    for name in ("Description", "Marker"):
        for x in find_named_all(frame, name):
            def mark(y):
                skip.add(id(y))
                for c in y.get("children", []):
                    mark(c)
            mark(x)
    fx, fy, fw, fh = bbox(frame)
    out, parent = [], {}
    def inside(b, clip):
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        return clip[0] <= cx <= clip[0] + clip[2] and clip[1] <= cy <= clip[1] + clip[3]
    def w(x, clip):
        if x.get("clipsContent") and bbox(x):
            clip = bbox(x)
        for c in x.get("children", []):
            if id(c) in skip or not c.get("visible", True) or "Description" in (c.get("name") or ""):
                continue   # 설명 칸·배지 묶음(05_DescriptionMarker 등)은 대상이 아니다
            parent[id(c)] = x
            b = bbox(c)
            if b and not inside(b, clip):   # 잘려서 보이지 않는 노드(접힌 드롭다운 항목 등)
                continue
            if b and b[2] * b[3] >= 200 and b[2] * b[3] <= fw * fh * 0.5:
                out.append(c)
            w(c, clip)
    w(frame, bbox(frame))
    return out, parent


def widen(c, parent, frame):
    """라벨 글자 하나로 잡히면 입력칸까지 든 한 줄(높이가 크게 늘지 않는 조상)로 넓힌다."""
    if c.get("type") != "TEXT":
        return c
    fw = bbox(frame)[2]
    h = bbox(c)[3]
    p = parent.get(id(c))
    while p is not None and p is not frame and bbox(p) and bbox(p)[3] <= h * 3 and bbox(p)[2] <= fw * 0.6:
        c, p = p, parent.get(id(p))
    return c


FILLER = re.compile(r"\[(?:필수|선택)\]|^\s*\d+(?:-\d+)*\.?|\(\d+/\d+\)|영역|버튼|팝업|아이콘|[\[\]()/*:·,.]")


def verdict(title, words):
    """일치 = 제목 낱말이 대상 글자에 있음, 영역 = 묶음 항목이라 이미지로 확인, 확인 = 사람·AI 가 crop 으로 확인."""
    toks = [t for t in FILLER.sub(" ", title).split() if len(t) >= 2]
    joined = " ".join(words).replace(" ", "")
    if toks and any(t in joined for t in toks):
        return "일치"
    return "영역" if re.search(r"영역\s*(\(\d+/\d+\))?\s*$", title) else "확인"


def target_for(mk, cands):
    mx, my, mw, mh = mk["bbox"]
    cx, cy = mx + mw / 2, my + mh / 2
    best = None
    for c in cands:
        x, y, w, h = bbox(c)
        if x + w < mx or y + h < my:      # 배지보다 왼쪽·위에서 끝나는 노드는 대상이 아니다
            continue
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        # 배지와 같은 높이에 걸치고 왼쪽 끝이 배지 근처인 노드(배지가 그 줄·칸 왼쪽에 붙은 경우)는 가장 작은 것을 먼저 고른다
        on = y <= cy <= y + h and -40 <= x - cx <= 60 and h <= 150
        key = (0, w * h) if on else (1, round(d / 6), -(w * h))
        if best is None or key < best[0]:
            best = (key, c, d)
    return best


def render_origin(frame):
    """프레임 이미지의 원점과 크기 - 잘리지 않는 프레임은 자식 범위까지 그린다."""
    x, y, w, h = bbox(frame)
    if frame.get("clipsContent", True):
        return x, y, w, h
    x0, y0, x1, y1 = x, y, x + w, y + h
    def walk(n):
        nonlocal x0, y0, x1, y1
        for c in n.get("children", []):
            b = c.get("absoluteRenderBounds") or c.get("absoluteBoundingBox")
            if b and c.get("visible", True):
                x0, y0 = min(x0, b["x"]), min(y0, b["y"])
                x1, y1 = max(x1, b["x"] + b["width"]), max(y1, b["y"] + b["height"])
            walk(c)
    walk(frame)
    return x0, y0, x1 - x0, y1 - y0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--page", nargs="*")
    ap.add_argument("--img", default="img")
    ap.add_argument("--no-crop", action="store_true")
    a = ap.parse_args()
    pages = a.page or sorted(glob.glob(os.path.join(a.dir, "page_*.json")))
    outdir = os.path.join(a.dir, "desc_map")
    os.makedirs(outdir, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        Image = None
    result, md = [], ["# Figma Description 매핑", "",
                      "화면 오른쪽 Description 의 번호 항목 ↔ 화면 위 번호 배지 ↔ 배지가 가리키는 컴포넌트.",
                      "판정 '일치' = 설명 제목이 대상 컴포넌트 글자에 있음, '영역' = 묶음 항목(crop 으로 확인), '확인' = crop 이미지로 사람·AI 가 확인할 것, "
                      "'배지 없음' = 설명만 있음, '설명 없음' = 배지만 있음.", ""]
    vf = os.path.join(a.dir, "figma_version.json")
    if os.path.exists(vf):
        v = json.load(open(vf, encoding="utf-8"))
        md[3:3] = [f"- 기준 Figma: {v.get('name')} · version `{v.get('version')}` · lastModified {v.get('lastModified')}",
                   "- 다음 조회 때 `GET /v1/files/<key>?depth=1` 의 version·lastModified 가 같으면 이 저장본만 본다. 다르면 쓰는 쪽(page)만 다시 받아 프레임별로 비교한다.", ""]
    for pf in pages:
        page = json.load(open(os.path.join(a.dir, os.path.basename(pf)) if not os.path.exists(pf) else pf, encoding="utf-8"))
        for fr in screen_frames(page):
            meta = header(fr)
            items = [s for r in desc_rows(fr) for s in split_sub(r["no"], r["body"])]
            mks = markers(fr)
            cands, parent = candidates(fr)
            img_path = os.path.join(a.dir, a.img, fr["id"].replace(":", "-") + ".png")
            img = Image.open(img_path) if (Image and not a.no_crop and os.path.exists(img_path)) else None
            ox, oy, ow, oh = render_origin(fr)
            sx = img.size[0] / ow if img else 1
            sy = img.size[1] / oh if img else 1
            fdir = os.path.join(outdir, "crops", fr["id"].replace(":", "-"))
            by_no = {}
            for mk in mks:
                by_no.setdefault(mk["no"], []).append(mk)
            entry = {"frame": fr["id"], "name": fr.get("name"), "meta": meta, "image": os.path.relpath(img_path, a.dir), "items": []}
            md += [f"## {meta.get('화면 ID', '-')} {meta.get('화면 명', fr.get('name'))}", "",
                   f"- 프레임 `{fr['id']}` {fr.get('name')} · 이미지 `{entry['image']}`",
                   f"- 화면경로: {meta.get('화면경로', '-')} · URL: {meta.get('URL 경로', '-')} · 사용자: {meta.get('사용자 구분', '-')}", "",
                   "| 번호 | 설명 제목 | 대상 컴포넌트 | 대상 안 글자(앞부분) | 판정 | crop |", "|---|---|---|---|---|---|"]
            # Figma 배지 번호 오류 정정: 같은 번호 배지가 여럿이고 같은 상위 번호의 설명 항목에 배지가 없으면,
            # 대상 글자가 그 설명 제목과 맞는 배지를 그 항목으로 옮긴다(옮긴 것은 판정에 표시).
            fixed = {}
            nos = {it["no"] for it in items}
            for no, lst in list(by_no.items()):
                if len(lst) < 2:
                    continue
                parent_no = no.rsplit("-", 1)[0]
                free = [it for it in items if it["no"] not in by_no and it["no"].rsplit("-", 1)[0] == parent_no and it["no"] in nos]
                for mk in list(lst):
                    hit = target_for(mk, cands)
                    if not hit:
                        continue
                    words = [x["characters"].strip() for x in texts(widen(hit[1], parent, fr))]
                    own = next((it for it in items if it["no"] == no), None)
                    if own and verdict(own["title"], words) == "일치":
                        continue
                    for it in free:
                        if verdict(it["title"], words) == "일치":
                            lst.remove(mk)
                            by_no.setdefault(it["no"], []).append(mk)
                            fixed[id(mk)] = no
                            free.remove(it)
                            break
            seen = set()
            for it in items:
                no = it["no"]
                rec = {"no": no, "title": it["title"], "text": "\n".join(it["lines"]).strip(), "targets": []}
                for mk in by_no.get(no, []):
                    seen.add(id(mk))
                    hit = target_for(mk, cands)
                    t = {"marker": mk["node"], "marker_bbox": mk["bbox"]}
                    if hit:
                        c = widen(hit[1], parent, fr)
                        words = [x["characters"].strip().replace("\n", " ") for x in texts(c)][:8]
                        t.update({"node": c.get("id"), "type": c.get("type"), "name": c.get("name"), "bbox": bbox(c),
                                  "texts": words, "verdict": verdict(it["title"], words)})
                        if id(mk) in fixed:
                            t["verdict"] += f"(Figma 배지 번호 오류: 배지는 {fixed[id(mk)]})"
                        if img:
                            os.makedirs(fdir, exist_ok=True)
                            x, y, w, h = bbox(c)
                            x0, y0 = min(x, mk["bbox"][0]) - 12, min(y, mk["bbox"][1]) - 12
                            x1, y1 = max(x + w, mk["bbox"][0] + mk["bbox"][2]) + 12, max(y + h, mk["bbox"][1] + mk["bbox"][3]) + 12
                            box = (int((x0 - ox) * sx), int((y0 - oy) * sy), int((x1 - ox) * sx), int((y1 - oy) * sy))
                            crop = img.crop(box).convert("RGB")
                            ImageDraw.Draw(crop).rectangle(((x - x0) * sx, (y - y0) * sy, (x + w - x0) * sx, (y + h - y0) * sy), outline=(255, 0, 0), width=2)
                            cp = os.path.join(fdir, f"{no}.png" if len(by_no[no]) == 1 else f"{no}_{mk['node'].replace(':', '-').replace(';', '_')}.png")
                            crop.save(cp)
                            t["crop"] = os.path.relpath(cp, a.dir)
                    rec["targets"].append(t)
                entry["items"].append(rec)
                if not rec["targets"]:
                    md.append(f"| {no} | {it['title'][:40]} | - | - | 배지 없음 | - |")
                for t in rec["targets"]:
                    md.append(f"| {no} | {it['title'][:40]} | `{t.get('node', '-')}` {t.get('type', '')} {str(t.get('name', ''))[:24]} | "
                              f"{' / '.join(t.get('texts', []))[:60]} | {t.get('verdict', '대상 없음')} | {t.get('crop', '-')} |")
            orphan = [mk for mk in mks if id(mk) not in seen]
            for mk in orphan:
                entry["items"].append({"no": mk["no"], "title": "", "text": "", "targets": [{"marker": mk["node"], "verdict": "설명 없음"}]})
                md.append(f"| {mk['no']} | - | 배지 `{mk['node']}` | - | 설명 없음 | - |")
            md += ["", "설명 원문:", ""]
            for rec in entry["items"]:
                if rec["text"]:
                    md += [f"- **{rec['no']}** " + rec["text"].replace("\n", " / ")]
            md.append("")
            result.append(entry)
    json.dump(result, open(os.path.join(outdir, "description_map.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(outdir, "description_map.md"), "w", encoding="utf-8").write("\n".join(md))
    n_items = sum(len(e["items"]) for e in result)
    n_check = sum(1 for e in result for r in e["items"] for t in r["targets"] if t.get("verdict") != "일치")
    print(f"[figma_desc_map] 화면 {len(result)} · 항목 {n_items} · 확인 필요 {n_check} -> {outdir}")


if __name__ == "__main__":
    sys.exit(main())
