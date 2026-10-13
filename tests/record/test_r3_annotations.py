"""錄製註記、標記、（聽不清）、summary 兩段、schema markers、地端總結、下游相容（spec §4.30.6、§4.31.1–§4.31.10、§4.45.3）。

時間軸（錄製時鐘 → 成品時間）：段落 [0,120)＋[210,500)，暫停 120→210（成品 02:00）；麥克風靜音 300→330（成品 03:30–04:00）；
輸出裝置切換 t=250（成品 02:40，builtIn → bluetooth）；兩路 ≤ -60 dBFS 的長靜音 400→440（成品 05:10–05:50）。
成品總長 410 秒；逐字段每 10 秒一段，講者每 60 秒交替（範例甲／範例乙）。
暫停註記的結束時間（成品時間軸上暫停長度為 0）spec 未定，本檔只比對開始時間。
所有素材只在 TMPDIR；地端總結用 127.0.0.1 上的替身模型（不連 ollama）；下游專案只讀（子程序、-B 不寫 .pyc）。
"""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from tests.record import _fixtures as fx
from tests.record._helpers import BIN, tmpdir
from tests.record.surface import REPO

RENDER_PY = BIN / "_render.py"
MERGE_PY = BIN / "_merge_speakers.py"
LOCAL_PY = BIN / "summarize-local.py"
SCHEMA = REPO / "schema" / "meeting-record.v1.json"
NOTES_SKILL = REPO / ".claude" / "skills" / "meeting-notes" / "SKILL.md"
DOWNSTREAM = Path("/Users/yuktang/Documents/Agent/PersonalAgent/tools/meetings.py")
R2_REV = "377dd92"
TITLE = "範例專案週會"
MARKERS = [{"label": "範例標記一", "t": 65.0, "speaker": "範例甲"}, {"label": "範例標記二", "t": 250.0}]
EXPECT_MARK_LINES = ["- 01:05 範例標記一（範例甲）", "- 04:10 範例標記二"]
REQUIRED_HEADS = ["## 決議", "## 依賴", "## 風險與未決", "## 交辦", "## 存疑"]
PAUSE_RE = r"〔暫停 02:00–\d\d:\d\d，這段沒有錄〕"
ANNOTATIONS = [(PAUSE_RE, 120.0), (re.escape("〔麥克風靜音 03:30–04:00〕"), 210.0),
               (re.escape("〔輸出裝置切換：builtIn → bluetooth〕"), 160.0), (re.escape("〔長靜音 05:10–05:50〕"), 310.0),
               (re.escape("〔範例標記一〕"), 65.0), (re.escape("〔範例標記二〕"), 250.0)]
MODEL_SUMMARY = ("# 範例專案週會\n\n一句話：範例專案本週進度確認。\n\n## 決議\n- 範例決議\n\n## 依賴\n- 範例依賴\n\n"
                 "## 風險與未決\n- 範例風險\n\n## 交辦\n- 範例交辦\n\n## 存疑（建議人工確認）\n- （無）")


def seg_text(i):
    return f"第{i + 1:02d}句範例內容"


def whisper_segments(total=410.0, step=10.0):
    n = int(total // step)
    return [(i * step, (i + 1) * step, seg_text(i)) for i in range(n)]


def levels(total_rec, *, silence=None, pauses=(), mutes=()):
    """錄製時鐘每 0.5 秒一窗：暫停中兩路 null、靜音中 mic null、silence 區間兩路 -75，其餘系統 -20、麥克風 -30。"""
    def inside(c, ivs):
        return any(a <= c < b for a, b in ivs)

    sysl, mic = [], []
    for k in range(int(round(total_rec / 0.5))):
        c = (k + 0.5) * 0.5
        if inside(c, pauses):
            sysl.append(None)
            mic.append(None)
            continue
        quiet = silence is not None and silence[0] <= c < silence[1]
        sysl.append(-75.0 if quiet else -20.0)
        mic.append(None if inside(c, mutes) else (-80.0 if quiet else -30.0))
    return sysl, mic


def build_session(base, *, events=True, silence=(400.0, 440.0), markers=MARKERS, markers_json=None,
                  quality=None, speakers=True, tracks=True):
    """完整場次：meeting.record.json、錄音/tracks/（JSON）、transcript.segments.json、diarization.json、speakers.map.json。"""
    sess = Path(base) / "20261011" / "範例場次"
    rec = sess / "錄音"
    rec.mkdir(parents=True, exist_ok=True)
    (sess / "meeting.record.json").write_text(json.dumps(fx.meeting_record(markers=markers, title=TITLE),
                                                         ensure_ascii=False, indent=2), encoding="utf-8")
    if tracks:
        if events:
            sysl, mic = levels(500.0, silence=silence, pauses=[(120.0, 210.0)], mutes=[(300.0, 330.0)])
            fx.write_tracks_json(rec, [(0.0, 120.0), (210.0, 290.0)], system=sysl, mic=mic,
                                 pauses=[(120.0, "pause"), (210.0, "resume")], mutes=[(300.0, True), (330.0, False)],
                                 device_events=[(250.0, "output", "builtIn", "bluetooth")])
        else:
            sysl, mic = levels(410.0, silence=silence)
            fx.write_tracks_json(rec, [(0.0, 410.0)], system=sysl, mic=mic)
    if markers_json is not None:
        (rec / "markers.json").write_text(json.dumps(markers_json, ensure_ascii=False, indent=2), encoding="utf-8")
    segs = whisper_segments()
    (rec / "transcript.segments.json").write_text(json.dumps(
        {"segments": [{"start": a, "end": b, "text": t} for a, b, t in segs]}, ensure_ascii=False), encoding="utf-8")
    (rec / "transcript.raw.md").write_text(
        "# 逐字稿（原始，未經任何後處理）\n\n> 來源：範例.wav　語言：zh　模型：範例\n\n" + "\n".join(t for _, _, t in segs) + "\n",
        encoding="utf-8")
    if quality is not None:
        (rec / "transcript.quality.json").write_text(json.dumps(quality, ensure_ascii=False), encoding="utf-8")
    if speakers:
        diar = [{"start": float(s), "end": float(min(s + 60, 410)), "speaker": f"SPEAKER_0{(s // 60) % 2}"}
                for s in range(0, 410, 60)]
        (rec / "diarization.json").write_text(json.dumps({"segments": diar, "segmentsOverlapped": diar},
                                                         ensure_ascii=False), encoding="utf-8")
        (rec / "speakers.map.json").write_text(json.dumps({"SPEAKER_00": "範例甲", "SPEAKER_01": "範例乙"},
                                                          ensure_ascii=False), encoding="utf-8")
    return sess


def py(args, timeout=120, env=None):
    e = dict(os.environ)
    e.pop("MH_MIN_SPEAKER_SEC", None)
    e.update(env or {})
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=timeout, env=e)


def merge(tc, sess):
    rec = sess / "錄音"
    r = py([MERGE_PY, rec / "transcript.segments.json", rec / "diarization.json", rec / "transcript.speakers.md",
            rec / "speakers.map.json"])
    tc.assertEqual(r.returncode, 0, r.stderr)
    return rec / "transcript.speakers.md"


def render(tc, sess, *flags, render_py=RENDER_PY):
    r = py([render_py, sess, *flags])
    tc.assertEqual(r.returncode, 0, f"_render.py {' '.join(flags)} 失敗：{r.stderr}")
    return r


def section(text, head):
    """summary.md 的某個 ## 段（含標題行）的內文行；沒有就 None。"""
    lines = text.splitlines()
    if head not in lines:
        return None
    i = lines.index(head)
    out = []
    for ln in lines[i + 1:]:
        if ln.startswith("## ") or ln.startswith("# "):
            break
        if ln.strip():
            out.append(ln)
    return out


def vtt_blocks(vtt):
    return [b.strip() for b in re.split(r"\n\s*\n", vtt) if b.strip()]


def r2_render(tc, d):
    """377dd92 的 _render.py（R2 版本）取到暫存目錄。"""
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{R2_REV}:bin/_render.py"], capture_output=True, text=True)
    tc.assertEqual(r.returncode, 0, r.stderr)
    p = Path(d) / "r2_render.py"
    p.write_text(r.stdout, encoding="utf-8")
    return p


class FakeOllama:
    """127.0.0.1 上的替身模型：/api/tags 列一個範例模型，/api/generate 回固定的 summary。"""

    def __init__(self, tc, response):
        resp = response

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send({"models": [{"name": "fake-model:latest"}]})

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self._send({"response": resp})

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        tc.addCleanup(self.srv.server_close)
        tc.addCleanup(self.srv.shutdown)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


class TestR3Annotations(unittest.TestCase):
    def assert_attached(self, md_lines, pattern, t, label):
        """註記行插在「t 所在段落」所屬 block 的標頭行之前（中間只容許其他註記行與空行）。"""
        idx = [i for i, ln in enumerate(md_lines) if re.fullmatch(pattern, ln.strip())]
        self.assertEqual(len(idx), 1, f"{label}：speakers.md 應恰有一行註記 {pattern}")
        j = idx[0] + 1
        while j < len(md_lines) and (not md_lines[j].strip() or md_lines[j].strip().startswith("〔")):
            j += 1
        self.assertLess(j, len(md_lines), f"{label}：註記之後應接 block 標頭")
        self.assertTrue(md_lines[j].startswith("**["), f"{label}：註記之後應接 block 標頭，實際：{md_lines[j]!r}")
        k = j + 1
        block = []
        while k < len(md_lines) and not md_lines[k].startswith("**["):
            block.append(md_lines[k])
            k += 1
        target = seg_text(int(t // 10))
        self.assertTrue(any(target in ln for ln in block), f"{label}：應掛在含「{target}」的 block 之前")

    # spec §4.31.1：speakers.md（經 --annotate-speakers）與 VTT 各有一行對應註記（成品時間），VTT 的註記在 NOTE 區塊
    def test_annotations_in_speakers_and_vtt(self):
        sess = build_session(tmpdir(self))
        md = merge(self, sess)
        render(self, sess, "--annotate-speakers")
        lines = md.read_text(encoding="utf-8").splitlines()
        for pat, t in ANNOTATIONS:
            with self.subTest(annotation=pat):
                self.assert_attached(lines, pat, t, pat)
        render(self, sess, "--vtt")
        blocks = vtt_blocks((sess / "錄音" / "transcript.vtt").read_text(encoding="utf-8"))
        for pat, _ in ANNOTATIONS:
            with self.subTest(vtt=pat):
                hits = [b for b in blocks if re.search(pat, b)]
                self.assertEqual(len(hits), 1, f"VTT 應恰有一處 {pat}")
                self.assertTrue(hits[0].startswith("NOTE"), f"VTT 的註記應在 NOTE 區塊：{hits[0]!r}")
                self.assertNotIn("-->", hits[0], "註記不得佔 cue")

    # spec §4.31.2：長靜音 29.5 秒不標、30 秒標；暫停區間內的不標
    def test_long_silence_threshold(self):
        for dur, want in ((29.5, False), (30.0, True)):
            with self.subTest(seconds=dur):
                sess = build_session(tmpdir(self), events=False, silence=(100.0, 100.0 + dur), markers=None)
                render(self, sess, "--summary")
                notes = section((sess / "summary.md").read_text(encoding="utf-8"), "## 錄製註記") or []
                hit = [ln for ln in notes if "長靜音" in ln]
                if want:
                    self.assertEqual(hit, ["- 01:40–02:10 長靜音"])
                else:
                    self.assertEqual(hit, [], "29.5 秒不得標長靜音")
        sess = build_session(tmpdir(self), silence=None, markers=None)
        render(self, sess, "--summary")
        notes = section((sess / "summary.md").read_text(encoding="utf-8"), "## 錄製註記")
        self.assertIsNotNone(notes, "有暫停時應有 ## 錄製註記")
        self.assertEqual([ln for ln in notes if "長靜音" in ln], [], "暫停區間（兩路 null 90 秒）不得標長靜音")

    # spec §4.31.3：段落內掛該段、兩段之間掛下一段、離最近一段 > 2 秒獨立成行
    def test_marker_alignment(self):
        def vtt_order(segs, marker_t):
            sess = tmpdir(self) / "場次"
            rec = sess / "錄音"
            rec.mkdir(parents=True)
            (sess / "meeting.record.json").write_text(json.dumps(fx.meeting_record(
                markers=[{"label": "範例對齊", "t": marker_t}], title=TITLE), ensure_ascii=False), encoding="utf-8")
            (rec / "transcript.segments.json").write_text(json.dumps(
                {"segments": [{"start": a, "end": b, "text": f"範例段{i}"} for i, (a, b) in enumerate(segs, 1)]},
                ensure_ascii=False), encoding="utf-8")
            render(self, sess, "--vtt")
            order = []
            for b in vtt_blocks((rec / "transcript.vtt").read_text(encoding="utf-8")):
                if b.startswith("NOTE") and "〔範例對齊〕" in b:
                    order.append("M")
                else:
                    mm = re.search(r"範例段(\d)", b)
                    if mm and "-->" in b:
                        order.append(mm.group(1))
            return order

        self.assertEqual(vtt_order([(0, 5), (8, 12)], 4.9), ["M", "1", "2"], "t=4.9 在第 1 段內，掛第 1 段（之前）")
        self.assertEqual(vtt_order([(0, 5), (8, 12)], 6.0), ["1", "M", "2"], "t=6 在兩段之間，掛下一段")
        self.assertEqual(vtt_order([(0, 5), (20, 25)], 10.0), ["1", "M", "2"], "t=10 離最近一段 > 2 秒，依時間獨立成行")

    # spec §4.31.4：markers 選用；t 負數、缺 label 驗證失敗；沒有 markers 的既有 fixture 仍通過
    def test_schema_markers_optional(self):
        import jsonschema

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(fx.meeting_record(), schema)
        jsonschema.validate(fx.meeting_record(markers=MARKERS + [{"label": "範例", "t": 0, "note": "範例備註"}]), schema)
        for bad in ([{"label": "範例", "t": -1.0}], [{"t": 3.0}], [{"label": 5, "t": 3.0}]):
            with self.subTest(markers=bad):
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(fx.meeting_record(markers=bad), schema)
        self.assertNotIn("markers", schema.get("required", []), "markers 為選用，required 不變")

    # spec §4.31.5：有標記與事件時 summary.md 依 §3.18 加兩段（在五個必備段之後）
    def test_summary_sections(self):
        sess = build_session(tmpdir(self))
        render(self, sess, "--summary")
        text = (sess / "summary.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(section(text, "## 標記"), EXPECT_MARK_LINES)
        notes = section(text, "## 錄製註記")
        self.assertIsNotNone(notes, "應有 ## 錄製註記")
        self.assertTrue(any(re.fullmatch(r"- 02:00–\d\d:\d\d 暫停（未錄）", ln) for ln in notes), notes)
        for want in ("- 03:30–04:00 麥克風靜音", "- 02:40 輸出裝置切換：builtIn → bluetooth", "- 05:10–05:50 長靜音"):
            self.assertIn(want, notes)
        self.assertEqual(len(notes), 4, notes)
        last_required = max(next(i for i, ln in enumerate(lines) if ln.startswith(h)) for h in REQUIRED_HEADS)
        self.assertLess(last_required, lines.index("## 標記"), "## 標記 應在五個必備段之後")
        self.assertLess(lines.index("## 標記"), lines.index("## 錄製註記"))

    # spec §4.31.5：沒有標記、沒有事件時兩段都不出現，與 R2 輸出逐位元相同
    def test_summary_unchanged_without_events(self):
        d = tmpdir(self)
        sess = build_session(d, events=False, silence=None, markers=None)
        render(self, sess, "--summary")
        r3 = (sess / "summary.md").read_bytes()
        render(self, sess, "--summary", render_py=r2_render(self, d))
        r2 = (sess / "summary.md").read_bytes()
        self.assertEqual(r3, r2, "沒有標記、沒有事件時 summary.md 應與 R2 逐位元相同")
        self.assertNotIn("## 標記".encode(), r3)
        self.assertNotIn("## 錄製註記".encode(), r3)

    # spec §4.31.6：meeting.record.json 沒有 markers 時取 錄音/markers.json；兩者都有時以 meeting.record.json 為準
    def test_markers_source_precedence(self):
        mj = [{"t": 30.0, "recordT": 30.0, "wallClock": "2026-10-12T21:00:30+08:00", "label": "標記 1"}]
        sess = build_session(tmpdir(self), events=False, silence=None, markers=None, markers_json=mj)
        render(self, sess, "--summary")
        self.assertEqual(section((sess / "summary.md").read_text(encoding="utf-8"), "## 標記"), ["- 00:30 標記 1"])
        sess = build_session(tmpdir(self), events=False, silence=None, markers=MARKERS, markers_json=mj)
        render(self, sess, "--summary")
        self.assertEqual(section((sess / "summary.md").read_text(encoding="utf-8"), "## 標記"), EXPECT_MARK_LINES)

    # spec §4.31.7：summary.md 與註記行不得含裝置名稱、uid、視窗標題
    def test_no_device_names(self):
        sess = build_session(tmpdir(self))
        merge(self, sess)
        render(self, sess, "--summary", "--vtt")
        render(self, sess, "--annotate-speakers")
        texts = {"summary.md": (sess / "summary.md").read_text(encoding="utf-8"),
                 "transcript.vtt": (sess / "錄音" / "transcript.vtt").read_text(encoding="utf-8"),
                 "transcript.speakers.md": (sess / "錄音" / "transcript.speakers.md").read_text(encoding="utf-8")}
        self.assertIn("## 錄製註記", texts["summary.md"], "前提：summary.md 應有 ## 錄製註記")
        for name, text in texts.items():
            for bad in ("範例裝置", "uid-範例", fx.R3_WINDOW_TITLE):
                with self.subTest(file=name, word=bad):
                    self.assertNotIn(bad, text)

    # spec §4.31.9：地端總結在模型輸出之後接上與 _render.py 相同的兩段；沒有標記與事件時與現行輸出相同
    def test_local_summary_sections(self):
        src = LOCAL_PY.read_text(encoding="utf-8")
        self.assertIn("importlib", src, "summarize-local.py 應以 importlib 呼叫 _render.py 的同一個函式")
        self.assertIn("_render", src)
        srv = FakeOllama(self, MODEL_SUMMARY)
        env = {"OLLAMA_HOST": srv.url, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}

        def local(sess):
            harness = tmpdir(self)
            r = py([LOCAL_PY, sess, harness, "--mode", "meeting", "--model", "fake-model"], env=env)
            self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
            return (sess / "summary.md").read_text(encoding="utf-8")

        plain = build_session(tmpdir(self), events=False, silence=None, markers=None)
        self.assertEqual(local(plain), MODEL_SUMMARY + "\n", "沒有標記、沒有事件時與現行輸出相同")

        mj = [{"t": 65.0, "recordT": 65.0, "wallClock": "2026-10-12T21:01:05+08:00", "label": "標記 1"}]
        sess = build_session(tmpdir(self), markers=None, markers_json=mj)
        out = local(sess)
        self.assertTrue(out.startswith(MODEL_SUMMARY.rstrip()), "模型輸出原樣在前")
        render(self, sess, "--summary")
        cloud = (sess / "summary.md").read_text(encoding="utf-8")
        for head in ("## 標記", "## 錄製註記"):
            with self.subTest(section=head):
                self.assertIsNotNone(section(cloud, head), f"前提：_render.py 應產生 {head}")
                self.assertEqual(section(out, head), section(cloud, head), f"地端與雲端的 {head} 應一致")
        ol = out.splitlines()
        self.assertLess(ol.index("## 存疑（建議人工確認）"), ol.index("## 標記"))

    # spec §4.31.10：--annotate-speakers 插入註記行與（聽不清），其他位元組不變
    def test_speakers_post_process(self):
        quality = [{"start": 30.0, "end": 40.0, "reason": "compression_ratio"}]
        sess = build_session(tmpdir(self), quality=quality)
        md = merge(self, sess)
        orig = md.read_text(encoding="utf-8")
        render(self, sess, "--annotate-speakers")
        new = md.read_text(encoding="utf-8")
        self.assertIn("（聽不清）" + seg_text(3), new, "品質檔列出的段落文字前應加（聽不清）")
        self.assertEqual(new.count("（聽不清）"), 1)
        inserted = [ln for ln in new.splitlines() if ln.strip().startswith("〔")]
        self.assertEqual(len(inserted), len(ANNOTATIONS), inserted)
        stripped = "\n".join(ln for ln in new.split("\n") if not ln.strip().startswith("〔")).replace("（聽不清）", "")
        self.assertEqual(stripped, orig, "除插入的行與（聽不清）外，speakers.md 的其他位元組不變")

    # spec §4.31.10：對已處理過的檔再跑一次結果不變（冪等）
    def test_speakers_post_process_idempotent(self):
        sess = build_session(tmpdir(self), quality=[{"start": 30.0, "end": 40.0, "reason": "repeat_run"}])
        md = merge(self, sess)
        render(self, sess, "--annotate-speakers")
        once = md.read_bytes()
        self.assertIn("〔".encode(), once, "前提：第一次應插入註記")
        render(self, sess, "--annotate-speakers")
        self.assertEqual(md.read_bytes(), once, "再跑一次結果應不變")

    # spec §4.30.6：（聽不清）只在衍生檔；raw 逐位元不變
    def test_unclear_marked_in_derived_only(self):
        quality = [{"start": 30.0, "end": 40.0, "reason": "no_speech_loop"}]
        sess = build_session(tmpdir(self), quality=quality)
        raw = sess / "錄音" / "transcript.raw.md"
        before = raw.read_bytes()
        md = merge(self, sess)
        render(self, sess, "--vtt")
        render(self, sess, "--annotate-speakers")
        vtt = (sess / "錄音" / "transcript.vtt").read_text(encoding="utf-8")
        cue = [b for b in vtt_blocks(vtt) if seg_text(3) in b and "-->" in b]
        self.assertEqual(len(cue), 1)
        self.assertRegex(cue[0].splitlines()[-1], r"^(<v [^>]+>)?（聽不清）" + re.escape(seg_text(3)) + "$")
        others = [b for b in vtt_blocks(vtt) if "-->" in b and seg_text(3) not in b]
        self.assertTrue(all("（聽不清）" not in b for b in others), "其他段落不得加（聽不清）")
        self.assertIn("（聽不清）" + seg_text(3), md.read_text(encoding="utf-8"))
        self.assertEqual(raw.read_bytes(), before, "transcript.raw.md 應逐位元不變")

    # spec §4.31.8：下游 meetings._missing_sections 對加了兩段的 summary.md 回空清單（下游不存在時 skip＝not_verifiable）
    def test_downstream_missing_sections(self):
        if not DOWNSTREAM.is_file():
            self.skipTest("not_verifiable：下游知識庫專案不存在，test 段由主 session 補跑")
        sess = build_session(tmpdir(self))
        render(self, sess, "--summary")
        summary = sess / "summary.md"
        self.assertIn("## 錄製註記", summary.read_text(encoding="utf-8"), "前提：summary.md 應有新段")
        code = ("import importlib.util, json, sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "spec = importlib.util.spec_from_file_location('downstream_meetings', sys.argv[2])\n"
                "mod = importlib.util.module_from_spec(spec)\n"
                "sys.modules[spec.name] = mod\n"
                "spec.loader.exec_module(mod)\n"
                "print('MISSING=' + json.dumps(mod._missing_sections(open(sys.argv[3], encoding='utf-8').read())))\n")
        r = subprocess.run([sys.executable, "-B", "-c", code, str(DOWNSTREAM.parent), str(DOWNSTREAM), str(summary)],
                           capture_output=True, text=True, timeout=60, cwd=str(tmpdir(self)),
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        # 下游載入時會印它自己的訊息（可能含其專案名稱）：失敗訊息只報結束碼，不轉印下游輸出（客戶資料邊界）
        self.assertEqual(r.returncode, 0, f"下游 tools/meetings.py 載入或執行失敗（結束碼 {r.returncode}）")
        got = [ln for ln in r.stdout.splitlines() if ln.startswith("MISSING=")]
        self.assertEqual(len(got), 1, "下游沒有回傳 _missing_sections 結果")
        self.assertEqual(json.loads(got[0][len("MISSING="):]), [], "下游 _missing_sections 應回空清單")

    # spec §4.45.3：meeting-notes SKILL.md 說明「## 標記」「## 錄製註記」
    def test_notes_skill_updated(self):
        text = NOTES_SKILL.read_text(encoding="utf-8")
        missing = [k for k in ("## 標記", "## 錄製註記") if k not in text]
        self.assertEqual(missing, [], f"meeting-notes SKILL.md 缺少：{missing}")


if __name__ == "__main__":
    unittest.main()
