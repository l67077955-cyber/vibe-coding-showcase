import logging
import random
import unittest

from afk.capture import Frame
from afk.config import Config
from afk.controller import AfkController
from afk.explore import ExplorePlan
from afk.geometry import Rect
from afk.motion import aim_px
from afk.sim import (FakeCapture, FakeInput, FakeWindow, MockGame, ScriptedVision,
                     VirtualClock)


def make_controller(cycles=1, explore=True):
    cfg = Config()
    cfg.mode.setup = "verify"
    cfg.timing.match_minutes = (0.2, 0.2)
    cfg.timing.lobby_cooldown_s = 1.0
    cfg.timing.queue_poll_s = 2.0
    cfg.timing.match_check_s = 30.0
    cfg.explore.enabled = explore
    cfg.explore.interval_s = (1.0, 1.0)
    cfg.cloud.pause_when_disconnected = False
    cfg.safety.max_cycles = cycles
    cfg.safety.focus_on_start = False
    cfg.logging.save_frames = "off"
    clock = VirtualClock()
    game = MockGame(clock)
    vision = ScriptedVision(game)
    inputs = FakeInput(clock, game)
    controller = AfkController(
        cfg, window=FakeWindow(), capture=FakeCapture(), inputs=inputs, vision=vision,
        clock=clock, sleeper=clock.sleep, panic=lambda: False, rng=random.Random(7),
    )
    return controller, game, vision, inputs


class SimulationTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_vertical_aim_moves_the_mouse_down(self):
        """The camera must tilt as well as pan: dy has to be non-zero."""
        controller, _game, _vision, inputs = make_controller(cycles=1)
        controller.cfg.turn.noise = False
        controller.last_frame = Frame(width=768, height=432, rgb=None,
                                      rect=Rect(0, 0, 768, 432), scale=1.0,
                                      captured_at=0.0)
        plan = ExplorePlan(keys=[], hold_s=0.2, aim_norm_y=0.30, action="stop")
        inputs.actions.clear()
        controller._execute_plan(plan, now=0.0)
        looks = [a for a in inputs.actions if a[0] == "look"]
        self.assertTrue(looks)
        self.assertGreater(sum(a[1][1] for a in looks), 0)

    def test_smooth_turn_is_many_small_steps(self):
        """One decision must not whip the camera in a single 300 px jump."""
        controller, _game, _vision, inputs = make_controller(cycles=1)
        controller.cfg.turn.noise = False  # exact-sum invariant, noise adds tremor
        controller.last_frame = Frame(width=768, height=432, rgb=None,
                                      rect=Rect(0, 0, 768, 432), scale=1.0,
                                      captured_at=0.0)
        plan = ExplorePlan(keys=[], hold_s=0.2, aim_norm=0.30, action="stop")
        inputs.actions.clear()
        controller._execute_plan(plan, now=0.0)
        looks = [a for a in inputs.actions if a[0] == "look" and a[1][1] == 0]
        self.assertGreaterEqual(len(looks), 8)
        expected = aim_px(0.80, 768, controller.cfg.turn)
        self.assertGreater(expected, 0)
        self.assertEqual(sum(a[1][0] for a in looks), expected)
        self.assertLessEqual(max(abs(a[1][0]) for a in looks), 40)

    def test_turn_with_noise_stays_on_target(self):
        """Hand tremor must not throw the turn off by more than a few pixels."""
        controller, _game, _vision, inputs = make_controller(cycles=1)
        controller.cfg.turn.noise = True
        controller.last_frame = Frame(width=768, height=432, rgb=None,
                                      rect=Rect(0, 0, 768, 432), scale=1.0,
                                      captured_at=0.0)
        plan = ExplorePlan(keys=[], hold_s=0.2, aim_norm=0.30, action="stop")
        inputs.actions.clear()
        controller._execute_plan(plan, now=0.0)
        looks = [a for a in inputs.actions if a[0] == "look"]
        expected = aim_px(0.80, 768, controller.cfg.turn)
        total = sum(a[1][0] for a in looks)
        self.assertLessEqual(abs(total - expected), 40)

    def test_move_and_turn_overlap(self):
        """Walking and turning must overlap, not happen in two separate beats."""
        controller, _game, _vision, inputs = make_controller(cycles=1)
        controller.cfg.turn.noise = False
        controller.last_frame = Frame(width=768, height=432, rgb=None,
                                      rect=Rect(0, 0, 768, 432), scale=1.0,
                                      captured_at=0.0)
        plan = ExplorePlan(keys=["w"], hold_s=0.5, aim_norm=0.30,
                           action="move_forward", continuous=True)
        inputs.actions.clear()
        controller._execute_plan(plan, now=0.0)
        kinds = [a[0] for a in inputs.actions]
        self.assertIn("down", kinds)
        self.assertIn("look", kinds)
        self.assertLess(kinds.index("down"), kinds.index("look"))
        self.assertNotIn("up", kinds)  # keys stay held for the next decision

    def test_aim_gain_adapts_to_result(self):
        controller, _game, _vision, _inputs = make_controller(cycles=1)
        controller._aim_gain = 0.60
        controller._last_aim = (0.30, 200)
        plan = ExplorePlan(keys=[], hold_s=0.2, aim_norm=0.05, action="stop")
        controller._adapt_aim(plan)
        self.assertGreater(controller._aim_gain, 0.60)

        controller._aim_gain = 0.60
        controller._last_aim = (0.30, 200)
        plan = ExplorePlan(keys=[], hold_s=0.2, aim_norm=0.45, action="stop")
        controller._adapt_aim(plan)
        self.assertLess(controller._aim_gain, 0.60)

    def test_full_cycle_with_explore(self):
        controller, game, vision, inputs = make_controller(cycles=1)
        summary = controller.run()
        self.assertEqual(summary.cycles, 1)
        self.assertIn(("hold", ("e",)), inputs.actions)
        self.assertIn(("press", "space"), inputs.actions)
        self.assertIn(("mouse_down", "left"), inputs.actions)
        self.assertIn(("mouse_up", "left"), inputs.actions)
        self.assertTrue(any(a[0] == "click" for a in inputs.actions))
        self.assertEqual(game.state, "lobby")

    def test_two_cycles_requeue(self):
        controller, game, vision, inputs = make_controller(cycles=2)
        summary = controller.run()
        self.assertEqual(summary.cycles, 2)
        play_clicks = [a for a in inputs.actions if a[0] == "click"]
        self.assertGreaterEqual(len(play_clicks), 2)
        self.assertGreaterEqual(game.escapes, 2)

    def test_results_screen_returns_to_lobby(self):
        controller, game, vision, inputs = make_controller(cycles=1)
        game.leave_to_results = True
        summary = controller.run()
        self.assertEqual(summary.cycles, 1)
        self.assertEqual(game.state, "lobby")

    def test_no_explore_random_afk(self):
        controller, game, vision, inputs = make_controller(cycles=1, explore=False)
        summary = controller.run()
        self.assertEqual(summary.cycles, 1)
        holds = [a for a in inputs.actions if a[0] == "hold"]
        self.assertTrue(holds)


if __name__ == "__main__":
    unittest.main()
