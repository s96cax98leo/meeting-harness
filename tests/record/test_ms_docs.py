"""meeting-speed 的文件、過期註解、名稱掃描（spec §4.5.6、§4.6.6、§4.6.7、§4.13.4、§4.15.3、§4.16.4）。

客戶名稱清單由 MH_CLIENT_NAMES_FILE 指定（不在 repo 內）。本檔只回報命中的「路徑:行號」，絕不印出清單內容或命中的字；
spec §4.15.3 規定這支不得 skipped，所以沒設 MH_CLIENT_NAMES_FILE 時判 FAIL（plan §2 的指令前綴一律會設）。
"""
import os
import subprocess
import unittest
from pathlib import Path

from tests.record import test_ms_support as s

REPO = s.REPO
EPIC_BASE = "042c404"
SKILLS = REPO / ".claude" / "skills"
RECORD_SKILL = SKILLS / "meeting-record" / "SKILL.md"
TRANSCRIBE_SKILL = SKILLS / "meeting-transcribe" / "SKILL.md"
SPEAKERS_SKILL = SKILLS / "meeting-speakers" / "SKILL.md"
SUMMARY_SKILL = SKILLS / "meeting-summary" / "SKILL.md"
README = REPO / "README.md"
PIPELINE_JS = REPO / ".claude" / "workflows" / "meeting-pipeline.js"


def read(tc, path):
    tc.assertTrue(path.is_file(), f"{path.relative_to(REPO)} 不存在")
    return path.read_text(encoding="utf-8")


def lines_with(text, *needles):
    return [ln for ln in text.splitlines() if all(n in ln for n in needles)]


def ms_files():
    """meeting-speed 新增或修改的檔：git diff --name-only 042c404（工作樹）＋未追蹤檔（不含 .gitignore 忽略的）。"""
    def git(*args):
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout

    names = set(git("diff", "--name-only", EPIC_BASE).splitlines())
    names |= set(git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(REPO / n for n in names if n and (REPO / n).is_file())


class TestMSDocs(unittest.TestCase):
    # spec §4.15.3：本 epic 新增與修改的檔不得含 client-names.txt 的名稱（不得 skipped）
    def test_no_client_names_in_ms_files(self):
        path = os.environ.get("MH_CLIENT_NAMES_FILE")
        self.assertTrue(path, "spec §4.15.3：這支不得 skipped，請設定 MH_CLIENT_NAMES_FILE（plan §2 的指令前綴）")
        p = Path(path)
        self.assertTrue(p.is_file(), "MH_CLIENT_NAMES_FILE 指向的清單檔不存在")
        names = [x.strip().casefold() for x in p.read_text(encoding="utf-8").splitlines()
                 if x.strip() and not x.strip().startswith("#")]
        self.assertTrue(names, "名稱清單沒有任何有效行")
        files = ms_files()
        self.assertTrue(files, "前提：應有本 epic 新增或修改的檔")
        hits = []
        for f in files:
            if f.resolve() == p.resolve():
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                text = f.read_bytes().decode("utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                low = line.casefold()
                if any(n in low for n in names):
                    hits.append(f"{f.relative_to(REPO)}:{i}")
        self.assertEqual(hits, [], "本 epic 的檔含客戶名稱（只列路徑:行號）")

    # spec §4.5.6：meeting-record SKILL 寫明正式 wav 先於影片、.verify-failed.mov 與再跑 finish、畫布鎖定的代價
    def test_record_skill_speed_notes(self):
        text = read(self, RECORD_SKILL)
        for needle in (".verify-failed.mov", "meeting record finish", "畫布鎖定", "解析度"):
            self.assertIn(needle, text, f"meeting-record SKILL.md 缺少「{needle}」")
        self.assertTrue(lines_with(text, "wav", "影片", "收尾"),
                        "應有一行同時寫到 wav、影片與收尾（正式 wav 先出現、影片可能仍在收尾）")
        self.assertTrue(lines_with(text, ".verify-failed.mov", "finish") or
                        any(".verify-failed.mov" in a and "finish" in b
                            for a, b in zip(text.splitlines(), text.splitlines()[1:])),
                        ".verify-failed.mov 的說明應附再跑 meeting record finish 的處理")

    # spec §4.16.4：不帶參數的 finish 接手行為寫進 meeting-record SKILL
    def test_record_skill_finish_no_arg(self):
        text = read(self, RECORD_SKILL)
        self.assertTrue(lines_with(text, "record finish", "不帶參數"),
                        "meeting-record SKILL.md 應有一行說明 meeting record finish 不帶參數的行為")
        self.assertTrue(lines_with(text, "異常中止", "接手"), "應寫明不帶參數時接手異常中止的場次")

    # spec §4.6.6：meeting-transcribe SKILL 寫明 raw 不轉字形、transcript.md 是正體版
    def test_transcribe_skill_raw_policy(self):
        text = read(self, TRANSCRIBE_SKILL)
        self.assertTrue(lines_with(text, "transcript.md", "正體"), "應有一行寫明 transcript.md 是正體版")
        self.assertTrue([ln for ln in text.splitlines() if "raw" in ln and "不轉" in ln],
                        "應有一行寫明 raw 不轉字形（「raw」與「不轉」同一行）")

    # spec §4.6.7：meeting-speakers SKILL 含 annotate 步驟與舊 embeddings.json 的手動清法
    def test_speakers_skill_annotate(self):
        text = read(self, SPEAKERS_SKILL)
        self.assertIn("--annotate-speakers", text)
        self.assertTrue(lines_with(text, "_render.py", "--annotate-speakers"),
                        "annotate 步驟應寫成 _render.py <場次> --annotate-speakers")
        self.assertTrue([ln for ln in text.splitlines() if "embeddings.json" in ln and ("刪" in ln or "清" in ln)],
                        "應寫明舊 embeddings.json 的手動清法（同一行含 embeddings.json 與「刪」或「清」）")

    # spec §4.6.7：meeting-summary SKILL 不得再寫 embedding 存在場次資料夾
    def test_summary_skill_no_session_embeddings(self):
        text = read(self, SUMMARY_SKILL)
        bad = [ln.strip() for ln in text.splitlines()
               if "embeddings.json" in ln and not any(w in ln for w in ("不再", "舊", "刪", "清"))]
        self.assertEqual(bad, [], "meeting-summary SKILL.md 不得再把 embeddings.json 列為場次資料夾的產物")

    # spec §4.13.4：README 流程圖反映音訊先出、轉錄與分離並行、增量轉錄
    def test_readme_flow(self):
        text = read(self, README)
        self.assertIn("增量轉錄", text)
        self.assertTrue("音訊先出" in text or "音訊就緒" in text, "README 應寫到音訊先出（或「音訊就緒」）")
        self.assertTrue([ln for ln in text.splitlines() if "並行" in ln and ("diarize" in ln or "分離" in ln)],
                        "README 應寫到轉錄與講者分離並行（同一行含「並行」與 diarize／分離）")

    # spec §4.13.4：transcribe.sh 檔頭註解（第 3 行附近）不得再寫「優先 large-v3」，應寫 Breeze-ASR-25
    def test_stale_comment_transcribe(self):
        head = "\n".join(s.TRANSCRIBE_SH.read_text(encoding="utf-8").splitlines()[:5])
        self.assertNotIn("優先 mlx-whisper large-v3", head, "transcribe.sh 檔頭註解過期")
        self.assertIn("Breeze", head, "transcribe.sh 檔頭註解應寫到 zh 預設 Breeze-ASR-25")

    # spec §4.13.4：_merge_speakers.py 檔頭（第 3 行附近）不得再寫 senko，應寫 pyannote
    def test_stale_comment_merge_speakers(self):
        head = "\n".join(s.MERGE_PY.read_text(encoding="utf-8").splitlines()[:6])
        self.assertNotIn("senko", head, "_merge_speakers.py 檔頭註解過期（講者分離已是 pyannote）")
        self.assertIn("pyannote", head)

    # spec §4.13.4：record.sh:973 的「整支重新編碼」過期（copy 路徑不重編影片）
    def test_stale_comment_record_sh(self):
        self.assertNotIn("整支重新編碼", s.RECORD_SH.read_text(encoding="utf-8"))

    # spec §4.13.4：.claude/workflows/meeting-pipeline.js 檔頭標示棄用並指向 meeting-summary
    def test_meeting_pipeline_js_deprecated(self):
        head = "\n".join(read(self, PIPELINE_JS).splitlines()[:10])
        self.assertIn("棄用", head, "meeting-pipeline.js 檔頭應標示棄用")
        self.assertIn("meeting-summary", head, "meeting-pipeline.js 檔頭應指向 meeting-summary")


if __name__ == "__main__":
    unittest.main()
