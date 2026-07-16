#!/usr/bin/env bash
# init-vault.sh — 首次使用：從 seeds/ 建立本機 vault（Obsidian wiki + 長期記憶）
# vault/ 不進 git（屬個人/機密會議內容）；本腳本讓新 clone 也能立即使用。
set -uo pipefail
HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="$HARNESS/vault"
mkdir -p "$VAULT/.obsidian" "$VAULT/wiki"
[[ -f "$VAULT/術語表.md" ]] || cp "$HARNESS/seeds/術語表.md" "$VAULT/術語表.md"
[[ -f "$VAULT/會議索引.md" ]] || cp "$HARNESS/seeds/會議索引.md" "$VAULT/會議索引.md"
echo "✓ vault 已就緒：$VAULT"
