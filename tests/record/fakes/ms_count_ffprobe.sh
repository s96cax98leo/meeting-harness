#!/usr/bin/env bash
# ms_count_ffprobe.sh —— MH_FFPROBE 的計數替身（meeting-speed spec §4.4.7）：每次呼叫在 MS_FFPROBE_LOG 附加一行
# （參數以 \x1f 分隔），再交給真的 ffprobe（MS_REAL_FFPROBE；沒設時取 PATH 上第一個不是本檔的 ffprobe）。
set -uo pipefail
[[ -n "${MS_FFPROBE_LOG:-}" ]] && printf '%s\n' "$(printf '%s\x1f' "$@")" >> "${MS_FFPROBE_LOG}"
real="${MS_REAL_FFPROBE:-}"
if [[ -z "${real}" ]]; then
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  IFS=: read -r -a dirs <<< "${PATH}"
  for d in "${dirs[@]}"; do
    if [[ -x "${d}/ffprobe" && "${d}/ffprobe" != "${self}" ]]; then real="${d}/ffprobe"; break; fi
  done
fi
exec "${real:-ffprobe}" "$@"
