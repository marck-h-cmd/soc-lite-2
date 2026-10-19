"""SOC-Lite · Servidor estático de la SPA + proxy de la API.

Sirve `frontend/dist` en http://localhost:5173 y reenvía `/api/*` al backend
FastAPI (http://127.0.0.1:8000), replicando el proxy que define `vite.config.ts`
para el modo desarrollo. Sirve para demostrar la aplicación sin necesidad de
ejecutar Vite (útil en entornos donde no se pueden lanzar procesos hijos).

Uso:
    python scripts/serve_frontend.py [--port 5173] [--api http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


def build_handler(api_base: str):
    api_base = api_base.rstrip("/")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "SOC-LiteStatic/1.0"

        # ----------------------------------------------------------
        # Utilidades
        # ----------------------------------------------------------
        def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _proxy(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            payload = self.rfile.read(length) if length else None

            url = api_base + self.path
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            request = urllib.request.Request(url, data=payload, headers=headers, method=self.command)
            try:
                with urllib.request.urlopen(request, timeout=180) as upstream:
                    body = upstream.read()
                    status = upstream.status
                    resp_headers = {
                        k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP
                    }
                    content_type = upstream.headers.get("Content-Type", "application/json")
            except urllib.error.HTTPError as exc:  # 4xx/5xx del backend: se propagan tal cual
                body = exc.read()
                status = exc.code
                resp_headers = {k: v for k, v in exc.headers.items() if k.lower() not in HOP_BY_HOP}
                content_type = exc.headers.get("Content-Type", "application/json")
            except Exception as exc:  # backend caído
                body = f'{{"detail":"Backend no disponible: {exc}"}}'.encode("utf-8")
                status = 502
                resp_headers = {}
                content_type = "application/json"

            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in resp_headers.items():
                if key.lower() in {"content-type", "content-length"}:
                    continue
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _static(self) -> None:
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            candidate = (DIST / path.lstrip("/")).resolve()
            # Sin path traversal fuera de dist/
            if DIST.resolve() not in candidate.parents and candidate != DIST.resolve():
                self._send(403, b"Forbidden", "text/plain; charset=utf-8")
                return

            if candidate.is_dir():
                candidate = candidate / "index.html"
            if not candidate.exists():
                # Fallback SPA: cualquier ruta del router de React devuelve index.html
                candidate = DIST / "index.html"

            content = candidate.read_bytes()
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            if candidate.suffix == ".html":
                content_type = "text/html; charset=utf-8"
                extra = {"Cache-Control": "no-store"}
            elif candidate.suffix in {".js", ".css"}:
                extra = {"Cache-Control": "public, max-age=31536000, immutable"}
            else:
                extra = {"Cache-Control": "public, max-age=3600"}
            self._send(200, content, content_type, extra)

        # ----------------------------------------------------------
        # Verbos HTTP
        # ----------------------------------------------------------
        def _dispatch(self) -> None:
            if self.path.startswith("/api/"):
                self._proxy()
            elif self.path == "/healthz":
                self._send(200, b'{"status":"ok"}', "application/json")
            else:
                self._static()

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_HEAD(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def do_PUT(self) -> None:  # noqa: N802
            self._dispatch()

        def do_PATCH(self) -> None:  # noqa: N802
            self._dispatch()

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Allow", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
            sys.stderr.write("[ui] " + fmt % args + "\n")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Sirve la SPA de SOC-Lite y hace proxy de /api")
    parser.add_argument("--port", type=int, default=int(os.getenv("FRONTEND_PORT", "5173")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api", default=os.getenv("API_TARGET", "http://127.0.0.1:8000"))
    args = parser.parse_args()

    if not (DIST / "index.html").exists():
        raise SystemExit(f"No existe {DIST/'index.html'}: ejecute antes `pnpm build` en frontend/.")

    server = ThreadingHTTPServer((args.host, args.port), build_handler(args.api))
    print(f"SOC-Lite UI en http://{args.host}:{args.port}  ->  API {args.api}/api/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
