#!/usr/bin/env bash
# failing_ffmpeg.sh —— MH_FFMPEG 的替身：一律失敗，用來製造「finalize 失敗」（record finish 應回 5）。
echo "failing_ffmpeg.sh：模擬 ffmpeg 失敗" >&2
exit 1
