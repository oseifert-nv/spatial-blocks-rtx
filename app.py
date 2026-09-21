"""Local-only desktop game server. Run with the repository's bootstrapped Python."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
from pathlib import Path
import threading
import time
import webbrowser

from game import Game

ROOT = Path(__file__).resolve().parent
ACTIONS = {"tick", "start", "left", "right", "down", "rotate", "rotate_ccw", "drop", "pause", "pause_only", "restart"}
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css"), "/app.js": ("app.js", "text/javascript")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    logging.basicConfig(filename=ROOT / "game.log", level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        game = Game(args.seed)
    except Exception:
        logging.exception("Native library startup failed")
        raise

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *values):
            if len(values) < 2 or str(values[1]) not in ("200", "204"):
                logging.info(fmt, *values)

        def send(self, status, data, content_type="application/json"):
            payload = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def allowed(self):
            authority = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == authority and self.headers.get("Origin", f"http://{authority}") == f"http://{authority}"

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {"error": "This game accepts local requests only."})
            if self.path == "/api/state":
                return self.send(200, game.snapshot())
            if self.path == "/api/health":
                return self.send(200, {"app": "spatial-blocks", "pid": os.getpid()})
            if self.path in ASSETS:
                name, content_type = ASSETS[self.path]
                return self.send(200, (ROOT / "web" / name).read_bytes(), content_type)
            self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.allowed() or self.headers.get("Content-Type") != "application/json":
                return self.send(403, {"error": "Invalid request origin or content type."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/shutdown":
                    self.send(200, {"stopped": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if self.path != "/api/action" or not isinstance(data, dict) or data.get("action") not in ACTIONS:
                    return self.send(400, {"error": "Unknown game action"})
                game.command(data["action"])
                self.send(200, game.snapshot())
            except (ValueError, TypeError) as error:
                self.send(400, {"error": str(error)})
            except Exception as error:
                logging.exception("Game operation failed")
                game.phase = "error"
                game.error = str(error)
                self.send(500, {"error": f"Spatial query failed: {error}"})

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    runtime = ROOT / "runtime.json"
    runtime.write_text(json.dumps({"url": url, "pid": os.getpid(), "started": time.time()}), encoding="utf-8")
    logging.info("Started %s with native library %s", url, game.spatial.library_path)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        game.close()
        if runtime.exists() and json.loads(runtime.read_text()).get("pid") == os.getpid():
            runtime.unlink()
        logging.info("Stopped cleanly")


if __name__ == "__main__":
    main()
