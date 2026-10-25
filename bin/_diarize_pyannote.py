#!/usr/bin/env python3
"""_diarize_pyannote.py <wav_path> <out_json> — 在 diarize venv 內執行。
   _diarize_pyannote.py --embed-speaker <音檔> <diarization.json> <SPEAKER_xx> <out.json>
       只算一位講者的語者向量（聲紋建檔用；_voiceprint.py add 在沒有現成向量時呼叫，輸出到暫存檔）。

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
  MH_EMBEDDINGS_OUT=<path>  另存每位講者的語者向量（給聲紋庫比對用）。diarize.sh 一律指到 mktemp 的暫存檔，
                            比對完就刪，不落場次資料夾（meeting-speed spec §4.6.1）。

為什麼用 exclusive_speaker_diarization 當主體：它已經把重疊講話解開，
一個時間點只會屬於一位講者，跟逐字稿段落對齊時不會一段話被兩個人搶。
原始（含重疊）的結果仍會統計進 meta，供品質判讀。
"""
import os, sys, json, time, subprocess, tempfile, wave


def harness_config(section):
    """讀 repo 根的 config.json 的某一段（讀不到回 {}）；環境變數仍優先於這裡的值。"""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get(section)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}

def _env_int(k):
    v = os.environ.get(k, "").strip()
    try:
        return int(v) if v else None
    except ValueError:
        return None

def pick_device():
    import torch
    want = str(os.environ.get("MH_DIARIZE_DEVICE") or harness_config("diarize").get("device", "auto")).strip().lower()
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

def load_pipeline():
    """載入 pyannote pipeline 並搬到裝置；失敗時印錯誤並以 3（venv）／4（token）／5（授權、載入）結束。
    回 (pipeline, model, device, 載入秒數)。"""
    # MPS 有少數 op 未實作，沒有這個 fallback 會直接崩
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    try:
        import torch  # noqa: F401  （pick_device 用；先 import 才能把缺套件歸到 exit 3）
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
    return pipeline, model, device, time.time() - t0


def is_16k_mono_wav(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
    except Exception:
        return False


# --embed-speaker：每段最短 0.5 秒（太短的向量不穩）、長段切成 10 秒窗、總長最多取 300 秒（最長的段優先）
EMBED_MIN_SEC, EMBED_WINDOW_SEC, EMBED_MAX_TOTAL_SEC = 0.5, 10.0, 300.0


def embed_speaker(args):
    """--embed-speaker <音檔> <diarization.json> <SPEAKER_xx> <out.json>：
    取該講者在 diarization.json 的段落，逐窗算語者向量後依時長加權平均，寫 <out.json>：
    {"model", "dim", "speaker", "vector", "speakers": {SPEAKER_xx: vector}}。
    與分離當下 pipeline 的 centroid 不會位元相同（同模型、同時段，差異應很小；spec §7 疑慮 6）。
    結束碼：0 完成、2 參數錯、3／4／5 同分離、6 該講者沒有可用段落。"""
    if len(args) < 4:
        print("usage: _diarize_pyannote.py --embed-speaker <音檔> <diarization.json> <SPEAKER_xx> <out.json>",
              file=sys.stderr)
        return 2
    src, diar_path, tag, out = args[:4]
    try:
        with open(diar_path, encoding="utf-8") as f:
            segs = [s for s in (json.load(f) or {}).get("segments", []) if s.get("speaker") == tag]
    except (OSError, ValueError) as e:
        print(json.dumps({"error": f"讀不到 {diar_path}：{e}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    spans = sorted(((float(s["start"]), float(s["end"])) for s in segs
                    if float(s["end"]) - float(s["start"]) >= EMBED_MIN_SEC), key=lambda x: x[0] - x[1])
    if not spans:
        print(json.dumps({"error": f"{tag} 在 diarization.json 沒有 ≥ {EMBED_MIN_SEC} 秒的段落"},
                         ensure_ascii=False), file=sys.stderr)
        return 6

    pipeline, model, device, _ = load_pipeline()
    embed = getattr(pipeline, "_embedding", None)
    if embed is None:
        print(json.dumps({"error": f"{model} 沒有可用的語者向量模型（pipeline._embedding）"}, ensure_ascii=False),
              file=sys.stderr)
        return 5

    tmp = None
    try:
        wav_path = src
        if not is_16k_mono_wav(src):
            fd, tmp = tempfile.mkstemp(prefix="mh-embed-", suffix=".wav")
            os.close(fd)
            r = subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp],
                               capture_output=True)
            if r.returncode != 0:
                print(json.dumps({"error": "ffmpeg 轉 16k mono wav 失敗"}, ensure_ascii=False), file=sys.stderr)
                return 5
            wav_path = tmp
        audio = load_wav(wav_path)
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass

    import numpy as np
    x, sr = audio["waveform"], audio["sample_rate"]
    total, acc, weight = 0.0, None, 0.0
    for st, en in spans:
        t = st
        while t < en and total < EMBED_MAX_TOTAL_SEC:
            e = min(en, t + EMBED_WINDOW_SEC)
            if e - t >= EMBED_MIN_SEC:
                chunk = x[:, int(t * sr):int(e * sr)]
                v = np.asarray(embed(chunk.unsqueeze(0).to(device)))[0]
                if np.all(np.isfinite(v)):
                    acc = v * (e - t) if acc is None else acc + v * (e - t)
                    weight += e - t
                    total += e - t
            t = e
        if total >= EMBED_MAX_TOTAL_SEC:
            break
    if acc is None or weight <= 0:
        print(json.dumps({"error": f"{tag} 算不出有效的語者向量"}, ensure_ascii=False), file=sys.stderr)
        return 6
    vec = [float(v) for v in acc / weight]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"model": model, "dim": len(vec), "speaker": tag, "vector": vec, "speakers": {tag: vec}},
                  f, ensure_ascii=False)
    print(json.dumps({"status": "ok", "speaker": tag, "dim": len(vec), "seconds": round(weight, 1)},
                     ensure_ascii=False))
    return 0


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--embed-speaker":
        sys.exit(embed_speaker(sys.argv[2:]))
    if len(sys.argv) < 3:
        print("usage: _diarize_pyannote.py <wav> <out.json>", file=sys.stderr); sys.exit(2)
    wav, out = sys.argv[1], sys.argv[2]

    pipeline, model, device, load_s = load_pipeline()

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

    # 語者向量（聲紋庫用）：pyannote 回的是 (n_speakers, dim)，列順序＝原始標籤順序。
    # 先寫向量、設好 meta["embeddings"]，再寫 diarization.json（spec §4.6.9；原本寫完才設，meta 永遠沒這個鍵）
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

    with open(out, "w", encoding="utf-8") as f:
        json.dump({"segments": segs, "segmentsOverlapped": segs_all,
                   "numSpeakers": len(mapping), "meta": meta},
                  f, ensure_ascii=False, indent=2)

    print(json.dumps({"status": "ok", "segments": len(segs), "numSpeakers": len(mapping),
                      "meta": meta}, ensure_ascii=False))

if __name__ == "__main__":
    main()
