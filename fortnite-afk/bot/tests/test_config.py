import json
import os
import tempfile
import unittest
from pathlib import Path

from afk.config import Config, ConfigError, load_config, resolve_api_key


class ConfigTests(unittest.TestCase):
    def test_example_config(self):
        cfg = load_config(Path(__file__).resolve().parents[1] / "config.example.json")
        self.assertEqual(cfg.model, "typesafe/jev-1.14")
        self.assertEqual(cfg.explore.interval_s, (2.5, 4.0))
        self.assertTrue(cfg.mode.zero_build)

    def test_tuple_coercion_and_unknown_key(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "c.json"
            path.write_text(json.dumps({"timing": {"match_minutes": [1, 2]}}), encoding="utf-8")
            cfg = load_config(path)
            self.assertEqual(cfg.timing.match_minutes, (1.0, 2.0))
            path.write_text(json.dumps({"nope": 1}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_api_key_env_and_inline(self):
        cfg = Config()
        cfg.api_key_env = "AFK_TEST_KEY"
        os.environ["AFK_TEST_KEY"] = "sk-test"
        try:
            self.assertEqual(resolve_api_key(cfg), "sk-test")
        finally:
            del os.environ["AFK_TEST_KEY"]
        cfg.api_key = "sk-inline"
        self.assertEqual(resolve_api_key(cfg), "sk-inline")

    def test_invalid_interval(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "c.json"
            path.write_text(json.dumps({"explore": {"interval_s": [5, 1]}}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
