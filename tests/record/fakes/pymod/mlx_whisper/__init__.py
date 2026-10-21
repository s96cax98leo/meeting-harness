"""mlx_whisper 套件的替身（meeting-speed spec §4.11.6）：放在 PYTHONPATH 最前面，攔截 `import mlx_whisper`。

- 匯入時在 FAKE_PYMOD_LOG（未設就不記）附加一行 {"event": "import", "pid": …}。
- transcribe(audio, path_or_hf_repo=…, **kw)：第一次遇到某個模型時記一筆 {"event": "load", "model": …}（模擬載入模型），
  每次呼叫記一筆 {"event": "transcribe", "pid", "model", "seconds", "call"}；不載入任何真的模型。
- 回固定段落：一段，涵蓋整個輸入（0 到輸入長度），文字「範例增量第 N 窗」（N＝本程序內第幾次呼叫）。
  輸入是路徑時以 wave 讀長度（非 wav 時以 FAKE_PYMOD_SECONDS 或 1.0 秒計）；是陣列時以 len ÷ 16000 計。
- 回傳與 mlx_whisper.transcribe() 相同的鍵：text、segments（id、start、end、text）、language。
"""
import json
import os
import wave

_LOADED = set()
_CALLS = [0]


def _log(rec):
    p = os.environ.get("FAKE_PYMOD_LOG")
    if p:
        rec = dict(rec, pid=os.getpid())
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


_log({"event": "import"})


def _seconds(audio):
    if isinstance(audio, (str, os.PathLike)):
        try:
            with wave.open(os.fspath(audio), "rb") as w:
                return w.getnframes() / float(w.getframerate() or 16000)
        except (wave.Error, OSError, EOFError):
            return float(os.environ.get("FAKE_PYMOD_SECONDS", "1.0") or 1.0)
    try:
        return len(audio) / 16000.0
    except TypeError:
        return float(os.environ.get("FAKE_PYMOD_SECONDS", "1.0") or 1.0)


def transcribe(audio, path_or_hf_repo="mlx-community/whisper-tiny", **kw):
    model = str(path_or_hf_repo)
    if model not in _LOADED:
        _LOADED.add(model)
        _log({"event": "load", "model": model})
    _CALLS[0] += 1
    n = _CALLS[0]
    dur = round(_seconds(audio), 3)
    _log({"event": "transcribe", "model": model, "seconds": dur, "call": n,
          "language": kw.get("language"), "initial_prompt": kw.get("initial_prompt")})
    text = f"範例增量第{n}窗"
    return {"text": text, "language": kw.get("language") or "zh",
            "segments": [{"id": 0, "seek": 0, "start": 0.0, "end": dur, "text": text}]}
