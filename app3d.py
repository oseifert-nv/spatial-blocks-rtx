"""Loopback UI with one owner thread for gameplay, ovstage and ovrtx."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
from queue import Queue, Empty, Full
import threading
import time
from urllib.parse import urlparse, parse_qs

from PIL import Image
from game import Game, Piece
from renderer3d import RtxScene

ROOT = Path(__file__).resolve().parent
GAME_ACTIONS = {"start", "restart", "pause", "pause_only", "left", "right", "down", "rotate", "rotate_ccw", "drop"}
CAMERA_ACTIONS = {"orbit", "zoom", "front", "angle"}
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css"), "/app.js": ("app.js", "text/javascript")}


def run(args):
    logging.basicConfig(filename=ROOT / "game3d.log", level=logging.INFO, format="%(asctime)s %(message)s")
    commands = Queue(maxsize=64)
    stop = threading.Event()
    condition = threading.Condition()
    shared = {"state": {"ready":False, "phase":"loading", "message":"Starting the RTX renderer…"},
              "jpeg":None, "sequence":0, "error":None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *values):
            if len(values) < 2 or str(values[1]) not in ("200", "204"):
                logging.info(fmt, *values)

        def allowed(self):
            authority = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == authority and self.headers.get("Origin", f"http://{authority}") == f"http://{authority}"

        def send(self, status, data, content_type="application/json", headers=None):
            payload = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'")
            for name, value in (headers or {}).items():
                self.send_header(name, str(value))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {"error":"Local requests only"})
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                return self.send(200, {"app":"spatial-blocks-3d", "pid":os.getpid(), "ready":shared["state"].get("ready",False)})
            if parsed.path == "/api/state":
                with condition:
                    state = shared["state"]
                return self.send(200, state)
            if parsed.path == "/frame.jpg":
                try:
                    after = int(parse_qs(parsed.query).get("after", ["-1"])[0])
                except ValueError:
                    return self.send(400, {"error":"Invalid frame number"})
                with condition:
                    condition.wait_for(lambda:shared["sequence"]>after or stop.is_set(), timeout=1)
                    jpeg, sequence = shared["jpeg"], shared["sequence"]
                if jpeg is None:
                    return self.send(204, b"", "image/jpeg")
                return self.send(200, jpeg, "image/jpeg", {"X-Frame":sequence})
            if parsed.path in ASSETS:
                name, content_type = ASSETS[parsed.path]
                return self.send(200, (ROOT / "web3d" / name).read_bytes(), content_type)
            self.send(404, {"error":"Not found"})

        def do_POST(self):
            if not self.allowed() or self.headers.get("Content-Type") != "application/json":
                return self.send(403, {"error":"Invalid request origin or content type"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/shutdown":
                    self.send(200, {"stopped":True})
                    stop.set()
                    return
                if self.path != "/api/action" or not isinstance(data, dict) or data.get("action") not in GAME_ACTIONS|CAMERA_ACTIONS:
                    raise ValueError("Unknown game action")
                for key in ("dx", "dy", "delta"):
                    value = data.get(key, 0)
                    if not isinstance(value, (float, int)) or not math.isfinite(value) or abs(value)>2000:
                        raise ValueError("Invalid camera input")
                if not shared["state"].get("ready"):
                    return self.send(409, {"error":"The RTX renderer is still starting"})
                request = {"data":data, "done":threading.Event(), "result":None}
                commands.put_nowait(request)
                if not request["done"].wait(timeout=10):
                    return self.send(503, {"error":"The renderer did not respond in time"})
                return self.send(200, request["result"])
            except Full:
                self.send(429, {"error":"Input queue is full"})
            except (ValueError, TypeError) as error:
                self.send(400, {"error":str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    runtime = ROOT / "runtime3d.json"
    runtime.write_text(json.dumps({"url":url, "pid":os.getpid(), "started":time.time()}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.info("Starting %s", url)
    game = scene = None
    try:
        game = Game(args.seed)
        scene = RtxScene()
        if args.test_scenario:
            for y in range(16, 20):
                for x in range(10):
                    if x != 4:
                        game.board[x,y] = (game.next_id, "IOTJLSZ"[(x+y)%7])
                        game.next_id += 1
            game.spatial.publish(game.board)
            game.active = Piece("I", x=2, y=3, rotation=1)
        scene.warm_up(game.snapshot(), stop)
        fps, previous = 0., time.monotonic()
        while not stop.is_set():
            started = time.monotonic()
            pending = []
            while True:
                try:
                    request = commands.get_nowait()
                except Empty:
                    break
                data = request["data"]
                before = game.snapshot()
                if data["action"] in CAMERA_ACTIONS:
                    scene.camera(data["action"], data)
                else:
                    game.command(data["action"], started)
                    if data["action"] == "restart":
                        scene.particles.clear(); scene.beams.clear()
                    scene.effect(before, game.snapshot(), started, data["action"]=="drop")
                pending.append(request)
            before = game.snapshot()
            game.advance(started)
            state = game.snapshot()
            scene.effect(before, state, started)
            scene.update(state, started)
            pixels = scene.render()
            buffer = BytesIO()
            Image.fromarray(pixels).convert("RGB").save(buffer, format="JPEG", quality=91, subsampling=0)
            now = time.monotonic()
            instantaneous = 1/max(now-previous, .001)
            fps = instantaneous if fps==0 else .9*fps+.1*instantaneous
            previous = now
            state["ready"] = True
            state["renderer"] = dict(engine="ovrtx", mode="RealTimePathTracing", frames=scene.frames,
                                     fps=round(fps,1), render_ms=round(scene.last_render_ms,1), ordinal=scene.ordinal,
                                     effects=scene.event_count, particles=len(scene.particles),
                                     camera=[scene.yaw, scene.pitch, scene.distance])
            with condition:
                shared["state"], shared["jpeg"] = state, buffer.getvalue()
                shared["sequence"] += 1
                condition.notify_all()
            for request in pending:
                request["result"] = state
                request["done"].set()
            target = 30 if game.phase == "playing" or scene.particles else 12
            stop.wait(max(0, 1/target-(time.monotonic()-started)))
    except Exception as error:
        logging.exception("3D engine failed")
        with condition:
            shared["state"] = {"ready":False, "phase":"error", "message":str(error)}
            condition.notify_all()
        # Keep the diagnostic page available, but stop issuing native operations.
        while not stop.wait(.2):
            pass
    finally:
        if scene is not None:
            scene.close()
        if game is not None:
            game.close()
        server.shutdown()
        server.server_close()
        if runtime.exists() and json.loads(runtime.read_text()).get("pid")==os.getpid():
            runtime.unlink()
        logging.info("Stopped cleanly")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--test-scenario", action="store_true", help="Start with a deterministic four-line clearance for integration testing")
    run(parser.parse_args())
