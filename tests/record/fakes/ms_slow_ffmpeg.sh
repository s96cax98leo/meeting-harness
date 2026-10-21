#!/usr/bin/env bash
# ms_slow_ffmpeg.sh —— MH_FFMPEG 的替身（meeting-speed spec §4.2.1、§4.2.5、§4.4.10、§4.5.1、§4.5.3）：
# 記錄每次呼叫的順序與分類，可讓某一類步驟變慢或失敗，其餘交給真的 ffmpeg。
#
# 分類（以參數判斷，依序取第一個成立的）：
#   verify ：含相鄰的「-f null」（解碼驗證）
#   video  ：含 -c:v、-f concat、[v]、h264_videotoolbox 或 libx264（影片步驟：copy remux、normalize、concat）
#   audio  ：其他（抽音訊、混音、PCM）
# 環境變數：
#   MS_FFMPEG_LOG         紀錄檔；每次呼叫兩行：「<秒> START <分類> <wav> <參數以 \x1f 分隔>」與「<秒> END <分類> <rc>」，
#                         <wav>＝呼叫當下 MS_FFMPEG_WATCH 目錄第一層有沒有 .wav（1／0；沒設 WATCH 時為 -）
#   MS_FFMPEG_WATCH       要觀察的目錄（通常是 <場次>/錄音）
#   MS_FFMPEG_SLOW_ON     逗號分隔的分類（verify、video、audio、all），呼叫真的 ffmpeg 前先睡 MS_FFMPEG_SLOW_SECONDS（預設 1）秒
#   MS_FFMPEG_FAIL_ON     逗號分隔：verify、video、audio、videotoolbox（含 h264_videotoolbox 的呼叫）、libx264；成立就不呼叫
#                         真的 ffmpeg、印一行錯誤、回 1
#   MS_REAL_FFMPEG        真的 ffmpeg 路徑（沒設時取 PATH 上第一個不是本檔的 ffmpeg）
set -uo pipefail
now() { perl -MTime::HiRes=time -e 'printf "%.6f", time'; }
args=("$@")
joined="$(printf '%s\x1f' "$@")"
cls=audio
prev=""
for a in "$@"; do
  if [[ "${prev}" == "-f" && "${a}" == "null" ]]; then cls=verify; break; fi
  prev="${a}"
done
if [[ "${cls}" != verify ]]; then
  prev=""
  for a in "$@"; do
    case "${a}" in
      -c:v|h264_videotoolbox|libx264|*"[v]"*) cls=video ;;
      concat) [[ "${prev}" == "-f" ]] && cls=video ;;
    esac
    prev="${a}"
  done
fi
wav="-"
if [[ -n "${MS_FFMPEG_WATCH:-}" ]]; then
  wav=0
  for f in "${MS_FFMPEG_WATCH}"/*.wav; do [[ -f "${f}" ]] && wav=1 && break; done
fi
log="${MS_FFMPEG_LOG:-}"
[[ -n "${log}" ]] && printf '%s START %s %s %s\n' "$(now)" "${cls}" "${wav}" "${joined}" >> "${log}"
hit() { # <清單> <分類>
  local IFS=,
  local x
  for x in $1; do
    [[ "${x}" == all || "${x}" == "$2" ]] && return 0
    [[ "${x}" == videotoolbox && "${joined}" == *h264_videotoolbox* ]] && return 0
    [[ "${x}" == libx264 && "${joined}" == *libx264* ]] && return 0
  done
  return 1
}
if hit "${MS_FFMPEG_FAIL_ON:-}" "${cls}"; then
  echo "ms_slow_ffmpeg.sh：模擬 ${cls} 步驟失敗" >&2
  [[ -n "${log}" ]] && printf '%s END %s 1\n' "$(now)" "${cls}" >> "${log}"
  exit 1
fi
if hit "${MS_FFMPEG_SLOW_ON:-}" "${cls}"; then
  sleep "${MS_FFMPEG_SLOW_SECONDS:-1}"
fi
real="${MS_REAL_FFMPEG:-}"
if [[ -z "${real}" ]]; then
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  IFS=: read -r -a dirs <<< "${PATH}"
  for d in "${dirs[@]}"; do
    if [[ -x "${d}/ffmpeg" && "${d}/ffmpeg" != "${self}" ]]; then real="${d}/ffmpeg"; break; fi
  done
fi
"${real:-ffmpeg}" "${args[@]}"
rc=$?
[[ -n "${log}" ]] && printf '%s END %s %s\n' "$(now)" "${cls}" "${rc}" >> "${log}"
exit "${rc}"
