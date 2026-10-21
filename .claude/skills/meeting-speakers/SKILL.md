---
name: meeting-speakers
description: 講者識別：把錄音切成「誰在什麼時候說話」（pyannote community-1，跑 Apple Silicon GPU），並用跨會議聲紋庫自動把 SPEAKER_01 對成真名。當需要 誰說了什麼 / 講者分離 / diarization / 認人 / 聲紋 時使用。
---

# meeting-speakers（講者分離＋聲紋庫）

`MH=/Users/yuktang/Documents/Agent/meeting-harness`

## 分離
```bash
bash "$MH/bin/meeting.sh" diarize "<場次目錄>"     # 場次＝底下有 錄音/ 的資料夾
```
引擎：**pyannote/speaker-diarization-community-1**（pyannote.audio 4）跑 **torch MPS**。
華語會議基準 AISHELL-4 DER 11.7%；本機實測 50–60 分鐘音檔約 80–90 秒。

首次需要：`bash "$MH/bin/setup-diarize.sh"`，並到
<https://huggingface.co/pyannote/speaker-diarization-community-1> 按一次 Agree（免費）。
`meeting.sh doctor` 會告訴你環境、裝置與授權狀態。

產物：`錄音/diarization.json`（講者時間段）、`錄音/transcript.speakers.md`（逐字稿加上講者標籤）。
語者向量**不再落場次資料夾**：`diarize.sh` 把它寫進 `mktemp` 的暫存檔，聲紋比對完（含失敗）就刪。

舊場次（meeting-speed 之前跑的）可能還留著 `錄音/embeddings.json`：`voiceprint add` 會只讀它建檔；
建完聲紋、確定不再需要後手動刪掉 `rm "<場次>/錄音/embeddings.json"`（屬生物特徵資料，清掉比較安全；之後要建檔會從音檔重算）。

### 講者數
由會議型態決定（`錄音/meeting.json`）：一對一／訪談鎖 2 人；內部／客戶 2–8；工作坊 3–12；研討會 1–6。
**出席名單只當上限提示，不要拿去鎖死人數**——實測硬鎖反而讓逐秒一致率從 94.1% 掉到 80.0%
（錄音常是多段串接，名單上的人不一定都開口）。
碎片講者（10 秒上下）由 `MH_MIN_SPEAKER_SEC` 折疊進最近的主要講者。

## 認人的三層順序
1. **聲紋庫比對**（自動，跑在分離之後）——命中就直接是名字。
2. **對話線索**——「Kevin 你這邊…」「請 Ricky 說明」、自我介紹、主持/收尾行為。
   在 harness 專案內可派 `speaker-id-agent`。
3. 都不確定 → 維持 `SPEAKER_0x`，寫進總結的「存疑」。**寧可匿名也不掛錯名字。**

`錄音/speakers.map.json` 格式（兩種都吃）：
```json
{"SPEAKER_01": {"name": "Kevin", "confidence": 0.92, "apply": true, "evidence": "多次被直呼 Kevin 並主持議程"}}
{"SPEAKER_00": "講者", "SPEAKER_01": "提問者A"}
```
`apply` 決定要不要真的改名；沒有這個欄位就看 `confidence ≥ 0.7`；**dict 沒有 `confidence` 視為未確認、不改名**
（手填 dict 請帶 `confidence` 或 `apply`，或直接寫字串）。
聲紋比對不會覆蓋人工填的對應：字串值、或 `evidence` 不以「聲紋庫比對」開頭的 dict 一律保留；
只有上一次聲紋比對寫的 dict 會被信心更高的新結果取代。

改完要重跑合併，再跑 annotate（在講者逐字稿插註記行與「（聽不清）」，冪等；和 `meeting.sh diarize` 的最後一步相同）：
```bash
python3 "$MH/bin/_merge_speakers.py" "<場次>/錄音/transcript.segments.json" \
        "<場次>/錄音/diarization.json" "<場次>/錄音/transcript.speakers.md" \
        "<場次>/錄音/speakers.map.json"
python3 "$MH/bin/_render.py" "<場次>" --annotate-speakers
```

## 聲紋庫（跨會議記住同一個人）
```bash
bash "$MH/bin/meeting.sh" voiceprint add "<場次>" SPEAKER_01 Kevin   # 只有人工確認過的才建檔
bash "$MH/bin/meeting.sh" voiceprint list
bash "$MH/bin/meeting.sh" voiceprint match "<場次>"                   # 手動重跑比對
bash "$MH/bin/meeting.sh" voiceprint remove Kevin
```
- 比對用的向量取自分離當下 pipeline 的 `return_embeddings`（暫存檔，比對完即刪）。
- `voiceprint add` 的向量來源依序：舊場次的 `錄音/embeddings.json`（只讀）→ 沒有就用分離環境從音檔重算該講者
  （`_diarize_pyannote.py --embed-speaker`，結果寫暫存檔、建檔後刪除）；分離環境不在時回 2，先跑 `bash "$MH/bin/setup-diarize.sh"`。
  同一人多場會累積平均。
- 門檻：**cos ≥0.75 才改名**；0.60–0.75 只寫成線索（`apply:false`）；<0.60 不寫。
- 實測跨 15 天 12 場會議，同一人 cos 0.79–1.00 全數認出，未建檔者維持匿名沒有亂配。
- **不要自動建檔**——把猜錯的名字寫進聲紋庫會長期汙染後面每一場。
- 聲紋屬生物特徵資料：只存 `$MH/vault/voiceprints/`（本機、不進版控），可隨時 remove。

## 歸屬的判準
逐字段要歸給某位講者，需「重疊 ≥30%」**或**「重疊 ≥0.6 秒」（`MH_MIN_OVERLAP_RATIO` /
`MH_MIN_OVERLAP_SEC` 可調）。兩條都要的原因：whisper 常把前後靜音併進同一段
（9 秒的段實際只講 2 秒），只看比例會冤枉它。證據不足就標 `SPEAKER_?`，不硬塞給最近的講者。
