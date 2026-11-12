"""Read-only HTTP hosting for *explicit* synthetic test media fixtures.

Only local fixture files are served. Paths outside the fixture directory,
including symlinks, are refused. No QQ/NapCat/Tencent dependencies.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import secrets
import threading
from urllib.parse import quote, unquote, urlsplit


class FixtureMediaServer:
    def __init__(self, directory: Path, *, bind_host: str = "127.0.0.1",
                 port: int = 0, public_host: str = "127.0.0.1",
                 size_limit: int = 64 * 1024 * 1024):
        self.root = directory.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("fixture directory must be a directory")
        self.size_limit = size_limit
        self.token = secrets.token_urlsafe(20)
        self.public_host = public_host
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                prefix = "/fixtures/" + owner.token + "/"
                path = urlsplit(self.path).path
                if not path.startswith(prefix):
                    self.send_error(404)
                    return
                relative = unquote(path[len(prefix):])
                if not relative or relative.startswith("/") or "\x00" in relative:
                    self.send_error(400)
                    return
                candidate = (owner.root / relative).resolve()
                if candidate == owner.root or not candidate.is_relative_to(owner.root):
                    self.send_error(403)
                    return
                if not candidate.is_file():
                    self.send_error(404)
                    return
                length = candidate.stat().st_size
                if length > owner.size_limit:
                    self.send_error(413)
                    return
                mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with candidate.open("rb") as stream:
                    while part := stream.read(64 * 1024):
                        self.wfile.write(part)

            def log_message(self, fmt, *args):
                pass

        self.httpd = ThreadingHTTPServer((bind_host, port), Handler)
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_port

    def url(self, filename: str) -> str:
        file_path = (self.root / filename).resolve()
        if file_path == self.root or not file_path.is_relative_to(self.root) or not file_path.is_file():
            raise ValueError("fixture path outside directory or missing")
        if file_path.stat().st_size > self.size_limit:
            raise ValueError("fixture exceeds size limit")
        path = quote(file_path.relative_to(self.root).as_posix(), safe="/")
        return f"http://{self.public_host}:{self.port}/fixtures/{self.token}/{path}"

    def start(self) -> None:
        if self.thread:
            return
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=3)
