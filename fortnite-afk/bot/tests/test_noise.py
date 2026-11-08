import random
import unittest

from afk.motion import CameraNoise, TurnConfig


class CameraNoiseTests(unittest.TestCase):
    def cfg(self, **overrides) -> TurnConfig:
        cfg = TurnConfig()
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg

    def test_disabled_produces_nothing(self):
        noise = CameraNoise(random.Random(1), self.cfg(noise=False))
        self.assertEqual([noise.step(0.02) for _ in range(50)], [(0, 0)] * 50)
        self.assertEqual(noise.saccades, 0)

    def test_deterministic_for_a_seed(self):
        a = CameraNoise(random.Random(7), TurnConfig())
        b = CameraNoise(random.Random(7), TurnConfig())
        self.assertEqual([a.step(0.02) for _ in range(200)],
                         [b.step(0.02) for _ in range(200)])

    def test_per_step_is_bounded(self):
        cfg = TurnConfig()
        noise = CameraNoise(random.Random(3), cfg)
        limit = (2 * cfg.noise_drift_px * 0.35 * 0.02 * 6.3
                 + cfg.noise_tremor_px + cfg.noise_saccade_px + 1)
        for _ in range(6000):
            dx, dy = noise.step(0.02)
            self.assertLessEqual(abs(dx), limit)
            self.assertLessEqual(abs(dy), cfg.noise_tremor_px + 1)

    def test_long_run_does_not_walk_away(self):
        """Alternating saccades + bounded sinusoids: the view stays near centre."""
        noise = CameraNoise(random.Random(11), TurnConfig())
        total = 0
        for _ in range(3000):  # 60 s at 50 Hz
            dx, _dy = noise.step(0.02)
            total += dx
        self.assertLess(abs(total), 80)

    def test_saccades_happen_but_are_rare(self):
        cfg = TurnConfig()
        noise = CameraNoise(random.Random(5), cfg)
        for _ in range(3000):  # 60 s
            noise.step(0.02)
        low = int(60 / cfg.noise_saccade_every_s[1]) - 1
        high = int(60 / cfg.noise_saccade_every_s[0]) + 2
        self.assertGreaterEqual(noise.saccades, max(1, low))
        self.assertLessEqual(noise.saccades, high)

    def test_zero_drift_still_trembles(self):
        noise = CameraNoise(random.Random(2), self.cfg(noise_drift_px=0.0))
        samples = [noise.step(0.02)[0] for _ in range(200)]
        self.assertTrue(any(samples))
        self.assertLessEqual(max(abs(s) for s in samples), 9)

    def test_slow_tick_scales_tremor(self):
        """A 200 ms step shakes more than a 20 ms step (perceived stillness)."""
        fast = CameraNoise(random.Random(9), TurnConfig())
        slow = CameraNoise(random.Random(9), TurnConfig())
        fast_total = sum(abs(fast.step(0.02)[0]) for _ in range(20))
        slow_total = sum(abs(slow.step(0.20)[0]) for _ in range(20))
        self.assertGreater(slow_total, fast_total)


if __name__ == "__main__":
    unittest.main()
