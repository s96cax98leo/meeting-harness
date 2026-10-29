#!/usr/bin/env python3
"""以 GitHub App 身分換短效 installation token，寫成 gh 用的 hosts.yml（spec §2.2、§4.4.1–§4.4.5）。

    python3 tools/merge_gate_project/gh_app_token.py mint   --app merger|publisher [--config <gh-apps.json>] [--out-dir <目錄>]
    python3 tools/merge_gate_project/gh_app_token.py revoke --app merger|publisher [--out-dir <目錄>]

- --config 預設 ~/.config/meeting-harness/gh-apps.json（{"merger": {"app_id": N}, "publisher": {"app_id": N}}）。
- --out-dir 預設 ~/.config/meeting-harness/gh/<app>；用法：GH_CONFIG_DIR=<out-dir> gh ...
- 私鑰：`security find-generic-password -s meeting-harness.gh-app.<app> -w`（MH_GH_APP_SECURITY 可換執行檔）。
- 簽章：`openssl dgst -sha256 -sign /dev/stdin`，PEM 只走 stdin，不落地（MH_GH_APP_OPENSSL 可換執行檔）。
- API 根 https://api.github.com（MH_GH_API_BASE 可換）。
- exit 0 成功；2 任何錯誤（stderr 寫原因，不含 token、JWT、PEM）。

只用標準庫。不印 token、JWT、私鑰；stdout 只有 mint 成功時的一行 JSON。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_OWNER = "s96cax98leo"
REPO_NAME = "meeting-harness"
APPS = {
    "merger": {"contents": "write", "pull_requests": "write"},
    "publisher": {"contents": "read", "pull_requests": "write"},
}
KEYCHAIN_SERVICE = "meeting-harness.gh-app.{app}"
API_VERSION = "2022-11-28"
TIMEOUT = 30


class Fail(Exception):
    """可預期的錯誤；訊息會寫到 stderr，不得含機敏值。"""


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def config_home() -> Path:
    return Path.home() / ".config" / "meeting-harness"


def api_base() -> str:
    return (os.environ.get("MH_GH_API_BASE") or "https://api.github.com").rstrip("/")


# ---------- 私鑰與 JWT ----------

def read_private_key(app: str) -> bytes:
    exe = os.environ.get("MH_GH_APP_SECURITY") or "security"
    cmd = [exe, "find-generic-password", "-s", KEYCHAIN_SERVICE.format(app=app), "-w"]
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail(f"無法執行 security（{type(e).__name__}）") from None
    if r.returncode != 0:
        raise Fail(f"從 Keychain 取 {KEYCHAIN_SERVICE.format(app=app)} 失敗（security exit {r.returncode}）")
    pem = r.stdout.strip()
    # security -w 遇到多行密碼時可能輸出十六進位
    if pem and b"-----BEGIN" not in pem and re.fullmatch(rb"[0-9a-fA-F]+", pem):
        try:
            pem = bytes.fromhex(pem.decode("ascii")).strip()
        except ValueError:
            pass
    if b"-----BEGIN" not in pem:
        raise Fail("Keychain 項目不是 PEM 格式的私鑰")
    return pem + b"\n"


def sign_rs256(pem: bytes, signing_input: bytes) -> bytes:
    """openssl dgst -sha256 -sign /dev/stdin：私鑰走 stdin；待簽資料（非機敏）放 0600 暫存檔，finally 刪除。"""
    exe = os.environ.get("MH_GH_APP_OPENSSL") or "openssl"
    fd, data_path = tempfile.mkstemp(prefix="mh-jwt-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(signing_input)
        try:
            r = subprocess.run([exe, "dgst", "-sha256", "-sign", "/dev/stdin", data_path],
                               input=pem, capture_output=True, timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Fail(f"無法執行 openssl（{type(e).__name__}）") from None
        if r.returncode != 0 or not r.stdout:
            raise Fail(f"openssl 簽章失敗（exit {r.returncode}）")
        return r.stdout
    finally:
        try:
            os.unlink(data_path)
        except OSError:
            pass


def make_jwt(app_id, pem: bytes) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {"iat": now - 60, "exp": now + 540, "iss": str(app_id)}
    signing_input = (b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." + b64url(json.dumps(claims, separators=(",", ":")).encode()))
    sig = sign_rs256(pem, signing_input.encode("ascii"))
    return signing_input + "." + b64url(sig)


# ---------- HTTP ----------

def call(method: str, path: str, auth: str, body: dict | None = None) -> dict | None:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(api_base() + path, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", API_VERSION)
    req.add_header("User-Agent", "meeting-harness-gh-app-token")
    req.add_header("Authorization", auth)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        msg = ""
        try:
            msg = str(json.loads(e.read().decode("utf-8", "replace")).get("message", ""))[:200]
        except Exception:
            pass
        raise Fail(f"{method} {path} 回 HTTP {e.code}" + (f"：{msg}" if msg else "")) from None
    except (urllib.error.URLError, OSError) as e:
        raise Fail(f"{method} {path} 連線失敗（{type(e).__name__}）") from None
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise Fail(f"{method} {path} 回應不是 JSON") from None


# ---------- 子指令 ----------

def load_app_id(config: Path, app: str):
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Fail(f"讀不到 App 設定 {config}（{type(e).__name__}）") from None
    app_id = (data.get(app) or {}).get("app_id") if isinstance(data, dict) else None
    if not isinstance(app_id, (int, str)) or not str(app_id).strip().isdigit():
        raise Fail(f"App 設定 {config} 沒有 {app}.app_id")
    return int(app_id)


def write_hosts(out_dir: Path, token: str, slug: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    content = (f"github.com:\n    oauth_token: {token}\n    user: {slug}[bot]\n    git_protocol: https\n")
    fd, tmp = tempfile.mkstemp(prefix=".hosts.", suffix=".tmp", dir=out_dir)  # mkstemp 本身就是 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        target = out_dir / "hosts.yml"
        os.replace(tmp, target)
        return target
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mint(app: str, config: Path, out_dir: Path) -> int:
    app_id = load_app_id(config, app)
    jwt = make_jwt(app_id, read_private_key(app))
    bearer = f"Bearer {jwt}"
    info = call("GET", "/app", bearer) or {}
    slug = info.get("slug")
    if not isinstance(slug, str) or not slug:
        raise Fail("GET /app 沒有回 slug")
    inst = call("GET", f"/repos/{REPO_OWNER}/{REPO_NAME}/installation", bearer) or {}
    inst_id = inst.get("id")
    if not isinstance(inst_id, int):
        raise Fail("取不到 installation id")
    tok = call("POST", f"/app/installations/{inst_id}/access_tokens", bearer,
               {"repositories": [REPO_NAME], "permissions": APPS[app]}) or {}
    token, expires_at = tok.get("token"), tok.get("expires_at")
    if not isinstance(token, str) or not token or not isinstance(expires_at, str):
        raise Fail("access_tokens 回應缺 token 或 expires_at")
    write_hosts(out_dir, token, slug)
    print(json.dumps({"app": app, "config_dir": str(out_dir), "expires_at": expires_at}, ensure_ascii=False))
    return 0


def revoke(out_dir: Path) -> int:
    hosts = out_dir / "hosts.yml"
    if not hosts.exists():
        print(f"{hosts} 不存在，不需撤銷", file=sys.stderr)
        return 0
    try:
        text = hosts.read_text(encoding="utf-8")
    except OSError as e:
        raise Fail(f"讀不到 {hosts}（{type(e).__name__}）") from None
    m = re.search(r"^\s*oauth_token:\s*(\S+)\s*$", text, re.M)
    if not m:
        raise Fail(f"{hosts} 沒有 oauth_token")
    call("DELETE", "/installation/token", f"token {m.group(1)}")
    hosts.unlink()
    print(f"已撤銷 token 並刪除 {hosts}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="GitHub App installation token：mint／revoke")
    ap.add_argument("command", choices=["mint", "revoke"])
    ap.add_argument("--app", required=True, help="merger 或 publisher")
    ap.add_argument("--config", default=None, help="gh-apps.json 路徑（mint 用）")
    ap.add_argument("--out-dir", default=None, help="hosts.yml 所在目錄（GH_CONFIG_DIR）")
    args = ap.parse_args(argv)

    if args.app not in APPS:
        print(f"--app 只接受 {'、'.join(APPS)}（收到：{args.app[:40]}）", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir) if args.out_dir else config_home() / "gh" / args.app
    try:
        if args.command == "mint":
            config = Path(args.config) if args.config else config_home() / "gh-apps.json"
            return mint(args.app, config, out_dir)
        return revoke(out_dir)
    except Fail as e:
        print(f"gh_app_token {args.command} 失敗：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
