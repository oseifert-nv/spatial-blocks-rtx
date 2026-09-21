"""ovrtx renders every 3D pixel; ovstage publishes transforms and material bindings."""
from pathlib import Path
import math
import time

import numpy as np
import ovrtx
import ovstage

ROOT = Path(__file__).resolve().parent
KINDS = "IOTJLSZ"
BLOCK_COUNT, GHOST_COUNT, SPARK_COUNT, BEAM_COUNT = 216, 4, 80, 24
GHOST_START, SPARK_START, BEAM_START = 216, 220, 300
CAMERA_INDEX = 324


def transform(position, scale=(1, 1, 1), angle=0.):
    result = np.eye(4, dtype=np.float64)
    c, s = math.cos(angle), math.sin(angle)
    result[:3, :3] = np.diag(scale) @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    result[3, :3] = position
    return result


def cell_position(x, y):
    return x-4.5, 19.5-y, 0.


class RtxScene:
    def __init__(self):
        self.renderer = ovrtx.Renderer()
        self.stage = ovstage.Stage("spatial-blocks-3d")
        self.renderer.attach_ovstage(self.stage)
        self.ordinal = 1
        ovstage.population.open_usd(self.stage, str(ROOT / "assets3d/board.usda"), ordinal=1)
        self.stage.advance_write_floor(1, ovstage.Scope.ALL).wait()
        self.paths = ovstage.PathDictionary(self.stage)
        blocks = [f"/World/Blocks/B{i:03}" for i in range(BLOCK_COUNT)]
        names = blocks + [f"/World/Ghosts/G{i}" for i in range(GHOST_COUNT)]
        names += [f"/World/Sparks/S{i:03}" for i in range(SPARK_COUNT)]
        names += [f"/World/Beams/E{i:02}" for i in range(BEAM_COUNT)] + ["/World/Camera"]
        self.transform_paths = self.paths.create_path_list_from_strings(names)
        self.material_paths = self.paths.create_path_list_from_strings(blocks)
        self.transform_query = self.stage.query_from_path_list(self.transform_paths)
        self.material_query = self.stage.query_from_path_list(self.material_paths)
        self.material_ids = {k: self.paths.intern_path(f"/World/Looks/{k}") for k in KINDS}
        self.previous_materials = None
        self.matrices = np.tile(np.eye(4, dtype=np.float64), (len(names), 1, 1))
        self.yaw, self.pitch, self.distance = .178, .125, 39.94
        self.particles, self.beams = [], []
        self.rng = np.random.default_rng(142)
        self.event_count = 0
        self.last_render_ms = 0.
        self.frames = 0
        self.closed = False

    def camera(self, action, data):
        if action == "orbit":
            self.yaw = float(np.clip(self.yaw + data.get("dx", 0) * .005, -.65, .65))
            self.pitch = float(np.clip(self.pitch + data.get("dy", 0) * .004, -.02, .42))
        elif action == "zoom":
            self.distance = float(np.clip(self.distance + data.get("delta", 0) * .015, 35, 53))
        elif action == "front":
            self.yaw, self.pitch, self.distance = 0., 0., 39.
        elif action == "angle":
            self.yaw, self.pitch, self.distance = .178, .125, 39.94

    def effect(self, before, after, now, hard_drop=False):
        if after["pieces"] <= before["pieces"]:
            return
        self.event_count += 1
        cells = before["ghost"] if hard_drop else before["active"]["cells"]
        cleared = after["cleared_rows"]
        origins = [cell_position(x, y) for x, y in cells]
        if cleared:
            origins = [cell_position(x, y) for y in cleared for x in range(10)]
            for y in cleared:
                self.beams.append(dict(start=now, life=.55, row=y))
        if hard_drop:
            for (x, y), (_, end_y) in zip(before["active"]["cells"], cells):
                if end_y > y+1:
                    self.beams.append(dict(start=now, life=.26, x=x, y=y, end_y=end_y))
        count = min(SPARK_COUNT, 16 + 14 * len(cleared))
        for i in range(count):
            p = np.array(origins[i % len(origins)]) + (0, 0, .5)
            velocity = self.rng.uniform([-3., 1.5, 1.], [3., 5., 5.])
            self.particles.append(dict(start=now, life=float(self.rng.uniform(.35, .85)),
                                       p=p, v=velocity, size=float(self.rng.uniform(.045, .1))))
        self.particles = self.particles[-SPARK_COUNT:]
        self.beams = self.beams[-BEAM_COUNT:]

    def update(self, state, now):
        self.ordinal += 1
        self.matrices[:] = transform((0, -25, 0), (.0001, .0001, .0001))
        materials = ["I"] * BLOCK_COUNT
        for b in state["board"]:
            index = b["y"] * 10 + b["x"]
            self.matrices[index] = transform(cell_position(b["x"], b["y"]))
            materials[index] = b["kind"]
        if state["phase"] not in ("over", "error"):
            for i, (x, y) in enumerate(state["active"]["cells"]):
                if y >= 0:
                    self.matrices[200+i] = transform(cell_position(x, y))
                materials[200+i] = state["active"]["kind"]
            for i, (x, y) in enumerate(state["ghost"]):
                if y >= 0:
                    self.matrices[GHOST_START+i] = transform(cell_position(x, y))
        # Next pieces float beside the frame in the same rendered scene.
        for item, piece in enumerate(state["next"]):
            xs, ys = zip(*piece["cells"])
            cx, cy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
            for i, (x, y) in enumerate(piece["cells"]):
                index = 204+item*4+i
                self.matrices[index] = transform((7.3+(x-cx)*.58, 17.3-item*2.6-(y-cy)*.58, -.1), (.55, .55, .55))
                materials[index] = piece["kind"]
        self.particles = [p for p in self.particles if now-p["start"] < p["life"]]
        for i, p in enumerate(self.particles):
            t = now-p["start"]
            position = p["p"] + p["v"]*t + (0, -6*t*t, 0)
            size = p["size"]*(1-t/p["life"])
            self.matrices[SPARK_START+i] = transform(position, (size, size, size*2.5), t*8)
        self.beams = [b for b in self.beams if now-b["start"] < b["life"]]
        for i, beam in enumerate(self.beams):
            t = (now-beam["start"])/beam["life"]
            if "row" in beam:
                scale = (10.5*(1+t*.25), .16*(1-t), .12*(1-t))
                position = (0, 19.5-beam["row"], .65+t*3)
            else:
                height = beam["end_y"]-beam["y"]
                scale = (.085*(1-t), height*(1-t), .06*(1-t))
                position = (beam["x"]-4.5, 19.5-beam["end_y"]+height*(1-t)/2, .6)
            self.matrices[BEAM_START+i] = transform(position, scale)
        cp = math.cos(self.pitch)
        w = np.array([math.sin(self.yaw)*cp, math.sin(self.pitch), math.cos(self.yaw)*cp])
        u = np.cross([0, 1, 0], w); u /= np.linalg.norm(u)
        v = np.cross(w, u)
        cam = np.eye(4, dtype=np.float64)
        cam[:3, :3] = [u, v, w]
        cam[3, :3] = np.array([0, 10, 0])+w*self.distance
        self.matrices[CAMERA_INDEX] = cam
        self.stage.write_attribute(self.transform_query, "omni:xform", ordinal=self.ordinal,
                                   tensors=self.matrices, is_array=False).wait()
        if materials != self.previous_materials:
            values = [np.array([self.material_ids[k]], dtype=np.uint64) for k in materials]
            self.stage.write_attribute(self.material_query, "material:binding", ordinal=self.ordinal,
                                       tensors=values, is_array=True,
                                       semantic=ovstage.AttributeSemantic.RELATIONSHIP_PATH_ID).wait()
            self.previous_materials = materials
        self.stage.advance_write_floor(self.ordinal, ovstage.Scope.ALL).wait()

    def render(self):
        start = time.perf_counter()
        products = self.renderer.step(render_products={"/Render/Game"}, delta_time=1/30, ordinal=self.ordinal)
        try:
            frame = products["/Render/Game"].frames[-1]
            var = frame.render_vars["/Render/Game/LdrColor"].map(device=ovrtx.Device.CPU)
            try:
                view = np.from_dlpack(var)
                pixels = view.copy()
                del view
            finally:
                var.unmap()
                del var
            del frame
        finally:
            del products
        self.last_render_ms = (time.perf_counter()-start)*1000
        self.frames += 1
        return pixels

    def warm_up(self, state, stopped):
        # Warm the actual spark and beam geometry before the first user action.
        # Inactive pools below the floor do not exercise their visible GPU paths.
        now = time.monotonic()
        self.particles = [dict(start=now, life=1., p=np.array([i%10-4.5, 2.+i//10, .8]),
                               v=np.zeros(3), size=.08) for i in range(SPARK_COUNT)]
        self.beams = [dict(start=now, life=1., row=y) for y in range(16,20)]
        for _ in range(8):
            if stopped.is_set():
                break
            self.update(state, now+.05)
            self.render()
        self.particles.clear(); self.beams.clear()
        self.update(state, time.monotonic())
        for _ in range(32):
            if stopped.is_set():
                break
            self.render()

    def close(self):
        if self.closed:
            return
        self.transform_query.release().wait()
        self.material_query.release().wait()
        self.paths.destroy_path_list(self.transform_paths)
        self.paths.destroy_path_list(self.material_paths)
        self.paths.destroy()
        self.renderer.detach_ovstage()
        self.stage.destroy()
        self.renderer.destroy()
        self.closed = True


if __name__ == "__main__":
    import argparse
    import json
    from PIL import Image
    from game import Game
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="qa-output/rtx-first.png")
    args = parser.parse_args()
    game = Game(seed=7)
    scene = RtxScene()
    try:
        # A deterministic sample stack makes shading and colored materials visible.
        for x, height in enumerate([2, 2, 3, 1, 4, 3, 2, 3, 2, 1]):
            for y in range(20-height, 20):
                game.board[(x, y)] = (game.next_id, KINDS[(x+y)//2 % 7])
                game.next_id += 1
        game.spatial.publish(game.board)
        game.active = __import__('game').Piece("T", x=4, y=6)
        state = game.snapshot()
        scene.update(state, time.monotonic())
        for _ in range(48):
            pixels = scene.render()
        path = ROOT / args.output
        path.parent.mkdir(exist_ok=True)
        Image.fromarray(pixels).save(path)
        print(json.dumps({"image":str(path), "shape":pixels.shape, "render_ms":scene.last_render_ms,
                          "frames":scene.frames, "ordinal":scene.ordinal}))
    finally:
        scene.close()
        game.close()
