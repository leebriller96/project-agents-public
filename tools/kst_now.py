#!/usr/bin/env python3
# kst_now.py — OS/로컬 시간대와 무관하게 KST 타임스탬프를 출력한다.
#   python tools/kst_now.py          → 2609211030      (파일명용 yyMMddHHmm)
#   python tools/kst_now.py --full   → 2026-09-21 10:30 (본문용)
import datetime, sys
KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")
now = datetime.datetime.now(KST)
print(now.strftime("%Y-%m-%d %H:%M") if "--full" in sys.argv else now.strftime("%y%m%d%H%M"))
