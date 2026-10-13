"""golden set：每個範例同時用 schemalib（hook 用）與官方 jsonschema 驗，兩者對 schema 部分的判斷必須一致；
語意規則（semantic=true 的反例）只由 schemalib 擋。用法：uv run --with jsonschema python3 .claude/teams/golden-set/run.py"""
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent / "tools"))
import schemalib
try:
    import jsonschema
except ImportError:
    jsonschema = None
ok = bad = skipped = 0
for kind in ("valid", "invalid"):
    for f in sorted((here / kind).glob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        if case.get("needs_task_prefix") and schemalib.task_id_regex() is None:
            skipped += 1; print(f"略過：未設 TASK_ID_PREFIX（{kind}/{f.name}）"); continue
        schema = schemalib.compose(case["payload"])
        mine = schemalib.check(case["data"], case["payload"])
        want_ok = kind == "valid"
        problems = []
        if (not mine) != want_ok:
            problems.append(f"schemalib 判 {'通過' if not mine else '不通過'}：{mine}")
        if jsonschema:
            official = list(jsonschema.Draft202012Validator(schema).iter_errors(case["data"]))
            schema_only = not schemalib.validate(case["data"], schema)
            if (not official) != schema_only:
                problems.append(f"官方 jsonschema 與 schemalib 的 schema 判斷不一致：official={len(official)} 錯")
            if kind == "invalid" and not case.get("semantic") and not official:
                problems.append("官方 jsonschema 應該擋但通過")
        if problems:
            bad += 1; print(f"FAIL {kind}/{f.name}：" + "；".join(problems))
        else:
            ok += 1
print(f"golden set：通過 {ok}，失敗 {bad}" + (f"，略過 {skipped}" if skipped else "") + ("" if jsonschema else "（未裝 jsonschema，只跑 schemalib；請用 uv run --with jsonschema）"))
sys.exit(1 if bad else 0)
