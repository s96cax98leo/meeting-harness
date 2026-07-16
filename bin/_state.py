#!/usr/bin/env python3
"""_state.py <pipeline-state.json> — 印出各 stage 狀態摘要（供 meeting.sh status 用）"""
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    stages = d.get("stages", {})
    parts = [f"{k}:{v.get('status','?')}" for k, v in stages.items()]
    print(", ".join(parts) if parts else "(空)")
except Exception:
    print("—")
