# tools/figma_desc_map.py — 저장한 Figma 노드만으로 Description 번호 ↔ 배지 ↔ 컴포넌트 매핑
import json
import os


def _t(i, s, x, y, w=60, h=20):
    return {"id": i, "type": "TEXT", "name": s, "characters": s, "absoluteBoundingBox": {"x": x, "y": y, "width": w, "height": h}}


def _f(i, name, x, y, w, h, kids, **kw):
    return dict({"id": i, "type": "FRAME", "name": name, "absoluteBoundingBox": {"x": x, "y": y, "width": w, "height": h}, "children": kids}, **kw)


def _page():
    row = lambda i, no, body, y: _f(i, "Row", 1500, y, 400, 100, [_f(i + "c", "Col", 1500, y, 40, 100, [_t(i + "n", no, 1505, y + 40, 20)]), _t(i + "b", body, 1550, y, 300, 90)])
    desc = _f("9:1", "Description", 1500, 0, 400, 400, [
        row("9:2", "1", "검색 영역\n검색 조건으로 조회한다.\n1-1. 등록일\n기간 검색\n1-2. 공개 대상\n공통코드", 10),
        row("9:3", "2", "[삭제] 버튼\n삭제한다.", 120)])
    marker = lambda i, no, x, y: _f(i, "Marker", x, y, 30, 30, [_t(i + "t", no, x + 5, y + 5, 20)])
    marks = _f("8:1", "05_DescriptionMarker", 0, 0, 1400, 900, [
        marker("8:2", "1", 10, 70), marker("8:3", "1-1", 40, 95), marker("8:4", "1-1", 400, 95), marker("8:5", "2", 600, 300)])
    search = _f("7:1", "Search", 30, 90, 900, 80, [
        _f("7:2", "DIV", 50, 110, 300, 40, [_t("7:3", "등록일", 50, 120)]),
        _f("7:4", "DIV", 410, 110, 300, 40, [_t("7:5", "공개대상", 410, 120)])])
    btn = {"id": "7:6", "type": "INSTANCE", "name": "DeleteButton", "absoluteBoundingBox": {"x": 620, "y": 320, "width": 80, "height": 36},
           "children": [_t("7:7", "삭제", 630, 328)]}
    head = [_t("6:1", "화면 ID", 0, -50), _t("6:2", "P1", 100, -50), _t("6:3", "화면 명", 0, -25), _t("6:4", "목록", 100, -25)]
    screen = _f("5:1", "10_목록", 0, -60, 2000, 1000, head + [search, btn, marks, desc])
    return {"id": "0:1", "type": "CANVAS", "name": "p", "children": [{"id": "4:1", "type": "SECTION", "name": "s", "children": [screen]}]}


def test_maps_items_markers_and_fixes_duplicate_badge_numbers(sandbox):
    d = os.path.join(sandbox.root, "fig")
    os.makedirs(d)
    json.dump(_page(), open(os.path.join(d, "page_0-1.json"), "w", encoding="utf-8"), ensure_ascii=False)
    out = sandbox.run("figma_desc_map.py", "--dir", d, "--no-crop", check=0).stdout
    assert "화면 1" in out
    res = json.load(open(os.path.join(d, "desc_map", "description_map.json"), encoding="utf-8"))[0]
    assert res["meta"] == {"화면 ID": "P1", "화면 명": "목록"}
    items = {i["no"]: i for i in res["items"]}
    assert items["1-1"]["targets"][0]["node"] == "7:2" and items["1-1"]["targets"][0]["verdict"] == "일치"
    # 배지는 1-1 로 잘못 붙었지만 대상 글자가 '공개대상' 이라 1-2 로 옮긴다
    fixed = items["1-2"]["targets"][0]
    assert fixed["node"] == "7:4" and "배지 번호 오류" in fixed["verdict"]
    assert items["2"]["targets"][0]["node"] == "7:6" and items["2"]["targets"][0]["verdict"] == "일치"
    assert items["1"]["targets"][0]["verdict"] in ("일치", "영역")
