import random
import unittest

from afk.capture import Frame
from afk.config import Config
from afk.explore import frame_signature, plan_explore, signature_similarity
from afk.geometry import Box, Rect
from afk.jev import Observation


def observation(**answers):
    base = {
        "screen": {"type": "choice", "choice": "in_match", "confidence": 0.99,
                   "probabilities": {"in_match": 0.99}},
    }
    base.update(answers)
    return Observation(screen="in_match", screen_confidence=0.99,
                       screen_probabilities={"in_match": 0.99}, answers=base)


def box_answer(box, conf=0.9):
    return {"type": "box", "box": box.as_dict(), "confidence": conf}


class ExplorePlanTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.rng = random.Random(1)

    def test_enemy_visible_triggers_attack(self):
        obs = observation(
            action={"type": "choice", "choice": "move_forward", "confidence": 0.8,
                    "probabilities": {}},
            hold={"type": "choice", "choice": "tap", "confidence": 0.7,
                  "probabilities": {}},
            enemy=box_answer(Box(0.60, 0.40, 0.72, 0.62)),
            enemy_visible={"type": "noul", "noul": 0.92},
            weapon_ready={"type": "noul", "noul": 0.85},
            path={"type": "choice", "choice": "clear", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.action, "attack")
        self.assertEqual(plan.mouse, "left")
        self.assertGreater(plan.aim_norm, 0.0)
        self.assertIn("enemy", plan.reason)

    def test_near_chest_interacts(self):
        obs = observation(
            move={"type": "choice", "choice": "forward", "confidence": 0.9,
                  "probabilities": {}},
            chest_visible={"type": "noul", "noul": 0.95},
            chest=box_answer(Box(0.40, 0.30, 0.60, 0.75)),
            chest_distance={"type": "choice", "choice": "near", "confidence": 0.9,
                            "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertTrue(plan.interact)
        self.assertEqual(plan.keys, ["e"])

    def test_chest_not_near_keeps_walking(self):
        obs = observation(
            move={"type": "choice", "choice": "forward", "confidence": 0.9,
                  "probabilities": {}},
            chest_visible={"type": "noul", "noul": 0.95},
            chest=box_answer(Box(0.46, 0.50, 0.54, 0.60)),
            chest_distance={"type": "choice", "choice": "far", "confidence": 0.9,
                            "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertFalse(plan.interact)
        self.assertEqual(plan.move, "forward")
        self.assertFalse(plan.jump)

    def test_hazard_overrides_forward(self):
        obs = observation(
            move={"type": "choice", "choice": "forward", "confidence": 0.9,
                  "probabilities": {}},
            hazard_ahead={"type": "noul", "noul": 0.95},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.move, "backward")
        self.assertEqual(plan.keys, ["s"])

    def test_obstacle_turns_walk_into_jump(self):
        obs = observation(
            move={"type": "choice", "choice": "forward", "confidence": 0.9,
                  "probabilities": {}},
            obstacle_ahead={"type": "noul", "noul": 0.93},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.move, "jump_forward")
        self.assertTrue(plan.jump)
        self.assertEqual(plan.keys, ["w"])

    def test_low_confidence_move_falls_back_to_forward(self):
        obs = observation(
            move={"type": "choice", "choice": "left", "confidence": 0.1,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.move, "forward")

    def test_stop_backs_up_and_scans(self):
        obs = observation(
            move={"type": "choice", "choice": "stop", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.keys, ["s"])
        self.assertNotEqual(plan.look_dx, 0)

    def test_signature(self):
        frame = Frame(width=16, height=16, rgb=bytearray([120]) * (16 * 16 * 3),
                      rect=Rect(0, 0, 16, 16), scale=1.0, captured_at=0.0)
        a = frame_signature(frame)
        b = frame_signature(frame)
        self.assertEqual(len(a), 64)
        self.assertEqual(signature_similarity(a, b), 1.0)
        frame.rgb = bytearray([0]) * (16 * 16 * 3)
        c = frame_signature(frame)
        self.assertLess(signature_similarity(a, c), 0.6)

    def test_action_attack_hold_repeat(self):
        obs = observation(
            action={"type": "choice", "choice": "attack", "confidence": 0.9,
                    "probabilities": {}},
            hold={"type": "choice", "choice": "short", "confidence": 0.9,
                  "probabilities": {}},
            repeat={"type": "choice", "choice": "twice", "confidence": 0.9,
                    "probabilities": {}},
            path={"type": "choice", "choice": "clear", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.action, "attack")
        self.assertEqual(plan.mouse, "left")
        self.assertEqual(plan.repeat, 2)
        self.assertAlmostEqual(plan.hold_s, 0.35)

    def test_action_move_long_hold(self):
        obs = observation(
            action={"type": "choice", "choice": "move_forward", "confidence": 0.9,
                    "probabilities": {}},
            hold={"type": "choice", "choice": "long", "confidence": 0.9,
                  "probabilities": {}},
            path={"type": "choice", "choice": "clear", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.keys, ["w"])
        self.assertAlmostEqual(plan.hold_s, 1.6)

    def test_action_target_near_interacts(self):
        obs = observation(
            action={"type": "choice", "choice": "move_forward", "confidence": 0.9,
                    "probabilities": {}},
            hold={"type": "choice", "choice": "short", "confidence": 0.9,
                  "probabilities": {}},
            target_visible={"type": "noul", "noul": 0.95},
            target=box_answer(Box(0.40, 0.30, 0.60, 0.75)),
            target_kind={"type": "choice", "choice": "chest", "confidence": 0.9,
                         "probabilities": {}},
            target_distance={"type": "choice", "choice": "near", "confidence": 0.9,
                             "probabilities": {}},
            interact_ready={"type": "noul", "noul": 0.93},
            path={"type": "choice", "choice": "clear", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertTrue(plan.interact)
        self.assertEqual(plan.keys, ["e"])
        self.assertGreaterEqual(plan.hold_s, 1.0)

    def test_path_low_overrides_action(self):
        obs = observation(
            action={"type": "choice", "choice": "move_forward", "confidence": 0.9,
                    "probabilities": {}},
            hold={"type": "choice", "choice": "short", "confidence": 0.9,
                  "probabilities": {}},
            path={"type": "choice", "choice": "low", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.action, "jump_forward")
        self.assertTrue(plan.jump)

    def test_path_hazard_overrides_action(self):
        obs = observation(
            action={"type": "choice", "choice": "move_forward", "confidence": 0.9,
                    "probabilities": {}},
            path={"type": "choice", "choice": "hazard", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertEqual(plan.action, "back_up")
        self.assertEqual(plan.keys, ["s"])

    def test_action_look_left(self):
        obs = observation(
            action={"type": "choice", "choice": "look_left", "confidence": 0.9,
                    "probabilities": {}},
            path={"type": "choice", "choice": "clear", "confidence": 0.9,
                  "probabilities": {}},
        )
        plan = plan_explore(obs, self.cfg, self.rng, chest_ready=True)
        self.assertLess(plan.look_dx, 0)
        self.assertFalse(plan.jump)


if __name__ == "__main__":
    unittest.main()
