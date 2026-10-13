#!/usr/bin/env python3
"""_diarize_pyannote.py <wav_path> <out_json> — 在 diarize venv 內執行。

用 pyannote.audio 4 的 speaker-diarization-community-1 做講者分離，跑 Apple Silicon GPU（MPS）。
輸出格式與舊版（senko）相同，下游 _merge_speakers.py 不用改：
  {"segments":[{"start":float,"end":float,"speaker":"SPEAKER_00"}...], "numSpeakers":n, ...}

講者數控制（由 _profile.py 依會議型態決定，透過環境變數傳入）：
  MH_NUM_SPEAKERS=2     已知人數就鎖死（一對一、有出席名單的客戶會議）
  MH_MIN_SPEAKERS=2     不知道人數時給範圍
  MH_MAX_SPEAKERS=8
裝置：
  MH_DIARIZE_DEVICE=auto|mps|cpu（預設 auto＝有 MPS 就用）
聲紋：
  MH_EMBEDDINGS_OUT=<path>  另存每位講者的語者向量（給聲紋庫比對／建檔用）

為什麼用 exclusive_speaker_diarization 當主體：它已經把重疊講話解開，
一個時間點只會屬於一位講者，跟逐字稿段落對齊時不會一段話被兩個人搶。
原始（含重疊）的結果仍會統計進 meta，供品質判讀。
"""
import os, sys, json, time

def _env_int(k):
    v = os.environ.get(k, "").strip()
    try:
        return int(v) if v else None
    except ValueError:
        return None

def pick_device():
    import torch
    want = os.environ.get("MH_DIARIZE_DEVICE", "auto").strip().lower()
    if want == "cpu":
        return torch.device("cpu")
    if want == "mps" or want == "auto":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if want == "mps":
            print("[diarize] 要求 mps 但此機器不可用 → 改用 cpu", file=sys.stderr)
    return torch.device("cpu")

def hf_token():
    """依序找 token：環境變數 → 本機檔案 → huggingface 官方快取（hf auth login）。"""
    for k in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    for p in ("~/.meeting-harness/hf-token", "~/.cache/huggingface/token", "~/.huggingface/token"):
        fp = os.path.expanduser(p)
        if os.path.isfile(fp):
            v = open(fp, encoding="utf-8").read().strip()
            if v:
                return v
    return None

GATED_HINT = (
    "pyannote 的模型是 gated（免費、按一下就通過）：\n"
    "  1. 開 https://huggingface.co/pyannote/speaker-diarization-community-1 按 Agree and access repository\n"
    "  2. 確認本機有 token：hf auth whoami（或把 read token 存到 ~/.meeting-harness/hf-token）"
)

def load_wav(path):
    """讀 16-bit PCM wav → pyannote 要的 {"waveform": [1,N] float32 tensor, "sample_rate": sr}。"""
    import wave, numpy as np, torch
    with wave.open(path, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise RuntimeError(f"只支援 16-bit PCM wav（這個是 {sw*8}-bit）")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return {"waveform": torch.from_numpy(x).unsqueeze(0), "sample_rate": sr}

def main():
    if len(sys.argv) < 3:
        print("usage: _diarize_pyannote.py <wav> <out.json>", file=sys.stderr); sys.exit(2)
    wav, out = sys.argv[1], sys.argv[2]

    # MPS 有少數 op 未實作，沒有這個 fallback 會直接崩
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as e:
        print(json.dumps({"error": f"diarize venv 未就緒：{e}",
                          "hint": "bash bin/setup-diarize.sh"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)

    token = hf_token()
    if not token:
        print(json.dumps({"error": "找不到 HuggingFace token", "hint": GATED_HINT},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(4)

    model = os.environ.get("MH_DIARIZE_MODEL", "pyannote/speaker-diarization-community-1")
    t0 = time.time()
    try:
        pipeline = Pipeline.from_pretrained(model, token=token)
    except Exception as e:
        msg = str(e)
        err = {"error": f"載入 {model} 失敗：{msg[:200]}"}
        if "restricted" in msg or "gated" in msg or "401" in msg or "403" in msg:
            err["hint"] = GATED_HINT
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        sys.exit(5)
    if pipeline is None:
        print(json.dumps({"error": f"{model} 回傳 None（多半是條款未接受）", "hint": GATED_HINT},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(5)

    device = pick_device()
    pipeline.to(device)
    load_s = time.time() - t0

    kwargs = {}
    n = _env_int("MH_NUM_SPEAKERS")
    if n and n > 0:
        kwargs["num_speakers"] = n
    else:
        lo, hi = _env_int("MH_MIN_SPEAKERS"), _env_int("MH_MAX_SPEAKERS")
        if lo: kwargs["min_speakers"] = lo
        if hi: kwargs["max_speakers"] = hi

    # 自己讀 wav 餵 tensor，不走 pyannote 內建的檔案解碼（torchcodec）。
    # 理由：torchcodec 要對得上系統 FFmpeg 的版本，對不上就整包載入失敗
    # （實測 macOS + ffmpeg 7.1 會 "Could not load libtorchcodec_core*.dylib"）。
    # 我們的輸入本來就是 diarize.sh 產的 16k mono wav，用標準庫讀最穩。
    audio = load_wav(wav)

    print(f"[diarize] pyannote {model} on {device}　{kwargs or '（講者數自動判定）'}", file=sys.stderr)
    t1 = time.time()
    want_emb = bool(os.environ.get("MH_EMBEDDINGS_OUT"))
    try:
        result = pipeline(audio, return_embeddings=want_emb, **kwargs)
    except TypeError:
        # 某些版本沒有 return_embeddings，退回不要向量
        want_emb = False
        result = pipeline(audio, **kwargs)
    infer_s = time.time() - t1

    # pyannote 4：return_embeddings=True 時回的是完整 output 物件，向量在 .speaker_embeddings
    # （不是 tuple）。舊版才是 (annotation, embeddings)。兩種都接。
    embeddings = None
    if want_emb:
        if isinstance(result, tuple):
            result, embeddings = result
        else:
            embeddings = getattr(result, "speaker_embeddings", None)

    # pyannote 4 回傳物件帶 speaker_diarization / exclusive_speaker_diarization；
    # 舊版直接回 Annotation。兩種都接。
    ann = getattr(result, "exclusive_speaker_diarization", None) or \
          getattr(result, "speaker_diarization", None) or result
    overlapped = getattr(result, "speaker_diarization", None)

    def to_segs(annotation):
        out = []
        for turn, _, spk in annotation.itertracks(yield_label=True):
            out.append({"start": float(turn.start), "end": float(turn.end), "speaker": str(spk)})
        out.sort(key=lambda x: x["start"])
        return out

    segs = to_segs(ann)
    # 含重疊的版本另外留著：exclusive 版對短插話（「對」「嗯」）比較保守，
    # 合併逐字稿時若 exclusive 判不出來，可以退到這一份再試（見 _merge_speakers.py）。
    segs_all = to_segs(overlapped) if (overlapped is not None and overlapped is not ann) else []

    # 標籤正規化成 SPEAKER_00 / 01 …（依首次出現時間排序，跨引擎維持同一種命名）
    order, mapping = [], {}
    for s in segs:
        if s["speaker"] not in mapping:
            mapping[s["speaker"]] = f"SPEAKER_{len(order):02d}"
            order.append(s["speaker"])
    for s in segs:
        s["speaker"] = mapping[s["speaker"]]
    for s in segs_all:
        if s["speaker"] not in mapping:          # 只出現在重疊版的講者也要有編號
            mapping[s["speaker"]] = f"SPEAKER_{len(order):02d}"
            order.append(s["speaker"])
        s["speaker"] = mapping[s["speaker"]]

    if not segs:
        print(json.dumps({"error": "沒有偵測到任何語音段落",
                          "hint": "確認音檔有人聲；或改用 MH_DIARIZE_DEVICE=cpu 再試一次"},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(6)

    n_overlap = 0
    if overlapped is not None and overlapped is not ann:
        try:
            n_overlap = len(list(overlapped.get_overlap()))
        except Exception:
            n_overlap = 0

    meta = {
        "engine": "pyannote",
        "model": model,
        "device": str(device),
        "loadSeconds": round(load_s, 1),
        "inferSeconds": round(infer_s, 1),
        "overlapRegions": n_overlap,
        "params": {k: v for k, v in kwargs.items()},
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"segments": segs, "segmentsOverlapped": segs_all,
                   "numSpeakers": len(mapping), "meta": meta},
                  f, ensure_ascii=False, indent=2)

    # 語者向量（聲紋庫用）：pyannote 回的是 (n_speakers, dim)，列順序＝原始標籤順序
    emb_path = os.environ.get("MH_EMBEDDINGS_OUT")
    if emb_path and embeddings is not None:
        try:
            # pyannote 的 centroid 列順序＝它自己的標籤排序（SPEAKER_00, 01, …），
            # 不是我們依出現時間重編的順序，所以要照它的標籤名排序來對。
            vecs = {}
            for i, raw_label in enumerate(sorted(mapping.keys())):
                if i < len(embeddings):
                    v = embeddings[i]
                    if v is None:
                        continue
                    vecs[mapping[raw_label]] = [float(x) for x in v]
            json.dump({"model": model, "dim": len(next(iter(vecs.values()))) if vecs else 0,
                       "speakers": vecs},
                      open(emb_path, "w", encoding="utf-8"), ensure_ascii=False)
            meta["embeddings"] = emb_path
        except Exception as e:
            print(f"[diarize] 語者向量輸出失敗（不影響分離結果）：{e}", file=sys.stderr)

    print(json.dumps({"status": "ok", "segments": len(segs), "numSpeakers": len(mapping),
                      "meta": meta}, ensure_ascii=False))

if __name__ == "__main__":
    main()
