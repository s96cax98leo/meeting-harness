"""spec §4.4.1–§4.4.5：tools/merge_gate_project/gh_app_token.py（由 app-tools 轉綠）。

測試金鑰在執行時以 `openssl genrsa` 產生在暫存目錄，不 commit 任何金鑰；`security` 用 fakes/security 替身
（MH_GH_APP_SECURITY），API 用 fake_github 替身（MH_GH_API_BASE）；HOME 指到暫存目錄，不碰真的 ~/.config。
"""
import base64
import json
import os
import shutil
import stat
import unittest
from pathlib import Path

from tests.governance import fake_github
from tests.governance.fake_github import EXPIRES_AT, INSTALLATION_ID, SLUG, TOKEN, FakeGitHub
from tests.governance.support import APP_TOKEN, FAKES, PY, run, tmpdir

APP_IDS = {"merger": 111111, "publisher": 222222}
PERMS = {"merger": {"contents": "write", "pull_requests": "write"},
         "publisher": {"contents": "read", "pull_requests": "write"}}
TOKENS_PATH = f"/app/installations/{INSTALLATION_ID}/access_tokens"


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class AppTokenTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(APP_TOKEN.is_file(), "tools/merge_gate_project/gh_app_token.py 不存在")
        self.assertIsNotNone(shutil.which("openssl"), "找不到 openssl")
        self.base = tmpdir(self, "mh-apptoken-")
        self.home = self.base / "home"
        self.home.mkdir()
        self.tmp = self.base / "tmp"
        self.tmp.mkdir()
        self.cwd = self.base / "cwd"
        self.cwd.mkdir()
        keys = self.base / "keys"
        keys.mkdir()
        self.pem = keys / "test.pem"
        self.pub = keys / "test.pub.pem"
        r = run(["openssl", "genrsa", "-out", str(self.pem), "2048"])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(["openssl", "rsa", "-in", str(self.pem), "-pubout", "-out", str(self.pub)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.config = self.base / "gh-apps.json"
        self.config.write_text(json.dumps({k: {"app_id": v} for k, v in APP_IDS.items()}), encoding="utf-8")
        self.sec_log = self.base / "security.log"

    def out_dir(self, app="merger") -> Path:
        return self.base / "out" / app

    def env(self, api: FakeGitHub, **extra) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("MH_GH_", "FAKE_SECURITY", "GH_"))}
        env.update({
            "HOME": str(self.home), "TMPDIR": str(self.tmp), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
            "MH_GH_APP_SECURITY": str(FAKES / "security"), "MH_GH_API_BASE": api.base,
            "FAKE_SECURITY_PEM": str(self.pem), "FAKE_SECURITY_LOG": str(self.sec_log),
        })
        env.update(extra)
        return env

    def tool(self, api, *args, **extra):
        return run([PY, str(APP_TOKEN), *args], env=self.env(api, **extra), cwd=self.cwd)

    def mint(self, api, app="merger", **extra):
        return self.tool(api, "mint", "--app", app, "--config", str(self.config), "--out-dir", str(self.out_dir(app)), **extra)

    def test_mint_writes_hosts(self):
        """§4.4.1：寫出 §2.2 格式的 hosts.yml（目錄 0700、檔 0600、user 為 <slug>[bot]），stdout 恰為三鍵 JSON。"""
        with FakeGitHub() as api:
            r = self.mint(api)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.out_dir()
        hosts = out / "hosts.yml"
        self.assertTrue(hosts.is_file(), "沒有寫出 hosts.yml")
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(hosts.stat().st_mode), 0o600)
        want = f"github.com:\n    oauth_token: {TOKEN}\n    user: {SLUG}[bot]\n    git_protocol: https\n"
        self.assertEqual(hosts.read_text(encoding="utf-8").rstrip("\n") + "\n", want)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, f"stdout 應只有一行 JSON：{len(lines)} 行")
        obj = json.loads(lines[0])
        self.assertEqual(sorted(obj), ["app", "config_dir", "expires_at"])
        self.assertEqual(obj["app"], "merger")
        self.assertEqual(Path(obj["config_dir"]).resolve(), out.resolve())
        self.assertEqual(obj["expires_at"], EXPIRES_AT)
        self.assertEqual([p.name for p in out.iterdir()], ["hosts.yml"], "out-dir 只應留下 hosts.yml（暫存檔要 rename 掉）")

    def test_no_secret_leak(self):
        """§4.4.2：mint、revoke 的輸出與 TMPDIR、out-dir 以外的新檔不含 token、JWT、PRIVATE KEY；TMPDIR 不留私鑰。"""
        def snapshot():
            return {p for p in self.base.rglob("*") if p.is_file()}
        before = snapshot()
        with FakeGitHub() as api:
            r1 = self.mint(api)
            r2 = self.tool(api, "revoke", "--app", "merger", "--out-dir", str(self.out_dir()))
            jwts = [q["headers"].get("authorization", "").split()[-1] for q in api.find("GET", "/app")]
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue(jwts and jwts[0].count(".") == 2, "GET /app 應帶 Bearer JWT")
        secrets = [TOKEN, jwts[0], "PRIVATE KEY"]
        for r in (r1, r2):
            for s in secrets:
                self.assertNotIn(s, r.stdout)
                self.assertNotIn(s, r.stderr)
        new = snapshot() - before - {self.sec_log}
        for p in new:
            if self.tmp in p.parents or self.out_dir() in p.parents:
                continue
            data = p.read_text(encoding="utf-8", errors="replace")
            for s in secrets:
                self.assertNotIn(s, data, f"{p.relative_to(self.base)} 含機敏字串")
        for p in self.tmp.rglob("*"):
            if p.is_file():
                self.assertNotIn("PRIVATE KEY", p.read_text(encoding="utf-8", errors="replace"), "TMPDIR 留下私鑰")

    def test_request_shape(self):
        """§4.4.3：access_tokens 請求的 permissions、repositories；JWT 的 iss、exp-iat、alg 與簽章。"""
        for app in ("merger", "publisher"):
            with self.subTest(app=app), FakeGitHub() as api:
                r = self.mint(api, app)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(len(api.find("GET", "/app")), 1)
                self.assertEqual(len(api.find("GET", fake_github.REPO_PATH)), 1)
                posts = api.find("POST", TOKENS_PATH)
                self.assertEqual(len(posts), 1)
                body = json.loads(posts[0]["body"])
                self.assertEqual(body.get("repositories"), ["meeting-harness"])
                self.assertEqual(body.get("permissions"), PERMS[app])
                for q in (api.find("GET", "/app")[0], posts[0]):
                    auth = q["headers"].get("authorization", "")
                    self.assertTrue(auth.startswith("Bearer "), f"{q['path']} 要以 Bearer JWT 認證")
                jwt = api.find("GET", "/app")[0]["headers"]["authorization"].split()[-1]
                h, p, s = jwt.split(".")
                header, claims = json.loads(b64url_decode(h)), json.loads(b64url_decode(p))
                self.assertEqual(header.get("alg"), "RS256")
                self.assertEqual(str(claims.get("iss")), str(APP_IDS[app]))
                self.assertLessEqual(int(claims["exp"]) - int(claims["iat"]), 600)
                sig_in, sig = self.base / f"{app}.in", self.base / f"{app}.sig"
                sig_in.write_bytes(f"{h}.{p}".encode("ascii"))
                sig.write_bytes(b64url_decode(s))
                v = run(["openssl", "dgst", "-sha256", "-verify", str(self.pub), "-signature", str(sig), str(sig_in)])
                self.assertEqual(v.returncode, 0, f"JWT 簽章驗不過：{v.stdout}{v.stderr}")
        calls = [json.loads(ln) for ln in self.sec_log.read_text(encoding="utf-8").splitlines()]
        for app in ("merger", "publisher"):
            self.assertTrue(any("find-generic-password" in c and f"meeting-harness.gh-app.{app}" in c and "-w" in c for c in calls),
                            f"應以 security find-generic-password -s meeting-harness.gh-app.{app} -w 取私鑰")

    def test_failures(self):
        """§4.4.4：--app gate／未知值、security 失敗、API 4xx（含 403 suspended）都 exit 2，且不留 hosts.yml。"""
        def check(r, app="merger"):
            self.assertEqual(r.returncode, 2, f"stdout={r.stdout!r} stderr={r.stderr[-300:]!r}")
            self.assertFalse((self.out_dir(app) / "hosts.yml").exists(), "失敗時不得留下 hosts.yml")
            self.assertNotIn("PRIVATE KEY", r.stdout + r.stderr)

        with FakeGitHub() as api:
            check(self.mint(api, "gate"), "gate")
            check(self.mint(api, "unknown"), "unknown")
            check(self.mint(api, FAKE_SECURITY_FAIL="1"))
        suspended = fake_github.default_routes()
        suspended[("POST", TOKENS_PATH)] = (403, {"message": "This installation has been suspended"})
        with FakeGitHub(suspended) as api:
            check(self.mint(api))
        no_install = fake_github.default_routes()
        no_install[("GET", fake_github.REPO_PATH)] = (404, {"message": "Not Found"})
        with FakeGitHub(no_install) as api:
            check(self.mint(api))
        bad_jwt = fake_github.default_routes()
        bad_jwt[("GET", "/app")] = (401, {"message": "A JSON web token could not be decoded"})
        with FakeGitHub(bad_jwt) as api:
            check(self.mint(api))

    def test_revoke(self):
        """§4.4.5：revoke 以 hosts.yml 的 token 送 DELETE /installation/token 並刪檔；檔不存在時 exit 0 且不送請求。"""
        out = self.out_dir()
        out.mkdir(parents=True)
        os.chmod(out, 0o700)
        hosts = out / "hosts.yml"
        hosts.write_text(f"github.com:\n    oauth_token: {TOKEN}\n    user: {SLUG}[bot]\n    git_protocol: https\n", encoding="utf-8")
        os.chmod(hosts, 0o600)
        with FakeGitHub() as api:
            r = self.tool(api, "revoke", "--app", "merger", "--out-dir", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            dels = api.find("DELETE", "/installation/token")
            self.assertEqual(len(dels), 1, "應送出一次 DELETE /installation/token")
            self.assertTrue(dels[0]["headers"].get("authorization", "").endswith(TOKEN), "DELETE 要用 hosts.yml 的 token 認證")
            self.assertFalse(hosts.exists(), "revoke 後要刪掉 hosts.yml")
            n = len(api.requests)
            r2 = self.tool(api, "revoke", "--app", "merger", "--out-dir", str(out))
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertEqual(len(api.requests), n, "hosts.yml 不存在時不得送請求")


if __name__ == "__main__":
    unittest.main()
