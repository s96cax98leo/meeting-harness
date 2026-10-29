"""替身 GitHub API（http.server 執行緒，只綁 127.0.0.1），給 gh_app_token 的測試用（spec §4.4）。

記錄每個請求（method、path、headers、body），依 routes 回應；沒列到的路徑回 404。
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INSTALLATION_ID = 4242
SLUG = "mh-example-merger"
TOKEN = "fake-installation-token-for-tests-0001"
EXPIRES_AT = "2026-10-29T13:00:00Z"
REPO_PATH = "/repos/s96cax98leo/meeting-harness/installation"


def default_routes() -> dict:
    return {
        ("GET", "/app"): (200, {"id": 1, "slug": SLUG}),
        ("GET", REPO_PATH): (200, {"id": INSTALLATION_ID}),
        ("POST", f"/app/installations/{INSTALLATION_ID}/access_tokens"): (201, {"token": TOKEN, "expires_at": EXPIRES_AT}),
        ("DELETE", "/installation/token"): (204, None),
    }


class FakeGitHub:
    def __init__(self, routes: dict | None = None):
        self.routes = routes or default_routes()
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 不印到 stderr
                pass

            def _handle(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode("utf-8") if n else ""
                path = self.path.split("?", 1)[0]
                outer.requests.append({"method": self.command, "path": path,
                                       "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                status, payload = outer.routes.get((self.command, path), (404, {"message": "Not Found"}))
                data = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                if data:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

            do_GET = do_POST = do_DELETE = do_PATCH = do_PUT = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def find(self, method: str, path: str) -> list[dict]:
        return [r for r in self.requests if r["method"] == method and r["path"] == path]
