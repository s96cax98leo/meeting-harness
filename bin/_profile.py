#!/usr/bin/env python3
"""_profile.py <場次目錄> [--json|--shell|--set-type <type>]

決定一個場次的「會議型態 profile」，並輸出該型態對應的參數。

來源優先序：
  1. 錄音/meeting.json 的 "type"
  2. 舊標記檔（相容）：錄音/.meeting → internal、錄音/.diarize → 只開分離不改型態
  3. 預設 seminar

meeting.json 範例（欄位都可省略）：
  { "type": "client",
    "attendees": [{"name":"Kevin","org":"某客戶","role":"PM"}],
    "expectedSpeakers": 4,
    "language": "zh",
    "llm": "claude" }

型態對應（diarize 一律開；差別在分離參數與總結模板）：
  seminar   研討會/演講（1 對多＋Q&A）   講者數 1–6、折疊 <30s 零星講者
  internal  內部會議（多對多）           有名單就鎖人數，否則 2–8
  client    客戶會議（多對多、對外）      有名單就鎖人數，否則 2–8
  1on1      一對一                       鎖 2 人
  workshop  工作坊（多組、講者多且雜）      3–12、不折疊
  interview 訪談／面談                   鎖 2 人
"""
import sys, os, json, shlex

# min/max_spk 是給 pyannote 的講者數範圍；fixed 是「真的只可能是這個數字」才填。
#
# 為什麼不拿出席名單去鎖 num_speakers：實測（0907 某客戶會議，4 人已人工確認）
# 自動判定的逐秒一致率 94.1%，硬鎖 4 人反而掉到 80.0%——因為錄音常是多段串接、
# 名單上的人不一定都開口、也可能有名單外的人插話。名單改當「上限提示」比較安全。
#
# min_speaker_sec：總時長低於此秒數的講者會併入最近的主要講者（在 _merge_speakers.py）。
# pyannote 偶爾會切出 10 秒上下的碎片講者（實測 0907 多出 12 秒與 6 秒兩個），這道用來收掉。
PROFILES = {
    "seminar":   {"diarize": 1, "min_spk": 1, "max_spk": 6,  "fixed": None, "min_speaker_sec": 30, "template": "seminar"},
    "internal":  {"diarize": 1, "min_spk": 2, "max_spk": 8,  "fixed": None, "min_speaker_sec": 20, "template": "notes"},
    "client":    {"diarize": 1, "min_spk": 2, "max_spk": 8,  "fixed": None, "min_speaker_sec": 20, "template": "client"},
    "1on1":      {"diarize": 1, "min_spk": 2, "max_spk": 2,  "fixed": 2,    "min_speaker_sec": 60, "template": "notes"},
    "workshop":  {"diarize": 1, "min_spk": 3, "max_spk": 12, "fixed": None, "min_speaker_sec": 15, "template": "workshop"},
    "interview": {"diarize": 1, "min_spk": 2, "max_spk": 2,  "fixed": 2,    "min_speaker_sec": 0,  "template": "interview"},
}
DEFAULT_TYPE = "seminar"

def meeting_json_path(sess):
    return os.path.join(sess, "錄音", "meeting.json")

def harness_config(section):
    """讀 repo 根的 config.json 的某一段（讀不到回 {}）；環境變數仍優先於這裡的值。"""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get(section)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def load(sess):
    """回傳 (meta, profile)。meta 是 meeting.json 內容（含相容推斷的 type）。"""
    meta = {}
    p = meeting_json_path(sess)
    if os.path.isfile(p):
        try:
            meta = json.load(open(p, encoding="utf-8")) or {}
        except Exception as e:
            print(f"[profile] meeting.json 解析失敗（忽略）：{e}", file=sys.stderr)
            meta = {}
    rec = os.path.join(sess, "錄音")
    if not meta.get("type"):
        # 舊標記檔相容
        if os.path.exists(os.path.join(rec, ".meeting")):
            meta["type"] = "internal"
        else:
            meta["type"] = DEFAULT_TYPE
    t = meta["type"]
    prof = dict(PROFILES.get(t, PROFILES[DEFAULT_TYPE]))
    if t not in PROFILES:
        print(f"[profile] 未知型態 {t}，改用 {DEFAULT_TYPE}", file=sys.stderr)
        meta["type"] = DEFAULT_TYPE
    # 舊 .diarize 標記：強制開分離（型態不變）
    if os.path.exists(os.path.join(rec, ".diarize")):
        prof["diarize"] = 1
    # config.json 的 diarize.enabled=false：整個關掉（.diarize 標記也不開）；MH_DIARIZE=1 仍可單次強制開
    if harness_config("diarize").get("enabled") is False:
        prof["diarize"] = 0
    if os.environ.get("MH_DIARIZE") == "1":
        prof["diarize"] = 1
    # 出席名單只當「上限提示」：把 max 收到名單人數 +1（容許名單外的插話），min 不動。
    # 只有型態本身就固定人數的（一對一／訪談）才真的鎖 num_speakers。
    n = meta.get("expectedSpeakers") or (len(meta["attendees"]) if isinstance(meta.get("attendees"), list) and meta.get("attendees") else 0)
    if n:
        prof["max_spk"] = max(int(prof["min_spk"]), int(n) + 1)
    prof["num_spk"] = prof.get("fixed")
    prof["language"] = meta.get("language", "zh")
    prof["llm"] = os.environ.get("MH_LLM") or meta.get("llm", "claude")
    return meta, prof

def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr); sys.exit(2)
    sess = os.path.abspath(sys.argv[1])
    args = sys.argv[2:]

    if "--set-type" in args:
        t = args[args.index("--set-type") + 1]
        if t not in PROFILES:
            print(f"[profile] 未知型態：{t}（可用：{', '.join(PROFILES)}）", file=sys.stderr); sys.exit(2)
        p = meeting_json_path(sess)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        meta = {}
        if os.path.isfile(p):
            try: meta = json.load(open(p, encoding="utf-8")) or {}
            except Exception: meta = {}
        meta["type"] = t
        json.dump(meta, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[profile] {os.path.basename(sess)} → type={t}")
        return

    meta, prof = load(sess)
    if "--json" in args:
        print(json.dumps({"meta": meta, "profile": prof}, ensure_ascii=False, indent=2))
        return
    # 預設 shell 形式，供 bash `eval` 使用：每個值一律 shlex.quote（meeting.json 是可編輯的，
    # language／llm 等欄位不得注入指令，ultrareview）
    def sh(v):
        return shlex.quote("" if v is None else str(v))
    print(f'MH_TYPE={sh(meta["type"])}')
    print(f'MH_TEMPLATE={sh(prof["template"])}')
    print(f'MH_DO_DIARIZE={sh(prof["diarize"])}')
    print(f'MH_NUM_SPEAKERS={sh(prof["num_spk"])}')
    print(f'MH_MIN_SPEAKERS={sh(prof["min_spk"])}')
    print(f'MH_MAX_SPEAKERS={sh(prof["max_spk"])}')
    print(f'MH_MIN_SPEAKER_SEC={sh(os.environ.get("MH_MIN_SPEAKER_SEC") or prof["min_speaker_sec"])}')
    print(f'MH_LANG={sh(prof["language"])}')
    print(f'MH_LLM_BACKEND={sh(prof["llm"])}')

if __name__ == "__main__":
    main()
