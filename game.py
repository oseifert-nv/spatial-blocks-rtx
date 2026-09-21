"""Falling-block rules; all settled-block collision checks use SpatialBoard."""
from __future__ import annotations

from dataclasses import dataclass, replace
import random
import time

from spatial_backend import SpatialBoard

WIDTH, HEIGHT = 10, 20
SHAPES = {
    "I": ((0, 1), (1, 1), (2, 1), (3, 1)),
    "O": ((1, 0), (2, 0), (1, 1), (2, 1)),
    "T": ((1, 0), (0, 1), (1, 1), (2, 1)),
    "J": ((0, 0), (0, 1), (1, 1), (2, 1)),
    "L": ((2, 0), (0, 1), (1, 1), (2, 1)),
    "S": ((1, 0), (2, 0), (0, 1), (1, 1)),
    "Z": ((0, 0), (1, 0), (1, 1), (2, 1)),
}
# SRS wall kicks in board coordinates (positive y points downward).
JLSTZ_KICKS = {
    (0, 1): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (1, 0): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (1, 2): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (2, 1): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (2, 3): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (3, 2): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (3, 0): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (0, 3): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
}
I_KICKS = {
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)),
}


@dataclass(frozen=True)
class Piece:
    kind: str
    x: int = 3
    y: int = -1
    rotation: int = 0

    def cells(self):
        points = SHAPES[self.kind]
        if self.kind != "O":
            size = 4 if self.kind == "I" else 3
            for _ in range(self.rotation % 4):
                points = tuple((size - 1 - y, x) for x, y in points)
        return tuple((self.x + x, self.y + y) for x, y in points)


class Game:
    def __init__(self, seed=None):
        self.spatial = SpatialBoard()
        self.rng = random.Random(seed)
        self.next_id = 1  # Object identities never repeat during this population's lifetime.
        self.error = None
        self.reset(playing=False)

    @property
    def level(self):
        return 1 + self.lines // 10

    @property
    def fall_interval(self):
        return max(0.08, 0.8 * 0.8 ** (self.level - 1))

    def reset(self, playing=True):
        self.board = {}
        self.spatial.publish(self.board)
        self.score = self.lines = self.pieces = 0
        self.queue = []
        self.phase = "playing" if playing else "ready"
        self.message = "Find your rhythm."
        self.action_result = "Ready"
        self.last_clear = []
        self.event_id = 0
        self.error = None
        self._ghost_key = None
        self._fill_queue()
        self.spawn(time.monotonic())

    def _fill_queue(self):
        while len(self.queue) < 7:
            bag = list(SHAPES)
            self.rng.shuffle(bag)
            self.queue.extend(bag)

    def spawn(self, now):
        self.active = Piece(self.queue.pop(0))
        self._fill_queue()
        self.last_gravity = now
        self.grounded_at = None
        self.lock_resets = 0
        if not self.valid(self.active):
            self.phase = "over"
            self.message = "The stack reached the top."

    def valid(self, piece):
        cells = piece.cells()
        if any(x < 0 or x >= WIDTH or y >= HEIGHT or y < -4 for x, y in cells):
            return False
        return not any(self.spatial.occupied(x, y) for x, y in cells)

    def move(self, dx, dy, now):
        candidate = replace(self.active, x=self.active.x + dx, y=self.active.y + dy)
        if not self.valid(candidate):
            self.action_result = "Blocked"
            if dy > 0 and self.grounded_at is None:
                self.grounded_at = now
            return False
        self.active = candidate
        self.action_result = "Clear"
        self._update_grounding(now, reset=dx != 0)
        return True

    def _update_grounding(self, now, reset=False):
        if self.valid(replace(self.active, y=self.active.y + 1)):
            self.grounded_at = None
        elif self.grounded_at is None:
            self.grounded_at = now
        elif reset and self.lock_resets < 15:
            self.grounded_at = now
            self.lock_resets += 1

    def rotate(self, direction, now):
        if self.active.kind == "O":
            return
        rotation = (self.active.rotation + direction) % 4
        table = I_KICKS if self.active.kind == "I" else JLSTZ_KICKS
        for dx, dy in table[(self.active.rotation, rotation)]:
            candidate = replace(self.active, rotation=rotation, x=self.active.x + dx, y=self.active.y + dy)
            if self.valid(candidate):
                self.active = candidate
                self.action_result = "Clear"
                self._update_grounding(now, reset=True)
                return
        self.action_result = "Blocked"

    def ghost(self):
        key = (self.active, self.spatial.ordinal)
        if key != self._ghost_key:
            piece = self.active
            while self.valid(replace(piece, y=piece.y + 1)):
                piece = replace(piece, y=piece.y + 1)
            self._ghost = piece
            self._ghost_key = key
        return self._ghost

    def lock(self, now):
        if any(y < 0 for _, y in self.active.cells()):
            self.phase = "over"
            self.message = "The stack reached the top."
            return
        for position in self.active.cells():
            self.board[position] = (self.next_id, self.active.kind)
            self.next_id += 1
        full = [y for y in range(HEIGHT) if sum((x, y) in self.board for x in range(WIDTH)) == WIDTH]
        self.last_clear = full
        if full:
            self.board = {(x, y + sum(row > y for row in full)): block for (x, y), block in self.board.items() if y not in full}
            self.score += (0, 100, 300, 500, 800)[len(full)] * self.level
            self.lines += len(full)
            self.message = ("", "Single line", "Double line", "Triple line", "Four lines!")[len(full)]
        else:
            self.message = "Piece settled."
        self.pieces += 1
        self.event_id += 1
        self.spatial.publish(self.board)
        self.spawn(now)

    def advance(self, now):
        if self.phase != "playing":
            return
        for _ in range(4):
            if now - self.last_gravity < self.fall_interval:
                break
            self.last_gravity += self.fall_interval
            if not self.move(0, 1, now):
                self.last_gravity = now
                break
        self._update_grounding(now)
        if self.grounded_at is not None and now - self.grounded_at >= 0.5:
            self.lock(now)

    def command(self, action, now=None):
        now = time.monotonic() if now is None else now
        if action == "restart":
            self.reset()
            return
        if action == "start":
            if self.phase in ("ready", "paused"):
                self.phase = "playing"
                self.last_gravity = now
                self.grounded_at = None
            elif self.phase == "over":
                self.reset()
            return
        if action in ("pause", "pause_only"):
            if self.phase == "playing":
                self.phase = "paused"
            elif self.phase == "paused" and action == "pause":
                self.command("start", now)
            return
        if self.phase != "playing":
            return
        self.advance(now)
        if self.phase != "playing":
            return
        if action == "left":
            self.move(-1, 0, now)
        elif action == "right":
            self.move(1, 0, now)
        elif action == "down":
            if self.move(0, 1, now):
                self.score += 1
            self.last_gravity = now
        elif action in ("rotate", "rotate_ccw"):
            self.rotate(1 if action == "rotate" else -1, now)
        elif action == "drop":
            landing = self.ghost()
            self.score += 2 * (landing.y - self.active.y)
            self.active = landing
            self.lock(now)

    def snapshot(self):
        ghost = self.ghost() if self.phase != "error" else self.active
        return dict(phase=self.phase, score=self.score, lines=self.lines, level=self.level, pieces=self.pieces,
                    board=[dict(x=x, y=y, kind=kind, id=identity) for (x, y), (identity, kind) in self.board.items()],
                    active=dict(kind=self.active.kind, cells=self.active.cells(), rotation=self.active.rotation),
                    ghost=ghost.cells(), next=[dict(kind=k, cells=SHAPES[k]) for k in self.queue[:3]],
                    engine=self.spatial.stats(), message=self.message, action_result=self.action_result,
                    event_id=self.event_id, cleared_rows=self.last_clear, error=self.error)

    def close(self):
        self.spatial.close()
