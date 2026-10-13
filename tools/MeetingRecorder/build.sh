#!/usr/bin/env bash
# build.sh —— 把 Sources/**/*.swift 編成 ~/Applications/MeetingRecorder.app
#
# 為什麼一定要包成 .app 而不是裸執行檔：TCC（隱私權授權）的 responsible process
# 判定。裸執行檔從 shell exec 出來時，權限常被歸到終端機，等於要把整個終端機開
# 螢幕錄製權限，而且失敗模式是「靜默錄到全靜音/黑畫面」。包成 .app 並用 open 啟動，
# 權限就永遠記在這個 bundle id 底下。
#
# 簽章（design §9.1；spec §4.2.8、§6 第 13 條）：
#   - 固定身分以 SHA-1 判斷與簽章。身分「MeetingHarness Dev」與私鑰成對但不受信任
#     （CSSMERR_TP_NOT_TRUSTED），find-identity 加了只列有效身分的旗標就看不到它、會誤退回 ad-hoc；
#     不受信任不影響簽章，所以判斷時不加那個旗標，直接比對 SHA-1。
#   - 固定身分：--options runtime（hardened runtime）＋ --entitlements（麥克風、Apple Events 兩項）。
#     hardened runtime 下沒有這兩項 entitlement，麥克風與查 Chrome 分頁會靜默失敗。
#   - 沒有固定身分才退回 ad-hoc（同樣帶 --entitlements，不帶 runtime）；ad-hoc 每次重建 cdhash
#     都會變，可能出現「系統設定裡明明打勾卻取不到內容」，所以只當過渡。
#
# 環境變數：MH_RECORDER_DEST（輸出目錄，預設 ~/Applications；驗收一律指向暫存目錄，
#           不覆蓋已授權的 app，覆蓋會換 cdhash、TCC 授權要重給）
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="MeetingRecorder"
DEST="${MH_RECORDER_DEST:-$HOME/Applications}"
APP="${DEST}/${APP_NAME}.app"
IDENTITY_SHA1="5E249F84A9EC2F2D2B3914120906DF29FB4DF348"   # 鑰匙圈「MeetingHarness Dev」
ENTITLEMENTS="${HERE}/Resources/MeetingRecorder.entitlements"
TARGET="arm64-apple-macosx15.0"   # 鎖 15.0 而不是 26：換機或降級還能跑

command -v swiftc >/dev/null || { echo "✗ 找不到 swiftc（需要 Xcode 或 Command Line Tools）" >&2; exit 2; }
[[ -f "${ENTITLEMENTS}" ]] || { echo "✗ 找不到 ${ENTITLEMENTS}" >&2; exit 2; }

# Sources/ 底下全部的 .swift（main.swift、Core/、Capture/、Trigger/）
SOURCES=()
while IFS= read -r f; do SOURCES+=("$f"); done < <(find "${HERE}/Sources" -name '*.swift' -type f | LC_ALL=C sort)
[[ "${#SOURCES[@]}" -gt 0 ]] || { echo "✗ Sources/ 沒有任何 .swift" >&2; exit 2; }

echo "== 編譯（${#SOURCES[@]} 個檔）=="
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"
swiftc -O -target "${TARGET}" \
  -o "${APP}/Contents/MacOS/${APP_NAME}" \
  "${SOURCES[@]}" || { echo "✗ 編譯失敗" >&2; exit 3; }

cp "${HERE}/Resources/Info.plist" "${APP}/Contents/Info.plist"
printf 'APPL????' > "${APP}/Contents/PkgInfo"

echo "== 簽章 =="
if security find-identity -p codesigning 2>/dev/null | grep -qF "${IDENTITY_SHA1}"; then
  codesign --force --options runtime --entitlements "${ENTITLEMENTS}" --sign "${IDENTITY_SHA1}" "${APP}" \
    || { echo "✗ 簽章失敗" >&2; exit 4; }
  echo "✓ 用固定身分簽章：MeetingHarness Dev（${IDENTITY_SHA1}），hardened runtime"
else
  codesign --force --entitlements "${ENTITLEMENTS}" --sign - "${APP}" \
    || { echo "✗ 簽章失敗" >&2; exit 4; }
  echo "⚠ 用 ad-hoc 簽章（每次重建指紋都會變）"
  cat <<'NOTE'

  建議建一張固定的自簽憑證，重建後比較不會掉授權：
    1) 開「鑰匙圈存取」→ 選單「鑰匙圈存取 → 憑證輔助程式 → 製作憑證…」
    2) 名稱填 MeetingHarness Dev，身分類型「自簽根憑證」，憑證類型「程式碼簽署」
    3) 建好後把 build.sh 的 IDENTITY_SHA1 換成新憑證的 SHA-1，重跑這支 build.sh
NOTE
fi

CDHASH="$(codesign -dvvv "${APP}" 2>&1 | grep -i '^CDHash=' | head -1 | cut -d= -f2)"
echo
echo "✓ 已安裝：${APP}"
echo "  CDHash：${CDHASH:-unknown}"
cat <<EOF

第一次使用要先授權（照順序做，少一步就會靜默失敗）：
  1) 在終端機跑一次： bash bin/meeting.sh record windows
     第一次會跳「螢幕錄製與系統音訊」授權視窗 → 按允許
     （有 Chrome 時另會跳「允許控制 Google Chrome」→ 選用，按允許才有 Chrome 會議分頁的 ★）
  2) 完全結束 MeetingRecorder，再跑一次 bash bin/meeting.sh record windows
     （授權對已經啟動的程式不生效，這是 Apple 官方 sample 明寫的要求）
  3) 跑 bash bin/meeting.sh record preflight --window <id>，13 項的 hard 項都要通過
     （第一次會跳麥克風授權 → 按允許；檢查時要對麥克風說一句話）

重建過（cdhash 變了）若擷取失敗：到系統設定 › 隱私權與安全性，重新勾選螢幕錄製與麥克風。

量測（第 0 階段的實驗）：
  bash "${HERE}/probe.sh" windows
  bash "${HERE}/probe.sh" <windowID> [秒數]
EOF
