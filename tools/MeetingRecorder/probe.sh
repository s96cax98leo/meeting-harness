#!/usr/bin/env bash
# probe.sh —— 第 0 階段的實驗跑台
#
# 回答一個問題：用 ScreenCaptureKit 的單視窗擷取（SCContentFilter(desktopIndependentWindow:)），
# 切換 Space 時會不會黑畫面。
#
# 官方（WWDC22 Session 10155）說單視窗 filter 是 display and space independent，唯一會暫停的
# 是視窗被最小化。但社群記載部分 Chromium/Electron app（Teams 就是）在非作用中 Space 會停止
# 重繪，這時 SCFrameStatus 仍可能回 complete，只有看像素才分得出來。
#
# 一律用 open 啟動 .app，不直接 exec 裡面的二進位：TCC 的責任程序才會是這個 app，
# 而不是終端機。代價是 stdout 沒有去處，所以結果走 --log 檔案，這支腳本幫你 tail。
#
# 用法：
#   bash probe.sh windows                        列出視窗與 windowID
#   bash probe.sh <windowID> [秒數] [情境標籤]    對該視窗量測（預設 30 秒）
set -uo pipefail

APP_NAME="MeetingRecorder"
APP="${MH_RECORDER_APP:-$HOME/Applications/${APP_NAME}.app}"
OUTDIR="${MH_PROBE_DIR:-$HOME/.meeting-harness/probe}"

[[ -d "${APP}" ]] || { echo "✗ 找不到 ${APP}，先跑 bash build.sh" >&2; exit 2; }
mkdir -p "${OUTDIR}"

quit_app() { osascript -e "quit app \"${APP_NAME}\"" >/dev/null 2>&1 || true; }

# 等 log 出現並持續印，直到 app 結束
follow() {
  local logf="$1"
  local waited=0
  while [[ ! -s "${logf}" ]]; do
    sleep 0.3
    waited=$((waited + 1))
    if [[ "${waited}" -gt 60 ]]; then
      echo "✗ 20 秒都沒有任何輸出。最可能的原因是螢幕錄製權限沒給或授權後沒重啟 app。" >&2
      echo "  open \"x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture\"" >&2
      return 4
    fi
  done
  tail -f "${logf}" &
  local tailpid=$!
  while pgrep -x "${APP_NAME}" >/dev/null 2>&1; do sleep 0.5; done
  sleep 0.5
  kill "${tailpid}" 2>/dev/null || true
  wait "${tailpid}" 2>/dev/null || true
  return 0
}

if [[ "${1:-}" == "windows" || -z "${1:-}" ]]; then
  logf="${OUTDIR}/windows.txt"
  : > "${logf}"
  quit_app
  open -n -a "${APP}" --args windows --log "${logf}"
  follow "${logf}"
  rc=$?
  echo
  echo "挑一個 windowID，然後： bash probe.sh <windowID> [秒數] [情境標籤]"
  exit "${rc}"
fi

WID="$1"
SECONDS_ARG="${2:-30}"
LABEL="${3:-scenario}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BASE="${OUTDIR}/${STAMP}-w${WID}-${LABEL}"

cat <<EOF
== probe ==
視窗 ID：${WID}
時長　：${SECONDS_ARG} 秒
log　 ：${BASE}.log
影片　：${BASE}.mov（供人眼覆核）

六個情境，每個單獨跑一次（口述時間點，log 的 t= 對得上）：
  1 前景同一個 Space          ← 先跑這個當基線
  2 切到另一個 Space（視窗留在原 Space、不要最小化）  ← 核心問題
  3 讓那個 app 進 native 全螢幕，然後切到別的 Space
  4 同 Space 內被另一個 app 全螢幕遮住
  5 把視窗最小化到 Dock       ← 官方承認會暫停，應該看到 suspended
  6 打開 Mission Control

重要：受測的會議 app 要真的在通話中或畫面有動靜。靜態視窗會合法地回 idle，
那樣就分不出「app 停止重繪」與「畫面本來就沒變」。

EOF

quit_app
open -n -a "${APP}" --args probe --window "${WID}" --seconds "${SECONDS_ARG}" \
  --log "${BASE}.log" --mov "${BASE}.mov"
follow "${BASE}.log"
rc=$?

if [[ -s "${BASE}.mov" ]]; then
  echo
  echo "覆核影片： open \"${BASE}.mov\""
fi
exit "${rc}"
