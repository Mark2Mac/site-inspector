from __future__ import annotations

import contextlib
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


class CorpusHandler(QuietHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = (
                "User-agent: *\n"
                "Allow: /\n"
                f"Sitemap: http://127.0.0.1:{self.server.server_port}/sitemap.xml\n"
            )
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if self.path == "/sitemap.xml":
            base = f"http://127.0.0.1:{self.server.server_port}"
            urls = [
                "/index.html",
                "/about.html",
                "/pricing.html",
                "/dup-a.html",
                "/dup-b.html",
                "/blog/post-1.html",
                "/resources/guide.html",
                "/noindex.html",
            ]
            items = "".join(f"<url><loc>{base}{path}</loc></url>" for path in urls)
            body = '<?xml version="1.0" encoding="UTF-8"?>' + (
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + items + '</urlset>'
            )
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        return super().do_GET()


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def fixture_site_url() -> str:
    root = Path(__file__).parent / "fixtures" / "site"
    port = _free_port()
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(root), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def fixture_corpus_url() -> str:
    root = Path(__file__).parent / "fixtures" / "corpus_site"
    port = _free_port()
    handler = lambda *args, **kwargs: CorpusHandler(*args, directory=str(root), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
