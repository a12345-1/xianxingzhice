# -*- coding: utf-8 -*-
"""无 FastAPI 时的本地预览服务器（只用标准库）。

用途：在没装 fastapi 的电脑上跑一遍页面，或用来截图。
生产/演示仍请用 `uvicorn server.main:app`。

    python scripts/devserver.py 8010
"""
import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import db, service  # noqa: E402

WEB = ROOT / "web"
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------------- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path):
        if not path.exists():
            return self._send(404, {"detail": "not found"})
        ext = path.suffix.lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ---------------- GET
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/health":
            with db.conn() as c:
                trips = len(c.execute("SELECT id FROM trips").fetchall())
            return self._send(200, {"ok": True, "mock": True, "poi": len(db.poi_list()), "trips": trips})
        m = re.match(r"^/api/trips/(\d+)$", p)
        if m:
            data = service.payload(int(m.group(1)))
            return self._send(200, data) if data else self._send(404, {"detail": "行程不存在"})
        if p in ("/", "/index.html"):
            return self._file(WEB / "index.html")
        if p == "/plan.html":
            return self._file(WEB / "plan.html")
        if p == "/trip.html":
            return self._file(WEB / "trip.html")
        return self._file(WEB / p.lstrip("/"))

    # ---------------- POST
    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()
        if p == "/api/parse":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, {"detail": "说一句话再试"})
            return self._send(200, service.parse_text(text))
        if p == "/api/trips":
            need = body.get("need") or {}
            tid = service.create_trip(need)
            data = service.payload(tid)
            data["id"] = tid
            return self._send(200, data)
        m = re.match(r"^/api/trips/(\d+)/days/(\d+)/regenerate$", p)
        if m:
            service.regenerate_day(int(m.group(1)), int(m.group(2)))
            data = service.payload(int(m.group(1)))
            data["id"] = int(m.group(1))
            return self._send(200, data)
        m = re.match(r"^/api/trips/(\d+)/items/(\d+)/swap$", p)
        if m:
            service.swap_item(int(m.group(1)), int(m.group(2)))
            data = service.payload(int(m.group(1)))
            data["id"] = int(m.group(1))
            return self._send(200, data)
        m = re.match(r"^/api/trips/(\d+)/members$", p)
        if m:
            merged = service.save_members(int(m.group(1)), body.get("members") or [])
            data = service.payload(int(m.group(1)))
            data["id"] = int(m.group(1))
            data["merge"] = merged
            return self._send(200, data)
        return self._send(404, {"detail": "not found"})

    # ---------------- DELETE / PATCH
    def do_DELETE(self):
        m = re.match(r"^/api/trips/(\d+)/items/(\d+)$", urlparse(self.path).path)
        if m:
            db.item_delete(int(m.group(2)))
            data = service.payload(int(m.group(1)))
            data["id"] = int(m.group(1))
            return self._send(200, data)
        return self._send(404, {"detail": "not found"})

    def do_PATCH(self):
        m = re.match(r"^/api/trips/(\d+)/items/(\d+)$", urlparse(self.path).path)
        if m:
            db.item_update(int(m.group(2)), self._body())
            data = service.payload(int(m.group(1)))
            data["id"] = int(m.group(1))
            return self._send(200, data)
        return self._send(404, {"detail": "not found"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    db.init()
    print(f"预览：http://127.0.0.1:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
