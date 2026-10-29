#!/usr/bin/env bash
# _lint.sh — 專案用的小型 shell 檢查（CJK 字串裡最容易踩的兩個坑）
#
# 1) $VAR 後面直接接全形字元：bash 會把全形字當成變數名的一部分 → unbound variable。
#    必須寫成 ${VAR}。這個坑已經造成過「轉錄產出空白稿卻回報成功」。
# 2) 雙引號字串裡的反引號：會被當成命令替換執行。中文說明常想用 `錄音/` 標示路徑，
#    要改用「」。
set -uo pipefail
BIN="$(cd "$(dirname "$0")" && pwd)"
fail=0

# 第 1 項用 python 比對：macOS 內建的 BSD grep 沒有 -P，以前會靜默略過這項檢查。
fullwidth_after_var() {
  python3 - "$1" <<'PY'
import re, sys
pat = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]")
hit = False
with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
    for n, line in enumerate(fh, 1):
        if pat.search(line):
            print(f"    {n}:{line.rstrip()}")
            hit = True
sys.exit(1 if hit else 0)
PY
}

for f in "$BIN"/*.sh; do
  bash -n "$f" || { echo "✗ 語法錯誤：${f}"; fail=1; }
  if ! hits="$(fullwidth_after_var "$f")"; then
    echo "✗ ${f}：\$VAR 後面接全形字元，要改 \${VAR}"
    printf '%s\n' "$hits"
    fail=1
  fi
  if grep -n '^[^#]*"[^"]*`[^`]*`[^"]*"' "$f" >/dev/null 2>&1; then
    echo "⚠ ${f}：雙引號字串內有反引號（會被當命令執行），確認是否該改成「」"
    grep -n '^[^#]*"[^"]*`[^`]*`[^"]*"' "$f" | sed 's/^/    /'
    fail=1
  fi
done

for f in "$BIN"/*.py; do
  python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$f" || { echo "✗ 語法錯誤：${f}"; fail=1; }
done

python3 -c "import json;json.load(open('$BIN/../config.json'))" || { echo "✗ config.json 不是合法 JSON"; fail=1; }

[[ "$fail" -eq 0 ]] && echo "✓ lint 通過（$(ls "$BIN"/*.sh "$BIN"/*.py | wc -l | tr -d ' ') 個檔）"
exit "$fail"
