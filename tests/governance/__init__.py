"""auto-merge epic 的長期有效驗收測試（CI 跑，spec §4）。

本套件與子模組不寫 __pycache__：`grep -rl`／`grep -rn` 的完成條件（plan §2 red-gov 第 2 點）
會連 .pyc 一起掃，留下位元組碼會讓常數字串多出一筆命中。
"""
import sys

sys.dont_write_bytecode = True
