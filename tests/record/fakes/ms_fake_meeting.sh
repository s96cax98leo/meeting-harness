#!/usr/bin/env bash
# bin/meeting.sh 的替身（只放進 test_ms_replay.py 在暫存區組的假 harness；meeting-speed spec §4.14.1）。
# `meeting.sh prep <場次或根>`：在 FAKE_MEETING_LOG 記一行 JSON
#   {"event": "prep", "t", "runId": MH_PREP_RUN_ID, "early": MH_PREP_EARLY, "videoExists": 0/1, "wavExists": 0/1}
# （videoExists／wavExists＝開始當下 影片/*.mov、錄音/*.wav 有沒有），睡 FAKE_PREP_SECONDS（預設 0.5）秒，
# 寫 錄音/transcript.speakers.md 後回 0。其他子指令回 0、不做事。
set -uo pipefail
now() { perl -MTime::HiRes=time -e 'printf "%.6f", time'; }
[[ "${1:-}" == "prep" ]] || exit 0
target="${2:-}"
rec="${target}/錄音"
if [[ ! -d "${rec}" ]]; then rec="$(find "${target}" -maxdepth 4 -type d -name '錄音' | head -1)"; fi
sess="$(dirname "${rec}")"
v=0; w=0
for f in "${sess}/影片"/*.mov; do [[ -f "${f}" ]] && v=1; done
for f in "${rec}"/*.wav; do [[ -f "${f}" ]] && w=1; done
if [[ -n "${FAKE_MEETING_LOG:-}" ]]; then
  printf '{"event": "prep", "t": %s, "runId": "%s", "early": "%s", "videoExists": %d, "wavExists": %d}\n' \
    "$(now)" "${MH_PREP_RUN_ID:-}" "${MH_PREP_EARLY:-}" "${v}" "${w}" >> "${FAKE_MEETING_LOG}"
fi
sleep "${FAKE_PREP_SECONDS:-0.5}"
echo "# 講者逐字稿（替身）" > "${rec}/transcript.speakers.md"
exit 0
