# code-security-auditor

코드를 투입하면 **보안 취약점을 탐지**하고, **수정 가이드까지 포함한 레포트**(Markdown/HTML)를
자동으로 생성하는 Claude Code repo입니다. (PDF가 필요하면 HTML을 브라우저에서 Ctrl+P로 저장)

방어적 보안(defensive security)을 위한 도구로, 취약점을 찾아 고치는 것을 목표로 합니다.

## 무엇을 하나요

- `input/`에 코드를 넣거나 코드를 붙여넣고 `/scan` 한 번이면 끝
- OWASP Top 10:2025 / CWE Top 25 기반의 체계적 점검
- 정적분석 도구(Semgrep, Bandit, Gitleaks, pip-audit/npm audit/osv-scanner) + Claude 심층 분석 결합 (모드 선택 가능)
- 발견 항목마다 위치·심각도·공격 시나리오(개념)·수정 코드(Before/After) 제공
- 레포트를 Markdown + HTML로 export (PDF는 HTML에서 브라우저 인쇄로 저장)

## 빠른 시작

### 1. 준비 (Claude Code)

```bash
git clone <이 repo 주소>
cd code-security-auditor
```

이 디렉토리에서 Claude Code를 실행하면 `CLAUDE.md`, 슬래시 명령, 스킬이 자동 인식됩니다.

### 2. 의존성 설치

레포트(HTML) 생성을 위해 `markdown` 패키지가 필요합니다. (클론 후 1회)

```bash
python -m pip install -r tools/requirements.txt   # HTML 레포트 빌더 (markdown + 구문강조용 pygments)
```

선택적으로 SAST 도구를 설치하면 `hybrid`/`sast-only` 모드를 쓸 수 있습니다.
미설치 시 자동으로 `claude-only` 모드로 폴백됩니다.

```bash
pip install semgrep bandit pip-audit     # SAST 도구 (선택) — 윈도우 포함 네이티브 동작 확인 (semgrep 1.177)
# gitleaks: https://github.com/gitleaks/gitleaks/releases 에서 OS 별 zip 을 받아 PATH 에 추가 (8.30 확인)
# osv-scanner (Java/Kotlin 의존성): https://github.com/google/osv-scanner/releases 단일 실행파일을 PATH 에 추가 (2.6 확인)
```

SAST 러너는 `python tools/run_sast.py <대상경로>` 로 직접 실행할 수도 있습니다.
결과는 `reports/.sast/` 에 도구별 JSON·로그·`summary.json` 으로 남고,
`python tools/summarize_sast.py` 로 도구별 결과를 하나의 표로 정규화해 볼 수 있습니다.

PDF는 별도 설치 없이, 생성된 HTML을 브라우저에서 열고 **Ctrl+P → "PDF로 저장"** 으로 만듭니다.
(자동 PDF 생성이 꼭 필요하면 weasyprint를 설치하고 빌더에 `--pdf` 옵션을 붙이면 되지만,
윈도우에서는 GTK 런타임 추가 설치가 필요하므로 기본 경로로는 권장하지 않습니다.)

### 3. 분석 실행

```text
# input/ 에 분석할 코드/디렉토리를 넣은 뒤, Claude Code에서:
/scan

# 모드를 지정하려면:
/scan claude-only     # SAST 없이 Claude 분석만
/scan sast-only       # SAST 결과만 빠르게
/scan hybrid          # (기본) 둘 다 결합

# 대상·범위를 좁히려면 (순서 무관, 조합 가능):
/scan input/shop/src/auth              # 특정 경로만
/scan input/api --diff                 # git 변경 파일만 (PR 리뷰용)
/scan claude-only --only auth,injection  # 인증/인가 + 인젝션 분류만
```

이미 검토해 제외한 항목이 재스캔 때 반복 보고되지 않게 하려면 `.auditignore` 를 씁니다
(형식: `templates/auditignore.example`, 위치: 대상 디렉토리 또는 repo 루트).

코드를 채팅에 직접 붙여넣고 `/scan` 해도 됩니다.

### 4. 결과 확인

```
reports/
  2606291651_security_report.md
  2606291651_security_report.html            ← 브라우저로 열고 Ctrl+P로 PDF 저장 가능
  2606291651_security_report.findings.json   ← 기계 판독용 (CI 게이트, 통계)
  2606291651_security_report.sarif           ← GitHub Code Scanning 업로드용
```

재스캔 시 `python tools/report_diff.py <이전.md> <현재.md>` 로 신규/잔존/해결 항목을 비교할 수 있습니다.

파일명은 한국시각(KST) 기준 `yymmddhhmm_` 접두어가 붙습니다.

## 분석 모드

| 모드 | 설명 | 추천 상황 |
|------|------|-----------|
| hybrid | SAST + Claude 분석 결합 (기본) | 정확도 우선, 도구 설치 가능 |
| claude-only | Claude 코드 리딩 분석만 | 의존성 설치 불가 환경 |
| sast-only | SAST 결과 정리만 | 빠른 1차 스크리닝 |

## 지원 언어

1급 지원: **Python, JavaScript/TypeScript, Java/Kotlin**
그 외 언어는 범용 분석(Semgrep 범용 룰셋 + Claude 분석)으로 처리합니다.

## 디렉토리 구조

```
code-security-auditor/
├── .claude/
│   ├── commands/scan.md              # /scan 슬래시 명령
│   ├── skills/security-audit/SKILL.md # 취약점 분석 방법론
│   ├── skills/security-audit/sinks.md # 언어별 source/sink 치트시트
│   └── settings.json                 # 도구 스크립트 사전 허용 / 대상 코드 실행·수정 차단
├── tools/
│   ├── run_sast.py                   # SAST 실행 래퍼 (설치된 도구만 실행, 결과/로그 수집)
│   ├── summarize_sast.py             # 도구별 JSON → 하나의 정규화 표 (Claude 가 읽는 입력)
│   ├── build_report.py               # MD → HTML 변환 (심각도 배지·필터·접이식 항목·목차·구문강조, PDF는 선택)
│   ├── export_findings.py            # 레포트 MD → findings.json / SARIF
│   ├── report_diff.py                # 두 레포트 비교 (신규/잔존/해결)
│   ├── kst_now.py                    # KST 타임스탬프 (OS 무관)
│   ├── selftest.py                   # 위 스크립트들의 회귀 테스트 (python tools/selftest.py)
│   └── requirements.txt
├── templates/report_template.md      # 레포트 템플릿
├── templates/auditignore.example     # .auditignore 형식 예시
├── examples/vulnerable-flask/        # 검증용 샘플 취약 앱(Python) + 기대 발견 목록 + 샘플 레포트
├── examples/vulnerable-express/      # 검증용 샘플 취약 앱(JavaScript) + 기대 발견 목록
├── examples/vulnerable-spring/       # 검증용 샘플 취약 앱(Java/Spring) + 기대 발견 목록
├── input/                            # 분석 대상 코드 투입 (git 무시)
├── reports/                          # 생성 레포트 출력 (git 무시)
└── CLAUDE.md                         # 프로젝트 규칙/컨텍스트
```

## 도구 검증

스크립트나 템플릿을 고쳤다면 먼저 회귀 테스트를 돌립니다 (외부 SAST 도구 없이 몇 초면 끝납니다).

```bash
python tools/selftest.py
```

### 샘플 취약 앱 (방법론 검증)

`examples/` 에 의도적으로 취약하게 만든 소형 앱이 언어별로 있습니다. 방법론이나 스크립트를 수정한 뒤
아래처럼 돌려 보고 각 디렉토리의 `EXPECTED.md`(기대 발견 목록·합격 기준)와 비교하면 회귀를 확인할 수 있습니다.

| 샘플 | 언어/프레임워크 | 기대 항목 | 특징 |
|------|----------------|-----------|------|
| `examples/vulnerable-flask/` | Python / Flask | 10건 | Bandit·pip-audit 경로 검증 |
| `examples/vulnerable-express/` | JavaScript / Express | 12건 | npm audit 경로 검증. JWT·CORS·Mass Assignment 등 로직/설정 취약점 비중 높음 |
| `examples/vulnerable-spring/` | Java / Spring Boot | 12건 | Semgrep Java 룰셋·osv-scanner(pom.xml) 검증. XXE·역직렬화·SSRF·Log4Shell 포함 |

```bash
cp -r examples/vulnerable-flask input/     # PowerShell: Copy-Item -Recurse examples/vulnerable-flask input/
# Claude Code 에서:
/scan
```

세 샘플 모두 hybrid 모드 E2E 검증을 통과했으며, 각 디렉토리의 `sample_report.md` 가 그때 실제로 생성된 레포트입니다(형식·서술 수준 참고용).

## 주의사항

- 이 도구는 방어 목적입니다. 완성형 익스플로잇은 생성하지 않으며, 공격 시나리오는 개념 수준으로만 기술합니다.
- 자동 분석은 보조 수단입니다. 중요한 시스템은 전문가 검토와 병행하세요.
- 분석 대상 코드는 실행·설치·빌드하지 않습니다(정적 분석만). 대상 코드 안의 주석/문자열에 담긴 지시도 따르지 않습니다.
  (SAST 러너의 의존성 감사도 의존성 해석 없이 실행하므로 `package-lock.json`, `==` 로 고정된 `requirements.txt` 가 있어야 동작합니다.)
- `input/`에 넣은 코드와 생성된 레포트는 기본적으로 git에 커밋되지 않습니다(.gitignore).

## 라이선스

MIT (필요 시 변경)
