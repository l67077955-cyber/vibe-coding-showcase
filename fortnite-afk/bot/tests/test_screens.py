import unittest

from afk.screens import questions_for


class ScreenQuestionTests(unittest.TestCase):
    def test_explore_questions(self):
        q = questions_for("explore")
        for key in ("screen", "move", "action", "hold", "repeat", "target_visible",
                    "target", "target_kind", "target_distance", "interact_ready", "path",
                    "chest_visible", "chest", "chest_distance", "obstacle_ahead",
                    "hazard_ahead", "eliminated", "look_around"):
            self.assertIn(key, q)
        self.assertEqual(q["action"]["type"], "choice")
        self.assertIn("jump_forward", q["action"]["criteria"])
        self.assertIn("long", q["hold"]["criteria"])
        self.assertIn("three_times", q["repeat"]["criteria"])

    def test_lobby_boxes_have_presence_companion(self):
        q = questions_for("lobby")
        boxes = [name for name, spec in q.items() if spec.get("type") == "box"]
        self.assertTrue(boxes)
        for name in boxes:
            self.assertIn(f"{name}_visible", q, f"{name} has no presence Noul")

    def test_results_play_again(self):
        q = questions_for("results")
        self.assertIn("play_again_button", q)
        self.assertIn("return_lobby_button", q)


if __name__ == "__main__":
    unittest.main()
