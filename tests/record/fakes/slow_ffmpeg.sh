#!/usr/bin/env bash
# slow_ffmpeg.sh —— MH_FFMPEG 的慢速替身：呼叫真的 ffmpeg 前後各睡 SLOW_FFMPEG_SECONDS 秒（預設 1），
# 讓測試能在 finalize 進行中插入 meeting.sh status（spec §4.6.5、§4.7.2）。
set -uo pipefail
real="${SLOW_FFMPEG_REAL:-$(command -v ffmpeg)}"
sleep "${SLOW_FFMPEG_SECONDS:-1}"
"${real}" "$@"
rc=$?
sleep "${SLOW_FFMPEG_SECONDS:-1}"
exit "${rc}"
