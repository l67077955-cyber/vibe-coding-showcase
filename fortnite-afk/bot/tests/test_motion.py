import math
import random
import unittest

from afk.motion import (
    TurnConfig,
    aim_px,
    jitter,
    plan_turn,
    scan_delta,
    smoothstep,
    turn_duration,
)

CFG = TurnConfig()
CAP = CFG.max_px_per_s * CFG.tick_s * 1.6
LIMIT = int(round(CFG.max_step_px))


def expected_total(dx: int) -> int:
    """plan_turn clamps a single decision to max_step_px (sign preserved)."""
    return (1 if dx > 0 else -1) * min(abs(dx), LIMIT)


class SmoothstepTests(unittest.TestCase):
    def test_bounds_and_midpoint(self):
        self.assertEqual(smoothstep(0.0), 0.0)
        self.assertEqual(smoothstep(1.0), 1.0)
        self.assertAlmostEqual(smoothstep(0.5), 0.5, places=12)

    def test_clamped_outside_unit_interval(self):
        self.assertEqual(smoothstep(-3.0), 0.0)
        self.assertEqual(smoothstep(4.0), 1.0)

    def test_monotonic(self):
        values = [smoothstep(i / 100.0) for i in range(101)]
        for a, b in zip(values, values[1:]):
            self.assertLessEqual(a, b)


class PlanTurnTests(unittest.TestCase):
    def test_sum_is_exact_over_sampled_range(self):
        # -500..500 step 7 is mostly inside the max_step_px budget; values
        # beyond it are clamped, so the invariant is "sum == clamped delta".
        for dx in range(-500, 501, 7):
            self.assertEqual(sum(plan_turn(dx)), expected_total(dx), msg=f"dx={dx}")

    def test_sum_is_exact_within_budget(self):
        for dx in range(-LIMIT, LIMIT + 1):
            self.assertEqual(sum(plan_turn(dx)), dx, msg=f"dx={dx}")

    def test_sum_is_exact_for_random_values(self):
        rng = random.Random(20261108)
        for _ in range(500):
            dx = rng.randint(-LIMIT, LIMIT)
            self.assertEqual(sum(plan_turn(dx)), dx, msg=f"dx={dx}")
            big = rng.randint(-100000, 100000)
            self.assertEqual(sum(plan_turn(big)), expected_total(big), msg=f"dx={big}")

    def test_negative_is_exact_mirror(self):
        for dx in range(1, LIMIT + 1):
            right = plan_turn(dx)
            left = plan_turn(-dx)
            self.assertEqual(left, [-step for step in right], msg=f"dx={dx}")

    def test_ease_in_and_out_at_300(self):
        steps = [abs(step) for step in plan_turn(300)]
        peak = max(steps)
        self.assertLess(steps[0], peak, "turn should start slowly")
        self.assertLess(steps[-1], peak, "turn should end slowly")
        self.assertLess(steps[0], peak / 2.0)
        self.assertLess(steps[-1], peak / 2.0)

    def test_speed_cap(self):
        ceiling = math.ceil(CAP)
        cases = list(range(-500, 501, 7)) + [-100000, 100000, 420, -420]
        for dx in cases:
            for step in plan_turn(dx):
                self.assertLessEqual(abs(step), ceiling, msg=f"dx={dx} step={step}")

    def test_zero_is_empty(self):
        self.assertEqual(plan_turn(0), [])

    def test_tiny_delta_still_gets_min_ticks(self):
        steps = plan_turn(5)
        self.assertEqual(sum(steps), 5)
        self.assertGreaterEqual(len(steps), CFG.min_ticks)
        self.assertTrue(any(step != 0 for step in steps))

    def test_length_bounds(self):
        for dx in range(1, LIMIT + 1, 3):
            self.assertGreaterEqual(len(plan_turn(dx)), CFG.min_ticks)
            self.assertLessEqual(len(plan_turn(dx)), CFG.max_ticks)


class AimPxTests(unittest.TestCase):
    def test_centre_is_zero(self):
        self.assertEqual(aim_px(0.5, 1920), 0)

    def test_deadzone(self):
        frame = 1920
        edge = 0.5 + CFG.deadzone_px / frame / 2.0
        self.assertEqual(aim_px(edge, frame), 0)
        self.assertEqual(aim_px(0.5 - CFG.deadzone_px / frame / 2.0, frame), 0)

    def test_sign(self):
        self.assertGreater(aim_px(0.75, 1920), 0)
        self.assertLess(aim_px(0.25, 1920), 0)

    def test_matches_gain_away_from_edges(self):
        self.assertEqual(aim_px(0.6, 1000), int(round((0.6 - 0.5) * 1000 * CFG.gain)))

    def test_clamped_to_max_step(self):
        self.assertEqual(aim_px(1.0, 1920), LIMIT)
        self.assertEqual(aim_px(0.0, 1920), -LIMIT)
        self.assertEqual(aim_px(1.0, 100000), LIMIT)

    def test_bad_frame_width(self):
        self.assertEqual(aim_px(0.9, 0), 0)
        self.assertEqual(aim_px(0.9, -100), 0)


class JitterTests(unittest.TestCase):
    def test_within_band(self):
        rng = random.Random(7)
        for seconds in (0.8, 0.35, 2.0, 0.05):
            for _ in range(200):
                value = jitter(seconds, rng, amount=0.12)
                self.assertGreaterEqual(value, seconds * 0.88)
                self.assertLessEqual(value, seconds * 1.12)

    def test_floor(self):
        rng = random.Random(7)
        self.assertEqual(jitter(0.0, rng), 0.01)
        self.assertGreaterEqual(jitter(0.001, rng), 0.01)

    def test_custom_amount(self):
        rng = random.Random(11)
        value = jitter(1.0, rng, amount=0.5)
        self.assertGreaterEqual(value, 0.5)
        self.assertLessEqual(value, 1.5)


class ScanDeltaTests(unittest.TestCase):
    def test_direction_zero(self):
        rng = random.Random(3)
        self.assertEqual(scan_delta(rng, 0, 1920), 0)

    def test_sign(self):
        rng = random.Random(3)
        self.assertGreater(scan_delta(rng, 1, 1920), 0)
        self.assertLess(scan_delta(rng, -1, 1920), 0)

    def test_magnitude_band(self):
        rng = random.Random(5)
        base = 1920 * 0.16
        for _ in range(300):
            value = abs(scan_delta(rng, 1, 1920))
            self.assertGreaterEqual(value, base * 0.75 - 0.5)
            self.assertLessEqual(value, base * 1.25 + 0.5)

    def test_custom_magnitude(self):
        rng = random.Random(5)
        base = 1000 * 0.05
        value = abs(scan_delta(rng, -1, 1000, magnitude=0.05))
        self.assertGreaterEqual(value, base * 0.75 - 0.5)
        self.assertLessEqual(value, base * 1.25 + 0.5)


class TurnDurationTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(turn_duration([]), 0.0)

    def test_matches_tick_count(self):
        steps = plan_turn(300)
        self.assertAlmostEqual(turn_duration(steps), len(steps) * CFG.tick_s, places=12)

    def test_respects_custom_tick(self):
        self.assertAlmostEqual(turn_duration([1, 2, 3], TurnConfig(tick_s=0.05)), 0.15, places=12)


if __name__ == "__main__":
    unittest.main()
