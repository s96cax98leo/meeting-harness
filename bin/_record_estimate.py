#!/usr/bin/env python3
"""_record_estimate.py --minutes <N> [--human]

錄製 N 分鐘需要的峰值磁碟空間（bytes），spec §3.7、design.md §5 Q7：
  ceil(N × (4 × 56,000,000 ＋ 1,920,000)) ＋ 2,000,000,000
4 倍＝段落 1 份＋正規化段落約 1.5 份＋串接輸出約 1.5 份；1.92 MB／分是 16 kHz 單聲道 wav；
2 GB 是錄製中「可用空間 < 2 GB 就優雅停止」的底線。單位一律十進位（1 MB＝10^6 bytes）。

meeting.sh doctor 與 record.sh（--min-free-bytes）共用這支，不各自另算。
N 不是正數 → 結束碼 2。
"""
import argparse
import math
import sys
from decimal import Decimal, InvalidOperation

PER_MINUTE = 4 * 56_000_000 + 1_920_000
FLOOR = 2_000_000_000


def estimate(minutes: Decimal) -> int:
    return math.ceil(minutes * PER_MINUTE) + FLOOR


def main(argv=None):
    ap = argparse.ArgumentParser(description="錄製需要的峰值磁碟空間（bytes）")
    ap.add_argument("--minutes", required=True)
    ap.add_argument("--human", action="store_true", help="另印「約 X.X GB」")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        n = Decimal(a.minutes)
    except InvalidOperation:
        n = None
    if n is None or not n.is_finite() or n <= 0:
        print(f"✗ --minutes 要是正數：{a.minutes}", file=sys.stderr)
        return 2
    b = estimate(n)
    print(b)
    if a.human:
        print(f"約 {b / 1e9:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
