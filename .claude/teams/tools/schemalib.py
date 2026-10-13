"""agent team 的 schema 工具：載入、組合（信封＋payload）、驗證。

只支援 schemas/ 用到的 JSON Schema 關鍵字（type、properties、required、enum、items、
minItems、minLength、minimum、maximum），所以 hook 不必依賴第三方套件；
golden-set/run.py 會拿官方 jsonschema 套件交叉比對，確保判斷一致。

任務編號規則讀 ../guard.config.json 的 task_id_prefix、task_authority（init.sh 產生）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TEAMS_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = TEAMS_DIR / "schemas"
PAYLOAD_DIR = SCHEMA_DIR / "payloads"
CONFIG = TEAMS_DIR / "guard.config.json"
_PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


def config() -> dict:
    """專案設定（沒有檔案或格式錯時回空 dict）；還沒替換的佔位符當成空值。"""
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: ("" if isinstance(v, str) and _PLACEHOLDER.search(v) else v) for k, v in data.items()} if isinstance(data, dict) else {}


def task_id_regex() -> re.Pattern | None:
    """上層系統發的任務編號長相：task_id_prefix 後接數字（例如 TASK-0123）；沒設定前綴就不檢查。"""
    prefix = (config().get("task_id_prefix") or "").strip()
    return re.compile(rf"(?<![\w-]){re.escape(prefix)}\d+\b") if prefix else None


def task_authority() -> str:
    return (config().get("task_authority") or "").strip() or "上層系統"


def payload_names() -> list[str]:
    return sorted(p.name.removesuffix(".schema.json") for p in PAYLOAD_DIR.glob("*.schema.json"))


def load(name: str) -> dict:
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        path = PAYLOAD_DIR / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _strip_meta(node, in_properties: bool = False):
    """移除 schema 節點上的 $id、title、description，讓內嵌進 workflow 的 schema 精簡。
    `properties` 底下的鍵是欄位名（例如子任務的 title 欄位），不能刪（2026-10-07 乾跑抓到）。"""
    if isinstance(node, dict):
        if in_properties:
            return {k: _strip_meta(v) for k, v in node.items()}
        return {k: _strip_meta(v, k == "properties") for k, v in node.items() if k not in ("$id", "title", "description")}
    if isinstance(node, list):
        return [_strip_meta(v) for v in node]
    return node


def compose(payload: str | None) -> dict:
    """信封＋指定 payload 的完整 schema；payload=None 時 payload 欄位不限形狀。"""
    env = load("envelope")
    if payload:
        env["properties"]["payload"] = load(payload)
    return _strip_meta(env)


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
}


def validate(data, schema: dict, path: str = "$") -> list[str]:
    """回傳錯誤清單（空＝通過）。"""
    errs: list[str] = []
    t = schema.get("type")
    if t:
        py = _TYPES[t]
        ok = isinstance(data, py) and not (t in ("number", "integer") and isinstance(data, bool))
        if not ok:
            return [f"{path}：型別應為 {t}"]
    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}：值 {data!r} 不在 {schema['enum']}")
    if isinstance(data, str) and "minLength" in schema and len(data) < schema["minLength"]:
        errs.append(f"{path}：不能是空字串")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errs.append(f"{path}：小於 {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errs.append(f"{path}：大於 {schema['maximum']}")
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errs.append(f"{path}：缺欄位 {key}")
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                errs.extend(validate(data[key], sub, f"{path}.{key}"))
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errs.append(f"{path}：至少要 {schema['minItems']} 項")
        if "items" in schema:
            for i, item in enumerate(data):
                errs.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return errs


def semantic_errors(env: dict) -> list[str]:
    """schema 表達不了的交接規則。"""
    errs: list[str] = []
    qs = env.get("open_questions") or []
    blocking = [q for q in qs if isinstance(q, dict) and q.get("blocking")]
    if env.get("status") == "done" and blocking:
        errs.append("有 blocking 的 open_questions 時 status 不能是 done")
    for i, q in enumerate(blocking):
        if len(q.get("options") or []) < 2:
            errs.append(f"open_questions[{i}]：blocking 問題要附 2–3 個選項與代價")
    tid = task_id_regex()
    for i, w in enumerate(env.get("derived_work") or []):
        if tid and isinstance(w, str) and tid.search(w):
            errs.append(f"derived_work[{i}]：不可自編任務編號（交 {task_authority()} 編）：{w}")
    payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
    subtasks = payload.get("subtasks")
    if isinstance(subtasks, list):
        owner: dict[str, str] = {}
        ids = {s.get("id") for s in subtasks if isinstance(s, dict)}
        for s in subtasks:
            if not isinstance(s, dict):
                continue
            for f in s.get("owns") or []:
                if f in owner and owner[f] != s.get("id"):
                    errs.append(f"子任務 {owner[f]} 與 {s.get('id')} 同時擁有 {f}（檔案所有權不得重疊）")
                owner[f] = s.get("id")
            for d in s.get("depends_on") or []:
                if d not in ids:
                    errs.append(f"子任務 {s.get('id')} 依賴不存在的 {d}")
    return errs


def check(env, payload: str | None = None) -> list[str]:
    return validate(env, compose(payload)) + (semantic_errors(env) if isinstance(env, dict) else [])


def extract_json(text: str):
    """從 agent 回報文字取出信封：優先最後一個 ```json 區塊，否則嘗試整段。"""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    for raw in reversed(blocks):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
