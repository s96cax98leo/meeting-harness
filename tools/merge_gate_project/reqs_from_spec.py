#!/usr/bin/env python3
"""requirements command adapter：從 base 的 specs/<epic>/spec.md 取驗收條件給 merge_gate.py（spec §2.1、§4.3）。

呼叫者：merge_gate.py（cwd＝專案根），沒有命令列參數。
環境變數：AWF_REPO、AWF_PR、AWF_HEAD_SHA（必填）；AWF_REQ_BASE（選填，預設 origin/main）。
stdout（exit 0）：{"requirements": [{"id", "text", "source"}], "epic": "<epic>", "base": "<40 碼>"}。
exit 2：任何讀不到或判不出的情況，原因寫 stderr（中文、≤300 字、不含 spec 全文）。

解析規則見 specs/auto-merge/adr/adr-am-requirements.md〈決定〉第 1–8 點：
- epic 候選＝merge-base..head 的 Spec-Epic trailer ∪ diff 裡 specs/<epic>/ 的 <epic>（排除 _templates），要恰好一個；
- 只讀 base 版本的 spec，不讀 PR head 的；
- 有 `## R<數字>` 標題時只看最後一個之後；取第一個含「驗收」的 2–4 級標題段；
- 排除第二欄以「（修正輪刪除」「（選做）」開頭的列；條號重複或一條都沒有 → exit 2；
- 「整合修訂與例外」段的列提到 §<條號> 時，只在該條 text 後附指標、不抄內容；
- 其他 trailer（例如 Spec-Reqs）一律不看，需求不允許縮小。

只用標準庫與本機 git：不執行 fetch／pull／clone／remote，不寫任何檔。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import List, Optional, Tuple

DEFAULT_BASE = "origin/main"
REQUIRED_ENV = ("AWF_REPO", "AWF_PR", "AWF_HEAD_SHA")
EPIC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXCLUDED_DIRS = {"_templates"}
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
ROUND = re.compile(r"^##\s+R\d")
REQ_ID = re.compile(r"^\d+(?:\.\d+)+[a-z]?$")
ROW_ID = re.compile(r"^\|\s*(\d+(?:\.\d+)+[a-z]?)\s*\|")
SECTION_REF = re.compile(r"§(\d+(?:\.\d+)+[a-z]?)")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
EXCLUDED_PREFIXES = ("（修正輪刪除", "（選做）")
ACCEPTANCE = "驗收"
EXCEPTIONS = "整合修訂與例外"
MAX_REASON = 300


class AdapterError(Exception):
    """讀不到或判不出：exit 2，訊息寫 stderr。"""


def _write(stream, text: str) -> None:
    data = text.encode("utf-8")
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        buf.write(data)
        buf.flush()
    else:  # pragma: no cover - 沒有 buffer 的串流（例如被替換成 StringIO）
        stream.write(text)
        stream.flush()


def git(*args: str) -> str:
    """執行本機 git（經 PATH），回傳 stdout；失敗丟 AdapterError。只用唯讀子指令。"""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"  # 唯讀操作不順手更新 index
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        r = subprocess.run(["git", *args], capture_output=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AdapterError(f"執行 git {args[0]} 失敗：{e}") from e
    if r.returncode:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise AdapterError(f"git {args[0]} 失敗：{err[-1] if err else 'exit ' + str(r.returncode)}")
    return r.stdout.decode("utf-8", "replace")


def resolve_commit(ref: str, label: str) -> str:
    try:
        sha = git("rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}").strip()
    except AdapterError:
        sha = ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise AdapterError(f"{label} {ref[:80]} 不是本機已有的 commit（adapter 不自己 fetch，請先 git fetch）")
    return sha


def read_env() -> Tuple[str, str]:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k, "").strip()]
    if missing:
        raise AdapterError(f"缺少必填環境變數：{'、'.join(missing)}")
    head_ref = os.environ["AWF_HEAD_SHA"].strip()
    base_ref = os.environ.get("AWF_REQ_BASE", "").strip() or DEFAULT_BASE
    return head_ref, base_ref


def epic_candidates(merge_base: str, head: str) -> List[str]:
    """Spec-Epic trailer 值 ∪ diff 碰到的 specs/<epic>/；回傳排序後的候選。"""
    found = set()
    log = git("log", "--format=%(trailers:key=Spec-Epic,valueonly)", f"{merge_base}..{head}")
    for ln in log.splitlines():
        v = ln.strip()
        if v:
            found.add(v)
    diff = git("diff", "--name-only", "--no-renames", merge_base, head)
    for path in diff.splitlines():
        parts = path.strip().split("/")
        if len(parts) >= 3 and parts[0] == "specs" and parts[1] and parts[1] not in EXCLUDED_DIRS:
            found.add(parts[1])
    return sorted(found)


def pick_epic(cands: List[str]) -> str:
    if not cands:
        raise AdapterError("PR 沒有指出 epic：commit 沒有 Spec-Epic trailer，diff 也沒碰到 specs/<epic>/")
    if len(cands) > 1:
        shown = "、".join(c[:40] for c in cands[:5])
        raise AdapterError(f"PR 指出了多個 epic（{shown}），需求來源要恰好一個")
    epic = cands[0]
    if not EPIC_NAME.match(epic) or epic in EXCLUDED_DIRS:
        raise AdapterError(f"Spec-Epic 的值 {epic[:40]} 不是合法的 epic 名稱")
    return epic


def read_base_spec(base: str, epic: str) -> List[str]:
    rel = f"specs/{epic}/spec.md"
    try:
        kind = git("cat-file", "-t", f"{base}:{rel}").strip()
    except AdapterError:
        kind = ""
    if kind != "blob":
        raise AdapterError(f"{rel} 不在 base（{base[:12]}）上；新 epic 要先把 spec 合進 main")
    return git("show", f"{base}:{rel}").splitlines()


def heading_level(line: str) -> Optional[Tuple[int, str]]:
    m = HEADING.match(line)
    return (len(m.group(1)), m.group(2)) if m else None


def scope_start(lines: List[str]) -> int:
    """有 `## R<數字>` 標題時回傳最後一個的下一行（0 起算）；沒有回 0。"""
    start = 0
    for i, ln in enumerate(lines):
        if ROUND.match(ln):
            start = i + 1
    return start


def find_section(lines: List[str], start: int, keyword: str) -> Optional[Tuple[int, int]]:
    """範圍內第一個含 keyword 的 2–4 級標題段：回傳 (標題下一行, 段尾) 的 0 起算索引。"""
    for i in range(start, len(lines)):
        h = heading_level(lines[i])
        if not h or not (2 <= h[0] <= 4) or keyword not in h[1]:
            continue
        end = len(lines)
        for j in range(i + 1, len(lines)):
            h2 = heading_level(lines[j])
            if h2 and h2[0] <= h[0]:
                end = j
                break
        return i + 1, end
    return None


def cells(line: str) -> List[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in CELL_SPLIT.split(body)]


def row_text(line: str, req_id_end: int) -> str:
    """條號之後的整列原文（去掉頭尾的 `|` 與空白）。"""
    rest = line[req_id_end:].strip()
    if rest.startswith("|"):
        rest = rest[1:]
    if rest.endswith("|") and not rest.endswith("\\|"):
        rest = rest[:-1]
    return rest.strip()


def parse_requirements(lines: List[str], begin: int, end: int, rel: str) -> List[dict]:
    out, seen = [], set()
    for i in range(begin, end):
        line = lines[i]
        m = ROW_ID.match(line.strip())
        if not m:
            continue
        rid = m.group(1)
        cs = cells(line)
        second = cs[1] if len(cs) > 1 else ""
        if second.startswith(EXCLUDED_PREFIXES):
            continue
        if rid in seen:
            raise AdapterError(f"{rel} 的驗收段條號 {rid} 重複（第 {i + 1} 行）")
        seen.add(rid)
        stripped = line.strip()
        out.append({"id": rid, "text": row_text(stripped, m.end(1)), "line": i + 1})
    if not out:
        raise AdapterError(f"{rel} 的驗收段裡一條驗收條件都沒有")
    return out


def exception_pointers(lines: List[str], start: int, rel: str) -> dict:
    """同一範圍內「整合修訂與例外」段：{條號: [指標文字, …]}。只給指標，不抄該列內容。"""
    sec = find_section(lines, start, EXCEPTIONS)
    pointers: dict = {}
    if not sec:
        return pointers
    for i in range(sec[0], sec[1]):
        line = lines[i].strip()
        if not line.startswith("|"):
            continue
        cs = cells(line)
        if not cs or not re.fullmatch(r"\d+", cs[0]):
            continue
        n = cs[0]
        refs = []
        for ref in SECTION_REF.findall(line):
            if REQ_ID.match(ref) and ref not in refs:
                refs.append(ref)
        for ref in refs:
            pointers.setdefault(ref, []).append(f"〔{EXCEPTIONS}第 {n} 條提到本條，見 {rel}:{i + 1}〕")
    return pointers


def build(base_ref: str, head_ref: str) -> dict:
    base = resolve_commit(base_ref, "base")
    head = resolve_commit(head_ref, "PR head")
    try:
        merge_base = git("merge-base", base, head).strip()
    except AdapterError as e:
        raise AdapterError(f"算不出 base 與 PR head 的 merge-base：{e}") from e
    epic = pick_epic(epic_candidates(merge_base, head))
    rel = f"specs/{epic}/spec.md"
    lines = read_base_spec(base, epic)
    start = scope_start(lines)
    sec = find_section(lines, start, ACCEPTANCE)
    if not sec:
        raise AdapterError(f"{rel}（base 版）找不到含「{ACCEPTANCE}」的 2–4 級標題")
    reqs = parse_requirements(lines, sec[0], sec[1], rel)
    pointers = exception_pointers(lines, start, rel)
    short = base[:12]
    out = []
    for r in reqs:
        text = r["text"] + "".join(pointers.get(r["id"], []))
        out.append({"id": r["id"], "text": text, "source": f"{rel}:{r['line']}@{short}"})
    return {"requirements": out, "epic": epic, "base": base}


def main() -> int:
    try:
        head_ref, base_ref = read_env()
        result = build(base_ref, head_ref)
    except AdapterError as e:
        msg = str(e).replace("\n", " ")
        _write(sys.stderr, msg[:MAX_REASON] + "\n")
        return 2
    _write(sys.stdout, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
