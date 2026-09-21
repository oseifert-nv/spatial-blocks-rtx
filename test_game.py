"""Integration tests using the built CPU DLL; no spatial mocks or fallbacks."""
from dataclasses import replace
import unittest

from game import Game, Piece, SHAPES


class NativeGameTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(seed=7)
        self.addCleanup(self.game.close)
        self.game.command("start")
        self.now = self.game.last_gravity

    def populate(self, positions):
        self.game.board = {}
        for position in positions:
            self.game.board[position] = (self.game.next_id, "J")
            self.game.next_id += 1
        self.game.spatial.publish(self.game.board)

    def test_real_query_distinguishes_occupied_and_touching_cells(self):
        self.populate([(4, 10)])
        native = self.game.spatial
        self.assertTrue(native.occupied(4, 10))
        for x, y in [(3, 10), (5, 10), (4, 9), (4, 11)]:
            self.assertFalse(native.occupied(x, y))
        self.assertEqual(native.stats()["engine"], "ovspatialquery")
        self.assertEqual(native.stats()["objects"], 1)

    def test_move_uses_native_collision_and_respects_walls(self):
        self.populate([(6, 5)])
        self.game.active = Piece("O", x=3, y=5)
        self.assertTrue(self.game.valid(self.game.active))
        before = self.game.spatial.queries
        self.assertFalse(self.game.move(1, 0, self.now))
        self.assertEqual(self.game.active.x, 3)
        self.assertGreater(self.game.spatial.queries, before)
        self.assertTrue(self.game.move(-1, 0, self.now))
        self.game.active = Piece("O", x=-1, y=5)
        self.assertFalse(self.game.move(-1, 0, self.now))

    def test_i_rotation_kicks_away_from_right_wall(self):
        self.game.active = Piece("I", x=7, y=8, rotation=1)
        self.assertTrue(self.game.valid(self.game.active))
        self.game.rotate(1, self.now)
        self.assertEqual(self.game.active.rotation, 2)
        self.assertEqual(self.game.active.x, 6)
        self.assertTrue(self.game.valid(self.game.active))

    def test_fully_obstructed_rotation_leaves_piece_unchanged(self):
        original = Piece("T", x=3, y=6)
        cells = set(original.cells())
        self.populate([(x, y) for x in range(10) for y in range(3, 12) if (x, y) not in cells])
        self.game.active = original
        self.assertTrue(self.game.valid(original))
        self.game.rotate(1, self.now)
        self.assertEqual(self.game.active, original)
        self.assertEqual(self.game.action_result, "Blocked")

    def test_ghost_and_hard_drop_stop_above_obstacle(self):
        self.populate([(4, 18)])
        self.game.active = Piece("O", x=3, y=0)
        landing = self.game.ghost()
        self.assertEqual(landing.y, 16)
        self.assertFalse(self.game.valid(replace(landing, y=17)))
        self.game.command("drop", self.now)
        self.assertEqual(self.game.score, 32)
        self.assertEqual(self.game.pieces, 1)
        self.assertEqual(len(self.game.board), 5)
        for position in landing.cells():
            self.assertTrue(self.game.spatial.occupied(*position))

    def test_four_line_clear_moves_survivor_and_preserves_identity(self):
        self.populate([(x, y) for y in range(16, 20) for x in range(10) if x != 4] + [(0, 15)])
        survivor = self.game.board[(0, 15)]
        ordinal = self.game.spatial.ordinal
        self.game.active = Piece("I", x=2, y=16, rotation=1)
        self.assertTrue(self.game.valid(self.game.active))
        self.game.lock(self.now)
        self.assertEqual(self.game.lines, 4)
        self.assertEqual(self.game.score, 800)
        self.assertEqual(self.game.board, {(0, 19): survivor})
        self.assertEqual(self.game.spatial.ordinal, ordinal + 1)
        self.assertTrue(self.game.spatial.occupied(0, 19))
        self.assertFalse(self.game.spatial.occupied(0, 15))
        self.assertFalse(self.game.spatial.occupied(4, 19))

    def test_soft_drop_and_level_progression(self):
        self.game.active = Piece("O", x=3, y=3)
        self.game.command("down", self.now)
        self.assertEqual(self.game.active.y, 4)
        self.assertEqual(self.game.score, 1)
        first_interval = self.game.fall_interval
        self.game.lines = 10
        self.assertEqual(self.game.level, 2)
        self.assertLess(self.game.fall_interval, first_interval)

    def test_gravity_pause_resume_and_lock_delay(self):
        original = self.game.active
        self.game.advance(self.now + 0.81)
        self.assertEqual(self.game.active.y, original.y + 1)
        self.game.command("pause", self.now + 1)
        paused = self.game.active
        self.game.advance(self.now + 100)
        self.assertEqual(self.game.active, paused)
        self.game.command("start", self.now + 100)
        self.game.advance(self.now + 100.1)
        self.assertEqual(self.game.active, paused)
        self.game.active = Piece("O", x=3, y=18)
        self.game.advance(self.now + 100.2)
        self.game.advance(self.now + 100.6)
        self.assertEqual(self.game.pieces, 0)
        self.game.advance(self.now + 100.71)
        self.assertEqual(self.game.pieces, 1)

    def test_lock_delay_cannot_be_reset_indefinitely(self):
        self.game.active = Piece("O", x=3, y=18)
        self.game._update_grounding(self.now)
        for index in range(16):
            self.game.move(1 if index % 2 == 0 else -1, 0, self.now + 0.01 * (index + 1))
        self.assertEqual(self.game.lock_resets, 15)
        self.game.advance(self.now + 0.66)
        self.assertEqual(self.game.pieces, 1)

    def test_spawn_collision_and_top_out(self):
        self.populate([(4, 0)])
        self.game.queue.insert(0, "O")
        self.game.spawn(self.now)
        self.assertEqual(self.game.phase, "over")
        self.game.reset()
        self.game.active = Piece("O", y=-1)
        self.game.lock(self.now)
        self.assertEqual(self.game.phase, "over")
        self.assertEqual(self.game.board, {})

    def test_each_bag_has_all_seven_shapes(self):
        sequence = [self.game.active.kind] + self.game.queue
        self.assertEqual(set(sequence[:7]), set(SHAPES))
        self.assertEqual(len(sequence[:7]), 7)

    def test_restart_removes_boxes_without_reusing_identities(self):
        for _ in range(4):
            self.game.command("drop", self.game.last_gravity)
            first_ids = {item[0] for item in self.game.board.values()}
            self.game.command("restart")
            self.assertEqual(self.game.spatial.stats()["objects"], 0)
            self.assertFalse(self.game.spatial.occupied(4, 19))
            self.game.command("drop", self.game.last_gravity)
            second_ids = {item[0] for item in self.game.board.values()}
            self.assertTrue(first_ids.isdisjoint(second_ids))
            self.game.command("restart")
        self.game.close()
        self.game.close()  # Cleanup is safe to call twice.


if __name__ == "__main__":
    unittest.main()
