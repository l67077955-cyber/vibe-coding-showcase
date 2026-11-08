import unittest

from afk.jev import Observation


def obs(answers):
    return Observation(screen="lobby", screen_confidence=0.9, screen_probabilities={},
                       answers=answers)


class ObservationTests(unittest.TestCase):
    def test_usable_box(self):
        o = obs({
            "play": {"type": "box", "confidence": 0.8,
                     "box": {"left": 0.1, "top": 0.1, "right": 0.2, "bottom": 0.2}},
            "play_visible": {"type": "noul", "noul": 0.9},
        })
        self.assertIsNotNone(o.usable_box("play", min_confidence=0.35))

    def test_low_confidence_rejected(self):
        o = obs({
            "play": {"type": "box", "confidence": 0.05,
                     "box": {"left": 0.1, "top": 0.1, "right": 0.2, "bottom": 0.2}},
            "play_visible": {"type": "noul", "noul": 0.9},
        })
        self.assertIsNone(o.usable_box("play", min_confidence=0.35))

    def test_low_presence_rejected(self):
        o = obs({
            "play": {"type": "box", "confidence": 0.9,
                     "box": {"left": 0.1, "top": 0.1, "right": 0.2, "bottom": 0.2}},
            "play_visible": {"type": "noul", "noul": 0.1},
        })
        self.assertIsNone(o.usable_box("play", min_confidence=0.35))

    def test_null_confidence(self):
        o = obs({
            "play": {"type": "box", "confidence": None,
                     "box": {"left": 0.1, "top": 0.1, "right": 0.2, "bottom": 0.2}},
            "play_visible": {"type": "noul", "noul": 0.9},
        })
        self.assertIsNotNone(o.usable_box("play", min_confidence=0.35, allow_null=True))
        self.assertIsNone(o.usable_box("play", min_confidence=0.35, allow_null=False))

    def test_huge_box_rejected(self):
        o = obs({
            "play": {"type": "box", "confidence": 0.9,
                     "box": {"left": 0.01, "top": 0.01, "right": 0.99, "bottom": 0.99}},
            "play_visible": {"type": "noul", "noul": 0.9},
        })
        self.assertIsNone(o.usable_box("play", min_confidence=0.35, max_side=0.92))

    def test_choice_and_noul(self):
        o = obs({
            "move": {"type": "choice", "choice": "forward_left", "confidence": 0.7,
                     "probabilities": {}},
            "chest": {"type": "noul", "noul": 0.83},
        })
        self.assertEqual(o.choice("move"), ("forward_left", 0.7))
        self.assertAlmostEqual(o.noul("chest"), 0.83)


if __name__ == "__main__":
    unittest.main()
