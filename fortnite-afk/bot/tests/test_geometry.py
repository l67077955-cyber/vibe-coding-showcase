import unittest

from afk.geometry import Box, Rect, box_center_screen, box_to_screen, parse_box


class GeometryTests(unittest.TestCase):
    def test_center(self):
        self.assertEqual(Box(0.1, 0.2, 0.5, 0.6).center, (0.3, 0.4))

    def test_screen_mapping(self):
        rect = Rect(100, 200, 1000, 500)
        box = Box(0.25, 0.10, 0.75, 0.90)
        self.assertEqual(box_to_screen(box, rect), (350, 250, 850, 650))
        self.assertEqual(box_center_screen(box, rect), (600, 450))

    def test_parse_swapped_edges(self):
        box = parse_box({"left": 0.8, "right": 0.2, "top": 0.9, "bottom": 0.1})
        self.assertEqual((box.left, box.right, box.top, box.bottom), (0.2, 0.8, 0.1, 0.9))

    def test_parse_clamps_small_overflow(self):
        box = parse_box({"left": -0.05, "right": 1.05, "top": 0.2, "bottom": 0.7})
        self.assertEqual((box.left, box.right), (0.0, 1.0))

    def test_parse_rejects_garbage(self):
        self.assertIsNone(parse_box({"left": 0.5, "right": 0.5, "top": 0.2, "bottom": 0.7}))
        self.assertIsNone(parse_box({"left": -2, "right": 0.5, "top": 0.2, "bottom": 0.7}))
        self.assertIsNone(parse_box("nope"))


if __name__ == "__main__":
    unittest.main()
