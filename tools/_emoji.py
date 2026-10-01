# _emoji.py — 이모지(그림 문자) 판정. 외부 의존성 없음.
#
# 원칙(CLAUDE.md "이모지 금지"): 소스 주석·Mapper 쿼리 주석·yml 주석·DDL COMMENT·레포트·산출물·에이전트 지침 어디에도
# 이모지를 쓰지 않는다. quality.py(생성 소스), gate.py(레포트), selfcheck.py(이 저장소), hooks/guard.py(쓰기 시점)가
# 모두 이 모듈 하나로 판정해 기준이 어긋나지 않게 한다.
#
# 판정 범위: 유니코드 그림 문자 블록 전체와, 기본 표시가 이모지인 기호(체크·경고·별·삼각 재생 등).
# 제외(문서에 정상적으로 쓰는 기호): 화살표(→ ↔ ←), 수학 기호(≥ ≠ ≈), 괘선(─ │ ├), 가운뎃점(·), ©·®·™, 원문자(①).

import re

_RANGES = [
    (0x1F000, 0x1FAFF),   # 마작·카드·원문자 보충·그림 문자·이모티콘·교통·기호 보충·확장 A (국기 1F1E6-1F1FF 포함)
    (0x2600, 0x27BF),     # 기타 기호(U+2600 U+2611 U+26A0 U+2605 U+2665)·딩뱃(U+2705 U+2714 U+2716 U+274C U+27A1)
    (0x2B00, 0x2BFF),     # 기타 기호와 화살표(U+2B06 U+2B1B U+2B50 U+2B55)
    (0x231A, 0x231B), (0x2328, 0x2328), (0x23CF, 0x23CF), (0x23E9, 0x23F3), (0x23F8, 0x23FA),  # U+231A U+23E9 U+23F0 U+23F3
    (0x25AA, 0x25AB), (0x25B6, 0x25B6), (0x25C0, 0x25C0), (0x25FB, 0x25FE),  # U+25AA U+25B6 U+25C0 U+25FB
    (0x203C, 0x203C), (0x2049, 0x2049), (0x2139, 0x2139), (0x24C2, 0x24C2),  # U+203C U+2049 U+2139 U+24C2
    (0x2934, 0x2935), (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299),
    (0xFE0F, 0xFE0F),     # 이모지 표시 선택자(VS16) — 일반 기호를 이모지로 바꿔 그린다
    (0x20E3, 0x20E3),     # 키캡 결합 문자(예: 숫자 1 + U+FE0F + U+20E3)
    (0x200D, 0x200D),     # 이모지 결합용 ZWJ
    (0xE0020, 0xE007F),   # 태그 문자(지역 국기)
]

EMOJI_RE = re.compile("[" + "".join(
    (re.escape(chr(a)) if a == b else f"{re.escape(chr(a))}-{re.escape(chr(b))}") for a, b in _RANGES) + "]")


def find_emoji(text):
    """이모지가 있는 (줄 번호, 열 번호, 문자, 코드포인트) 목록. 줄·열은 1부터."""
    out = []
    for no, line in enumerate(text.split("\n"), 1):
        for m in EMOJI_RE.finditer(line):
            ch = m.group(0)
            out.append((no, m.start() + 1, ch, f"U+{ord(ch):04X}"))
    return out


def has_emoji(text):
    return EMOJI_RE.search(text) is not None
