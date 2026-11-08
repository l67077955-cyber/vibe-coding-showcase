import unittest

from afk.autotune import estimate_closing_rate, estimate_shift, measure_sensitivity
from afk.capture import Frame
from afk.geometry import Rect


def make_frame(cols: int = 96, height: int = 60) -> Frame:
    """A vertical luminance pattern that is distinctive and not periodic."""
    width = cols * 4
    rgb = bytearray(width * height * 3)
    for x in range(width):
        value = (x * 37 % 251)
        for y in range(height):
            i = (y * width + x) * 3
            rgb[i] = rgb[i + 1] = rgb[i + 2] = value
    return Frame(width=width, height=height, rgb=rgb,
                 rect=Rect(0, 0, width, height), scale=1.0, captured_at=0.0)


def shift_right(frame: Frame, columns: int) -> Frame:
    width, height = frame.width, frame.height
    rgb = bytearray(width * height * 3)
    for y in range(height):
        row = y * width
        for x in range(width):
            sx = min(width - 1, max(0, x - columns))
            src = (row + sx) * 3
            dst = (row + x) * 3
            rgb[dst:dst + 3] = frame.rgb[src:src + 3]
    return Frame(width=width, height=height, rgb=rgb,
                 rect=frame.rect, scale=1.0, captured_at=0.0)


class ShiftTests(unittest.TestCase):
    def test_no_shift(self):
        frame = make_frame()
        shift, confidence = estimate_shift(frame, make_frame())
        self.assertEqual(shift, 0.0)
        self.assertGreater(confidence, 0.99)

    def test_known_shift(self):
        before = make_frame()
        after = shift_right(before, 48)  # 12 of 96 columns (4 px each) = 1/8 of the width
        shift, confidence = estimate_shift(before, after)
        self.assertAlmostEqual(shift, 12 / 96, delta=0.02)
        self.assertGreater(confidence, 0.85)

    def test_negative_shift_is_mirrored(self):
        before = make_frame()
        after = shift_right(before, -72)
        shift, _confidence = estimate_shift(before, after)
        self.assertAlmostEqual(shift, -18 / 96, delta=0.02)


class SensitivityTests(unittest.TestCase):
    def test_measure_sensitivity_math(self):
        before = make_frame()
        after = shift_right(before, 48)  # 0.125 of a screen
        result = measure_sensitivity(before, after, 180)
        self.assertTrue(result["ok"], result["reason"])
        self.assertAlmostEqual(result["px_per_screen"], 180 / 0.125, delta=60)

    def test_half_sensitivity_needs_twice_the_pixels(self):
        before = make_frame()
        # A game with half the sensitivity pans half as far for the same delta.
        after = shift_right(before, 24)
        result = measure_sensitivity(before, after, 180)
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["px_per_screen"], 180 / 0.0625, delta=60)

    def test_static_frame_is_rejected(self):
        frame = make_frame()
        result = measure_sensitivity(frame, make_frame(), 180)
        self.assertFalse(result["ok"])
        self.assertIn("barely moved", result["reason"])

    def test_tiny_delta_is_rejected(self):
        before = make_frame()
        result = measure_sensitivity(before, shift_right(before, 48), 4)
        self.assertFalse(result["ok"])


class ClosingRateTests(unittest.TestCase):
    def test_growing_target_closes_positive(self):
        rate = estimate_closing_rate(0.20, 0.25, 1.0)
        self.assertAlmostEqual(rate, 1.0, delta=1e-6)

    def test_shrinking_target_goes_negative(self):
        rate = estimate_closing_rate(0.25, 0.20, 1.0)
        self.assertLess(rate, 0.0)

    def test_invalid_inputs(self):
        self.assertIsNone(estimate_closing_rate(0.0, 0.2, 1.0))
        self.assertIsNone(estimate_closing_rate(0.2, 0.2, 0.0))


if __name__ == "__main__":
    unittest.main()
