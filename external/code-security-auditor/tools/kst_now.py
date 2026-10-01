#!/usr/bin/env python3
# kst_now.py — 운영체제/로컬 시간대와 무관하게 한국시각(KST, UTC+9)을 출력한다.
#
# 사용법:
#   python tools/kst_now.py          # 레포트 파일명 접두어용: yymmddHHMM  (예: 2606291651)
#   python tools/kst_now.py --full   # 레포트 본문용:        YYYY-MM-DD HH:MM
#
# `TZ=Asia/Seoul date` 는 PowerShell에서 동작하지 않고, `Get-Date` 는 로컬 시간대를 쓰므로
# KST를 보장하지 않는다. 이 스크립트 하나로 모든 OS에서 동일한 값을 얻는다.

import datetime
import sys

KST = datetime.timezone(datetime.timedelta(hours=9))


def main():
    now = datetime.datetime.now(KST)
    if "--full" in sys.argv[1:]:
        print(now.strftime("%Y-%m-%d %H:%M"))
    else:
        print(now.strftime("%y%m%d%H%M"))


if __name__ == "__main__":
    main()
