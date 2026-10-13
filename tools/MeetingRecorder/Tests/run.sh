#!/bin/bash
# MeetingRecorder Core 單元測試執行器（spec §3.4、§4.15；plan.md §2 t2）。
# 把 ../Sources/Core/*.swift、本目錄的 *Tests.swift 與 main.swift 編成一支執行檔並執行。
# 可從任何目錄執行；必須在 macOS 內建 /bin/bash 3.2.57 下可跑。
# 紅燈階段 Sources/Core/ 不存在時，swiftc 應報「cannot find '…' in scope」（缺符號），
# 不得是「no such file」或「unbound variable」。
set -euo pipefail
cd "$(dirname "$0")"
shopt -s nullglob
core=(../Sources/Core/*.swift)
out="${TMPDIR:-/tmp}/mr-tests.$$"
trap 'rm -f "$out"' EXIT
# bash 3.2 在 set -u 下展開空陣列 "${core[@]}" 會報 unbound variable 並結束，swiftc 根本不會執行；
# 所以用 ${core[@]+"${core[@]}"}：空陣列展開成零個參數。
swiftc -target arm64-apple-macosx15.0 ${core[@]+"${core[@]}"} *Tests.swift main.swift -o "$out"
"$out" "$@"
