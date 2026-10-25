# reencode-regress 證據：重編路徑每段 normalize 牆鐘（spec §4.4.14）

- 子任務：`reencode-regress`（Story G1；spec §4.4.14）
- 日期：2026-10-23；分支 `feature/meeting-speed--reencode-regress`（自 `feature/meeting-speed` `8fe98fb`）
- 機器：Apple M3 Max（16 核）、macOS 26.6；`/opt/homebrew/bin/ffmpeg` 7.1.1；Python `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`
- 範圍：只用合成段落（`ffmpeg -f lavfi testsrc2`／`tests/record/_media.py::make_segment`），**沒有**讀 `~/Documents` 底下任何真實會議資料、`~/.meeting-harness/`、`vault/`、`.env`；沒有啟動錄製器或選單 app。暫存檔都在暫存目錄，量完已刪。
- 比較的三個版本：
  - **042c404**：`git archive 042c404 bin`（R3 合併、10/20 基準時的版本）
  - **修正前 HEAD**：`git archive 8fe98fb bin`（本子任務開工時的 `feature/meeting-speed`）
  - **修正後 HEAD**：本分支的 `bin/`（見 §5：本子任務沒有改程式，`bin/` 與修正前 HEAD 相同）

## 1. 結論（先講）

1. **同一段、同一台機器、單段量測時，修正前 HEAD 的 normalize 沒有比 042c404 慢**：五種段落的中位數差在 −13%～+3% 之間（§3 表 1），全部在 §4.4.14 的 15% 內。平行度 3 同時跑 3 段時也一樣（表 2，修正前 HEAD 比 042c404 快約 2%）。
2. **§4.4.12 的 `TAIL_PAD_FPS_FLOOR=240` 不是根因**：把它關掉（`floor=0`，等同 042c404 的公式）只省 0.4～0.6 秒／段（約 2%），而且關掉後 link_fps 低報的段 `check_norm` 失敗（就是 §4.4.12 要修的缺陷）。多補的複製幀全被夾到 cap、由 `select` 丟掉，不進編碼器（§4.1）。
3. **`select` 去重不是負擔，反而是省時的那一步**：拿掉它（實驗）時 tail9 從 24.1 秒變 33.5 秒、tail50 從 22.7 秒變 77.6 秒——被丟掉的複製幀全都進了編碼器（§4.2）。
4. **濾鏡鏈與編碼參數在兩版之間沒有差異**：`normalize()` 與 `encode()`、`encoders()` 在 042c404 與修正前 HEAD 之間唯一的差異就是補幀數那一行（§2）。
5. **重放量測「每段約 48 秒、10/20 基準約 24 秒」不是同一段的比較**：每段的牆鐘由「輸出影格數 × 畫布像素」與 VideoToolbox 的吞吐決定（§4.3）；平行度 3 時每段牆鐘本來就是單段的約 2.6 倍。10/20 基準是另一場（121 段、吞吐約 8.2 秒／段），而 R3 合併後 `042c404` 版本跑的另一場（88 段）吞吐已是約 15.7 秒／段，與重放量測的 16.3 秒／段只差 4%（§4.4）。在本機可重現的條件下找不到程式上的 2 倍退化。
6. 因此**本子任務不改程式**（不動 §4.4.12 的公式，也就不需要 `needs_decision`）；修正後 HEAD 的中位數不比 042c404 慢超過 15%（表 1、表 2）。要在同一批真實段落上確認，見 §6 的衍生工作。

## 2. 程式差異（042c404 → 修正前 HEAD，重編路徑）

以 `ast` 抽出兩版同名函式逐一 diff：

| 函式 | 差異 |
|---|---|
| `normalize` | 只有補幀數：042c404 `n = int(math.ceil((cap - last) * fps)) + 1`（042c404 `bin/_record_finalize.py:1247`）→ 修正前 HEAD `n = int(math.ceil((cap - last) * max(fps, TAIL_PAD_FPS_FLOOR))) + 1`（`bin/_record_finalize.py:839`，常數在 `:99`） |
| `encode` | 只多 libx264 成功後 `note_x264_success()`（印訊息，不影響 videotoolbox 路徑） |
| `encoders` | 無（`h264_videotoolbox` high、`-bf 0`、每 2 秒強制關鍵幀，`bin/_record_finalize.py:589-597`） |
| `check_norm` | 原本跑 3 次 ffprobe 封包掃描，改成 `probe_packets` 一次共用（`bin/_record_finalize.py:754-797`）——只會更快 |
| `analyze`、`link_fps` | 無 |
| `probe` | 多 `-show_data_hash sha256`（只雜湊 extradata，表 1 的 analyze 都在 0.15 秒內） |

濾鏡鏈（`tpad` → `setpts` → `select` → `pad`，`bin/_record_finalize.py:840,863`）在兩版逐字相同（bench 印出的 `-filter_complex` 字串比對過，只差 `tpad` 的 `stop=` 數字）。

## 3. 量測

### 3.1 合成段落

| 名稱 | 內容 | 產生方式 |
|---|---|---|
| small | `tests/record` 的合成段落：320×240、60 fps、影片 3 秒、音訊 12 秒（`test_tail_pad_low_r_frame_rate` 同款） | `tests.record._media.make_segment(path, dur=12.0, vdur=3.0, fps=60)` |
| full60 | 2560×1440、60 fps、60 秒全動態（3600 幀），音訊 60 秒；不需補尾 | `ffmpeg -f lavfi -i testsrc2=s=2560x1440:r=60:d=60 -f lavfi -i sine=f=440:sample_rate=48000:d=60 -c:v h264_videotoolbox -b:v 12M -pix_fmt yuv420p -c:a aac -b:a 128k -ac 2 -f mov full60.mov` |
| tail9 | 同上，影片 51 秒、音訊 60 秒（末 9 秒靜止，§4.4.12 的情境） | 同上，`testsrc2` 的 `d=51` |
| tail50 | 同上，影片 10 秒、音訊 60 秒（末 50 秒靜止：螢幕分享畫面不動時 SCK 不出幀） | 同上，`testsrc2` 的 `d=10` |

三段 1440p 的 `r_frame_rate`、`avg_frame_rate` 都是 60/1、`time_base` 1/15360。「`r_frame_rate` 低於連結影格率」的情況照 `test_ms_video_copy.py::TAIL_PAD_PATCHED` 的做法，把模組的 `link_fps` 換成回 58（下表的「link58」）。

### 3.2 量法

`bench_norm.py`（附錄 A）以 `importlib` 載入指定版本的 `bin/_record_finalize.py`，對一段跑 `analyze()` 後量 `normalize()`（含 `encode()` 與 `check_norm()`）的牆鐘，`W×H`＝段落尺寸、碼率＝`MIN_BITRATE`。`run_bench.sh` 同一設定連跑 3 次取中位數。全部在 `caffeinate -i` 下依序跑（一次只跑一段，表 2 除外）。

量測期間機器上有其他子任務的測試與一個正在錄製的錄製器（非本子任務啟動），load average 在 4～9 之間浮動；每列後面附量完時的 1 分鐘 load。三次之間的離散都在 ±1 秒內（tail50 042c404 第 1 次 37.1 秒是外部負載尖峰，中位數不受影響）。

### 3.3 表 1：單段 normalize 牆鐘（秒，3 次與中位數）

| 段落 | 條件 | 042c404 | 修正前 HEAD | 修正後 HEAD | 修正後 ÷ 042c404 |
|---|---|---|---|---|---|
| small | 原樣 | 0.79／0.79／0.80 → **0.79** | 0.69／0.70／0.71 → **0.70** | 0.69／0.69／0.70 → **0.69** | 0.87 |
| full60 | 原樣（不補尾） | 24.24／24.40／24.66 → **24.40** | 25.22／24.57／25.07 → **25.07** | 24.65／24.43／24.67 → **24.65** | 1.01 |
| tail9 | 原樣（link 60） | 24.33／24.05／24.10 → **24.10** | 24.71／23.97／24.30 → **24.30** | 24.48／24.52／25.02 → **24.52** | 1.02 |
| tail50 | 原樣（link 60） | 37.06／23.15／22.91 → **23.15** | 22.78／23.26／22.76 → **22.78** | 22.79／22.64／22.65 → **22.65** | 0.98 |
| small | link58 | 0.74／0.73／0.73 → **0.73**（3 次都 `FinalizeError`） | 0.69／0.69／0.69 → **0.69** | 0.69／0.70／0.69 → **0.69** | 0.95 |
| tail9 | link58 | 23.94／24.02／24.26 → **24.02**（3 次都 `FinalizeError`） | 24.01／24.47／24.07 → **24.07** | 23.79／23.76／23.75 → **23.76** | 0.99 |
| tail50 | link58 | 22.14／22.14／22.12 → **22.14**（3 次都 `FinalizeError`） | 22.62／22.66／22.67 → **22.66** | 22.69／22.94／22.71 → **22.71** | 1.03 |

`FinalizeError`＝`check_norm` 的「正規化後補尾幀沒有可讀的封包」：042c404 依 58 fps 推算補幀數、ffmpeg 實際以 60 fps 補，複製幀用完時還沒到 cap（例：tail9 最後一幀 59.717，應在 59.995）——即 incident 2018 的缺陷，§4.4.12 修掉的就是它。時間照記（編碼已跑完才在 `check_norm` 失敗）。

### 3.4 表 2：平行度 3（同時 3 段 full60）

| 版本 | 3 段各自的牆鐘（秒） | 中位數 |
|---|---|---|
| 042c404 | 62.67／64.55／64.59 | 64.55 |
| 修正前 HEAD | 62.02／63.10／63.12 | 63.10 |

修正前 HEAD ÷ 042c404 ＝ 0.98。平行度 3 時每段牆鐘約為單段的 2.6 倍（吞吐 21.0～21.5 秒／段），兩版相同。

### 3.5 表 3：實驗對照（修正前 HEAD、link58，3 次中位數，秒）

| 段落 | 照 §4.4.12（floor 240） | 關掉 floor（`TAIL_PAD_FPS_FLOOR=0`，等同 042c404 公式） | 拿掉 `select` 去重 |
|---|---|---|---|
| small | 0.69（ok） | 0.68（`FinalizeError`） | 1.54 |
| tail9 | 24.07（ok） | 23.65（`FinalizeError`） | 33.51 |
| tail50 | 22.66（ok） | 22.02（`FinalizeError`） | 77.58 |

「拿掉 `select`」的實驗同時關掉 `check_norm`（只量時間，產物不合格）。

### 3.6 表 4：外部負載對單段的影響（full60，單次，秒）

| 版本 | 無額外負載 | 同時 12 個 `yes`（CPU） | 同時 mlx fp16 4096² 矩陣乘迴圈（GPU，3 次中位數） |
|---|---|---|---|
| 042c404 | 24.26 | 24.37 | 23.82（23.80／23.82／25.35） |
| 修正前 HEAD | 24.07 | 24.17 | 35.26（35.26／49.10／26.88；量時機器 load 升到 36，是其他子任務的負載尖峰，不是可比的數字） |

CPU、GPU 的額外負載都沒有讓單段明顯變慢（042c404 那列兩種負載都在 ±1 秒內）：單段 normalize 的瓶頸在 VideoToolbox 編碼器，不在 CPU 解碼或 GPU。

## 4. 根因分析

### 4.1 `TAIL_PAD_FPS_FLOOR=240` 為什麼幾乎不花時間

`tpad=stop_mode=clone:stop=n` 依**連結影格率**（這裡 60）的間隔出複製幀，`n` 只決定出幾張（`bin/_record_finalize.py:839-840`）。floor 240 讓 `n` 變成原本的 4 倍，但多出來的複製幀 PTS 都在 cap 之後，被 `setpts` 夾成 cap（`:846-847`），再被 `select` 的「pts > prev_selected_pts」丟掉（`:859-863`），根本不進 `pad` 與編碼器。真正進編碼器的複製幀數仍是 `(cap − last) × 60`，與 042c404 相同。多出來的只有 `tpad` 的參考計數複製與 `select` 的運算式求值：link58 時 tail50 多約 9100 張（12004 對 2902）、tail9 多約 1600 張（2164 對 524），實測各多 0.6、0.4 秒（表 3）。

### 4.2 `select` 去重為什麼是省時的

`select` 在 `pad` 與編碼器之前（`bin/_record_finalize.py:863`）。拿掉它，夾到 cap 的複製幀全部以同一個 PTS 進編碼器（`-fps_mode passthrough` 不丟），tail50 的編碼幀數從約 3600 變成約 12600，牆鐘從 22.7 秒變 77.6 秒（表 3）。所以去重不但不是退化來源，還是 floor 240 能幾乎零成本的前提。

### 4.3 每段牆鐘由什麼決定

- 表 1 的 tail50（影片只有 10 秒、600 張原始幀）仍要 22.7 秒：末 50 秒的靜止由複製幀以 60 fps 補滿，編碼器實際編的是約 3600 張 2560×1440，與 full60 幾乎一樣。也就是說**每段成本 ≈ 段長 × 連結影格率 × 畫布像素**，與畫面是否在動無關。
- 單段約 150 幀／秒；平行度 3 時總吞吐約 170 幀／秒（表 2：3 × 3600 ÷ 63 秒），VideoToolbox 已接近飽和，所以每段牆鐘被拉長到約 2.6 倍。
- 錄製器（`MeetingRecorder`）錄製中本身也用 VideoToolbox 編碼；收尾若與一場錄製同時跑，吞吐會再被分走（本次量測期間就有一個錄製器在跑，表 1 的數字已含這份干擾，兩版受同樣影響）。

### 4.4 重放量測的「2 倍」

| 來源 | 段數 | normalize 總長 | 吞吐（秒／段） | 平行度 3 時每段牆鐘 |
|---|---|---|---|---|
| 10/20 基準 A（R3 合併前；run 目錄 `baseline.md`） | 121 | 約 990 秒 | 約 8.2 | 約 24.5 |
| 基準 B（`042c404`；run 目錄 `baseline.md`，normalize 為推算） | 88 | 約 1380 秒 | 約 15.7 | 約 47 |
| 重放量測 2026-10-23（spec §4.4.14） | 141 | 2302 秒 | 約 16.3 | 約 49 |
| 本檔 full60 合成段落（全動態 1440p60） | 3（同時） | 約 63 秒 | 約 21 | 約 63 |

spec 引的「10/20 基準約 24 秒」是場次 A；重放的是另一場。同樣是 `042c404` 的場次 B 已經是約 47 秒／段，與重放量測只差 4%。`baseline.md` 第 34 行當時也記下「normalize 的單段耗時不只跟段數有關，可能跟畫布大小或來源碼率有關」。依 §4.3，畫布越大、段越長，每段越慢；A 與重放場次的畫布、段長不同，數字不能直接相除。

結論：**在「同一段、同一台機器」的條件下沒有可重現的程式退化**；「每段 48 秒對 24 秒」比的是不同場次（畫布與段長不同），且平行度 3 下 VideoToolbox 飽和。

## 5. 修正

不改程式。理由：

- 表 1、表 2 的修正前 HEAD 已在 042c404 的 +3% 內（§4.4.14 要求 ≤ +15%）；
- 唯一能省時的改動是關掉 floor（約 2%），但那等於放寬 §4.4.12、讓 link_fps 低報的段 `check_norm` 失敗，spec 明文禁止自行放寬；
- 把 `tpad` 改用時間（`stop_duration`）而不是張數，也只能省同樣的約 2%，而且是改 §4.4.12 的公式本身，不值得為 2% 回 `needs_decision`。

修正後 HEAD 的 `bin/_record_finalize.py`、`bin/lib/_finalize_media.py` 與修正前 HEAD 逐位元相同；表 1「修正後 HEAD」一欄是對本分支的 `bin/` 實際重跑的結果。

## 6. 衍生工作（不編號）

- 在同一批真實段落上做「同一段」對照：由主 session（可讀真實資料的一方）對重放用的段落，以 `042c404` 與 HEAD 的 `bin/_record_finalize.py` 各跑一次 `MH_FINALIZE_JOBS=1` 的收尾（或用附錄 A 的 `bench_norm.py` 抽 3 段），比對每段 normalize；並以 `tools/bench/replay.py --legacy` 再跑一次，排除前處理並行的干擾。預期：差距在 15% 內。
- 若要縮短重編路徑本身（不是退化，是既有成本）：每段成本 ≈ 段長 × 60 fps × 畫布像素，可行方向是讓舊段落也走 copy（不在本 spec 範圍）或在使用者決定 §4.4.13 的 30 fps 後自然減半。

## 附錄 A：bench_norm.py

```python
"""量一段 normalize() 的牆鐘：bench_norm.py <finalize.py> <seg.mov> <work_dir> [--link-fps N] [--floor N] [--no-select]
只用合成段落。印一行 JSON。"""
import importlib.util, json, os, re, sys, time

fin, seg, work = sys.argv[1:4]
opts = sys.argv[4:]
spec = importlib.util.spec_from_file_location("_rf_bench", fin)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if "--link-fps" in opts:
    lf = float(opts[opts.index("--link-fps") + 1])
    mod.link_fps = lambda s: lf
if "--floor" in opts and hasattr(mod, "TAIL_PAD_FPS_FLOOR"):
    mod.TAIL_PAD_FPS_FLOOR = float(opts[opts.index("--floor") + 1])
cmds = []
orig_ffmpeg = mod.ffmpeg
def spy(*args, **kw):
    cmds.append([str(x) for x in args])
    return orig_ffmpeg(*args, **kw)
mod.ffmpeg = spy
if "--no-select" in opts:  # 實驗：拿掉 select 去重（只量時間；產物過不了 check_norm）
    orig_encode = mod.encode
    def enc(inputs, graph, out, **kw):
        return orig_encode(inputs, re.sub(r"select='[^']*',", "", graph), out, **kw)
    mod.encode = enc
    mod.check_norm = lambda *a, **k: None
os.makedirs(work, exist_ok=True)
t0 = time.monotonic()
a = mod.analyze(seg)
t1 = time.monotonic()
v = a["video"]["stream"]
W, H = mod.even_up(v["width"]), mod.even_up(v["height"])
err = None
try:
    mod.normalize(1, seg, a, None, work, W, H, mod.MIN_BITRATE)
except Exception as e:  # 042c404 在 link_fps 低報時 check_norm 失敗：照樣記時間
    err = type(e).__name__
t2 = time.monotonic()
graph = next((c[c.index("-filter_complex") + 1] for c in cmds if "-filter_complex" in c), "")
print(json.dumps({"analyze": round(t1 - t0, 2), "normalize": round(t2 - t1, 2), "error": err, "graph": graph}))
for f in os.listdir(work):
    os.remove(os.path.join(work, f))
```

`run_bench.sh <標籤> <finalize.py> <seg.mov> [選項…]`：建 `mktemp -d` 工作目錄，同一設定跑 3 次 `bench_norm.py`（取 stdout 最後一行），印 3 次的秒數與排序後第 2 個（中位數）。版本取法：`git archive <commit> bin | tar -x -C <dir>`，再把 `<dir>/bin/_record_finalize.py` 交給 bench。
