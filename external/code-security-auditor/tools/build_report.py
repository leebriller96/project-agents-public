#!/usr/bin/env python3
# build_report.py — Markdown 보안 레포트를 HTML로 변환한다. (HTML이 기본 산출물)
#
# 사용법:
#   python tools/build_report.py reports/2606291651_security_report.md
#   python tools/build_report.py reports/2606291651_security_report.md --pdf   # (선택) PDF도 시도
#
# 결과: 같은 디렉토리에 동일 이름의 .html 생성. --pdf 옵션 + weasyprint 설치 시 .pdf도 생성.
#
# 의존성:
#   필수: markdown        (설치: pip install markdown)
#   선택: pygments        (코드 구문 강조. 없으면 강조 없이 출력)
#   선택: weasyprint      (PDF가 꼭 필요할 때만. 보통은 브라우저 Ctrl+P 사용 권장)
#
# PDF가 필요하면: 생성된 HTML을 브라우저로 열고 Ctrl+P → "PDF로 저장"이 가장 간단하고 안정적이다.

import datetime
import os
import re
import sys

# 윈도우 콘솔(cp949)에서 한글 출력이 깨지지 않도록 stdout/stderr를 UTF-8로 고정한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

KST = datetime.timezone(datetime.timedelta(hours=9))

# 심각도별 색상 (HTML 배지/스타일에 사용)
SEVERITY_COLORS = {
    "Critical": "#b00020",
    "High": "#e65100",
    "Medium": "#f9a825",
    "Low": "#2e7d32",
    "Info": "#1565c0",
}
SEVERITY_PATTERN = "|".join(SEVERITY_COLORS)

# HTML 문서 골격 + 스타일. 가독성 있는 레포트 출력을 위해 CSS를 내장한다.
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Malgun Gothic", "Noto Sans KR", sans-serif;
         line-height: 1.65; color: #1a1a1a; max-width: 900px; margin: 0 auto; padding: 40px 24px; }}
  h1 {{ border-bottom: 3px solid #1a1a1a; padding-bottom: 8px; }}
  h2 {{ margin-top: 2.2em; border-bottom: 1px solid #ddd; padding-bottom: 6px; }}
  h3 {{ margin-top: 1.6em; }}
  code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-size: 0.92em; }}
  pre {{ background: #f7f7f7; border: 1px solid #e0e0e0; border-radius: 6px;
        padding: 14px; overflow-x: auto; }}
  pre code {{ background: none; padding: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  blockquote {{ border-left: 4px solid #ccc; margin: 1em 0; padding: 4px 16px; color: #555; }}
  .pdf-hint {{ background: #eef4ff; border: 1px solid #c7dbff; border-radius: 6px;
              padding: 10px 14px; margin-bottom: 24px; font-size: 0.9em; color: #1a3a6b; }}
  .toc {{ background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px;
         padding: 12px 18px; margin-bottom: 28px; font-size: 0.92em; }}
  .toc summary {{ cursor: pointer; font-weight: 600; }}
  .toc ul {{ margin: 6px 0; padding-left: 20px; }}
  .toc a {{ color: #1a3a6b; text-decoration: none; }}
  .footer {{ margin-top: 3em; padding-top: 1em; border-top: 1px solid #ddd;
            color: #888; font-size: 0.85em; }}
  /* 심각도 배지: "심각도: Critical" 표기와 표 셀의 심각도 단어에 자동 적용된다 */
  .sev {{ display: inline-block; padding: 1px 9px; border-radius: 10px; color: #fff;
         font-weight: 700; font-size: 0.85em; letter-spacing: 0.02em; }}
  /* 발견 항목 접기/펼치기 + 심각도 필터 바 */
  .finding {{ border: 1px solid #e3e3e3; border-left-width: 5px; border-radius: 6px; margin: 14px 0; }}
  .finding > summary {{ cursor: pointer; padding: 10px 14px; font-weight: 600; list-style: none;
                       display: flex; gap: 10px; align-items: center; }}
  .finding > summary::-webkit-details-marker {{ display: none; }}
  .finding > summary::before {{ content: "\25B8"; color: #888; font-size: 0.9em; }}
  .finding[open] > summary::before {{ content: "\25BE"; }}
  .finding > summary .fid {{ color: #666; font-family: monospace; font-size: 0.9em; }}
  .finding > .body {{ padding: 4px 18px 12px; border-top: 1px solid #eee; }}
  .finding > .body h3 {{ display: none; }}
  .finding.hidden {{ display: none; }}
  .filterbar {{ position: sticky; top: 0; z-index: 5; background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
               padding: 8px 12px; margin: 0 0 18px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 0.9em; }}
  .filterbar label {{ display: inline-flex; gap: 4px; align-items: center; cursor: pointer; }}
  .filterbar button {{ border: 1px solid #ccc; background: #f7f7f7; border-radius: 4px; padding: 2px 10px; cursor: pointer; }}
  .filterbar .cnt {{ color: #666; margin-left: auto; }}
  {severity_css}
  {code_css}
  /* 인쇄(브라우저 Ctrl+P로 PDF 저장) 시 안내 배너는 숨기고 여백을 정리한다 */
  @media print {{
    body {{ padding: 0; max-width: none; }}
    .pdf-hint {{ display: none; }}
    .toc, .filterbar {{ display: none; }}
    .finding {{ border: none; margin: 0; }}
    .finding > summary {{ display: none; }}
    .finding > .body {{ display: block !important; padding: 0; border: none; }}
    .finding > .body h3 {{ display: block; }}
    .finding.hidden {{ display: block; }}
    pre {{ white-space: pre-wrap; word-break: break-all; overflow-x: visible; }}
    pre, blockquote, table {{ page-break-inside: avoid; }}
    h2, h3 {{ page-break-after: avoid; }}
    .sev {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>
<div class="pdf-hint">PDF로 저장하려면: 이 화면에서 <b>Ctrl + P</b> (Mac은 Cmd + P) → 프린터를 "PDF로 저장" 또는 "Microsoft Print to PDF"로 선택하세요.</div>
{toc}
{content}
<div class="footer">생성: {generated} (KST) · code-security-auditor</div>
<script>
(function () {{
  var findings = document.querySelectorAll("details.finding");
  var bar = document.getElementById("filterbar");
  if (!findings.length || !bar) return;
  var cnt = document.getElementById("filter-count");
  function apply() {{
    var on = {{}};
    bar.querySelectorAll("input[type=checkbox]").forEach(function (c) {{ on[c.value] = c.checked; }});
    var shown = 0;
    findings.forEach(function (f) {{ var v = on[f.dataset.sev] !== false; f.classList.toggle("hidden", !v); if (v) shown++; }});
    cnt.textContent = shown + " / " + findings.length + "건 표시";
  }}
  bar.addEventListener("change", apply);
  document.getElementById("expand-all").onclick = function () {{ findings.forEach(function (f) {{ f.open = true; }}); }};
  document.getElementById("collapse-all").onclick = function () {{ findings.forEach(function (f) {{ f.open = false; }}); }};
  window.addEventListener("beforeprint", function () {{ findings.forEach(function (f) {{ f.open = true; }}); }});
  function openHash() {{
    if (!location.hash) return;
    var el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    var d = el && el.closest("details.finding");
    if (d) d.open = true;
  }}
  window.addEventListener("hashchange", openHash); openHash();
  apply();
}})();
</script>
<script>
  // mermaid 다이어그램(ERD·구성도)이 있으면 CDN 에서 로드해 렌더링한다. 오프라인이면 소스 텍스트가 그대로 보인다.
  if (document.querySelector('pre.mermaid')) {{
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';
    s.onload = function () {{ mermaid.initialize({{ startOnLoad: false, theme: 'neutral' }}); mermaid.run({{ querySelector: 'pre.mermaid' }}); }};
    document.body.appendChild(s);
  }}
</script>
</body>
</html>
"""


def build_severity_css() -> str:
    # "Critical" 등 심각도 단어를 색상 배지로 강조하는 CSS 클래스 생성
    rules = []
    for name, color in SEVERITY_COLORS.items():
        rules.append(f".sev-{name.lower()} {{ background: {color}; }}")
        rules.append(f".finding[data-sev={name}] {{ border-left-color: {color}; }}")
    return "\n  ".join(rules)


def build_code_css() -> str:
    # pygments가 있으면 구문 강조 CSS를 내장한다. 없으면 강조 없이 출력(에러 아님).
    try:
        from pygments.formatters import HtmlFormatter
    except Exception:
        return ""
    return HtmlFormatter(style="default").get_style_defs(".codehilite")


def apply_severity_badges(html: str) -> str:
    # 1) "<strong>심각도</strong>: Critical" 또는 "<strong>심각도</strong>: <code>Critical</code>"
    html = re.sub(
        rf"(심각도</strong>\s*:\s*)(?:<code>)?({SEVERITY_PATTERN})(?:</code>)?",
        lambda m: f'{m.group(1)}<span class="sev sev-{m.group(2).lower()}">{m.group(2)}</span>',
        html,
    )
    # 2) 표 셀에 심각도 단어만 단독으로 들어간 경우 (심각도 분포표, 로드맵표)
    html = re.sub(
        rf"<td>\s*(?:<strong>|<code>)?({SEVERITY_PATTERN})(?:</strong>|</code>)?\s*</td>",
        lambda m: f'<td><span class="sev sev-{m.group(1).lower()}">{m.group(1)}</span></td>',
        html,
    )
    return html


FINDING_H3 = re.compile(r'<h3 id="([^"]*)">\[(F-\d+)\]\s*(.*?)</h3>', re.S)
BLOCK_END = re.compile(r"<h[23]\b|<hr\s*/?>")


def wrap_findings(html: str) -> str:
    """'### [F-001] 제목' 블록을 접이식 <details class="finding"> 으로 감싸고, 앞에 심각도 필터 바를 넣는다.
    항목 범위는 다음 <h2>/<h3>/<hr> 직전까지. 심각도는 항목 안의 첫 배지에서 읽는다."""
    heads = list(FINDING_H3.finditer(html))
    if not heads:
        return html
    out, pos, counts = [], 0, {}
    for h in heads:
        out.append(html[pos:h.start()])
        nxt = BLOCK_END.search(html, h.end())
        end = nxt.start() if nxt else len(html)
        block = html[h.start():end]
        sev_m = re.search(r'class="sev sev-[a-z]+">([A-Za-z]+)<', block)
        sev = sev_m.group(1) if sev_m else "Info"
        counts[sev] = counts.get(sev, 0) + 1
        title = re.sub(r"<[^>]+>", "", h.group(3))
        out.append(
            f'<details class="finding" data-sev="{sev}" open>'
            f'<summary><span class="sev sev-{sev.lower()}">{sev}</span>'
            f'<span class="fid">{h.group(2)}</span><span>{title}</span></summary>'
            f'<div class="body">{block}</div></details>'
        )
        pos = end
    out.append(html[pos:])
    html = "".join(out)

    boxes = "".join(
        f'<label><input type="checkbox" value="{s}" checked>'
        f'<span class="sev sev-{s.lower()}">{s}</span> {counts[s]}</label>'
        for s in SEVERITY_COLORS if counts.get(s)
    )
    bar = (f'<div class="filterbar" id="filterbar"><b>필터</b> {boxes}'
           f'<button type="button" id="expand-all">모두 펼치기</button>'
           f'<button type="button" id="collapse-all">모두 접기</button>'
           f'<span class="cnt" id="filter-count"></span></div>')
    first = html.find('<details class="finding"')
    return html[:first] + bar + html[first:]


def extract_title(md_text: str, fallback: str) -> str:
    # 첫 번째 H1 제목을 HTML <title>로 사용한다.
    m = re.search(r"^#\s+(.+?)\s*$", md_text, flags=re.MULTILINE)
    return m.group(1).strip() if m else fallback


def md_to_html(md_text: str, fallback_title: str) -> str:
    try:
        import markdown  # 지연 임포트로 미설치 시 친절한 에러 제공
    except ImportError:
        sys.exit("[build_report] 'markdown' 패키지가 필요합니다. "
                 "설치: python -m pip install markdown")

    # 표/코드펜스/목차/구문강조 확장 기능 활성화
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists", "codehilite"],
        extension_configs={
            "toc": {"toc_depth": "2-3"},
            "codehilite": {"guess_lang": False, "css_class": "codehilite"},
        },
    )
    body = wrap_findings(apply_severity_badges(md.convert(md_text)))

    toc_html = ""
    toc_body = getattr(md, "toc", "") or ""
    if "<li>" in toc_body:
        toc_html = f'<details class="toc" open><summary>목차</summary>{toc_body}</details>'

    generated = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    return HTML_TEMPLATE.format(
        title=extract_title(md_text, fallback_title),
        toc=toc_html,
        content=body,
        severity_css=build_severity_css(),
        code_css=build_code_css(),
        generated=generated,
    )


def try_make_pdf(html_text: str, pdf_path: str) -> None:
    # --pdf 옵션을 줬을 때만 호출. weasyprint가 없으면 조용히 안내만 한다(에러 아님).
    try:
        from weasyprint import HTML
    except Exception:
        print("[build_report] (참고) PDF는 건너뜁니다. weasyprint가 설치돼 있지 않습니다. "
              "PDF가 필요하면 생성된 HTML에서 Ctrl+P로 저장하세요.")
        return
    try:
        HTML(string=html_text).write_pdf(pdf_path)
        print(f"[build_report] PDF 생성: {pdf_path}")
    except Exception as exc:
        print(f"[build_report] (참고) PDF 생성에 실패했습니다: {exc}. "
              "HTML에서 Ctrl+P로 저장하세요.")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("사용법: python tools/build_report.py <레포트.md> [--pdf]")

    want_pdf = "--pdf" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        sys.exit("사용법: python tools/build_report.py <레포트.md> [--pdf]")

    md_path = paths[0]
    if not os.path.isfile(md_path):
        sys.exit(f"[build_report] 파일을 찾을 수 없습니다: {md_path}")

    base, _ = os.path.splitext(md_path)
    html_path = base + ".html"

    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()

    html_text = md_to_html(md_text, os.path.basename(base))

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"[build_report] HTML 생성: {html_path}")

    if want_pdf:
        try_make_pdf(html_text, base + ".pdf")
    else:
        print("[build_report] PDF가 필요하면 HTML을 브라우저로 열고 Ctrl+P로 저장하세요. "
              "(또는 --pdf 옵션 + weasyprint 설치)")


if __name__ == "__main__":
    main()
