"""revoke 遇到 token 已失效（deliver 審查 bugs-1）：凍結與 token 外洩程序正是 DELETE 回 401／403／404 的情境，
此時仍要刪掉本機 hosts.yml、exit 0；其他錯誤（例如 500）維持 exit 2、不刪檔。"""
import os
import shutil
import unittest

from tests.governance.fake_github import SLUG, TOKEN, FakeGitHub, default_routes
from tests.governance import test_app_token as base


class RevokeExpiredTest(unittest.TestCase):
    # 沿用 test_app_token 的替身環境；只借方法、不繼承，避免重跑那邊的測試
    setUp = base.AppTokenTest.setUp
    tool = base.AppTokenTest.tool
    env = base.AppTokenTest.env
    out_dir = base.AppTokenTest.out_dir

    def hosts_file(self):
        out = self.out_dir()
        out.mkdir(parents=True)
        os.chmod(out, 0o700)
        hosts = out / "hosts.yml"
        hosts.write_text(f"github.com:\n    oauth_token: {TOKEN}\n    user: {SLUG}[bot]\n    git_protocol: https\n", encoding="utf-8")
        os.chmod(hosts, 0o600)
        return out, hosts

    def routes(self, status):
        r = default_routes()
        r[("DELETE", "/installation/token")] = (status, {"message": "Bad credentials"})
        return r

    def test_revoke_deletes_hosts_when_token_invalid(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                out, hosts = self.hosts_file()
                try:
                    with FakeGitHub(self.routes(status)) as api:
                        r = self.tool(api, "revoke", "--app", "merger", "--out-dir", str(out))
                        self.assertEqual(r.returncode, 0, r.stderr)
                        self.assertEqual(len(api.find("DELETE", "/installation/token")), 1)
                    self.assertFalse(hosts.exists(), f"DELETE 回 {status} 時也要刪掉 hosts.yml")
                    self.assertNotIn(TOKEN, r.stdout + r.stderr, "不得印出 token")
                finally:
                    shutil.rmtree(out, ignore_errors=True)

    def test_revoke_keeps_hosts_on_other_errors(self):
        out, hosts = self.hosts_file()
        with FakeGitHub(self.routes(500)) as api:
            r = self.tool(api, "revoke", "--app", "merger", "--out-dir", str(out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertTrue(hosts.exists(), "非失效類錯誤不得刪檔")
        self.assertNotIn(TOKEN, r.stdout + r.stderr, "不得印出 token")


if __name__ == "__main__":
    unittest.main()
