"""End-to-end probe of the Jev `systemone` API using the bundled mock lobby.

No third-party packages: reads assets/mock_lobby.png, sends it to Jev, prints
the typed answers and box centres. Verifies key, request shape and normalised
coordinates before the real script is pointed at Fortnite.

Run:  python tools/probe_jev.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from afk.capture import Frame  # noqa: E402
from afk.config import Config  # noqa: E402
from afk.jev import JevClient  # noqa: E402


def main() -> int:
    path = ROOT / "assets" / "mock_lobby.png"
    if not path.exists():
        print(f"missing fixture: {path}", file=sys.stderr)
        return 2
    cfg = Config()
    cfg.model = "typesafe/jev-1.14"
    cfg.logging.save_frames = "off"

    frame = Frame.from_png_file(path)
    questions = {
        "screen": {
            "type": "choice",
            "instructions": "Which screen is shown?",
            "criteria": {
                "lobby": "The main menu where a match can be started",
                "in_match": "A live match with a HUD",
                "other": "Anything else",
            },
        },
        "play_button": {
            "type": "box",
            "instructions": "the large yellow PLAY button at the bottom right",
        },
        "play_button_visible": {
            "type": "noul",
            "instructions": "Is a large yellow PLAY button visible at the bottom right?",
        },
        "zero_build_tile": {
            "type": "box",
            "instructions": "the ZERO BUILD game-mode tile, not the Battle Royale tile",
        },
        "zero_build_tile_visible": {
            "type": "noul",
            "instructions": "Is a ZERO BUILD game-mode tile visible?",
        },
        "fill_toggle": {
            "type": "box",
            "instructions": "the control that turns squad FILL on or off",
        },
        "fill_toggle_visible": {
            "type": "noul",
            "instructions": "Is a squad FILL toggle visible?",
        },
        "leave_button": {
            "type": "box",
            "instructions": "the LEAVE MATCH button",
        },
        "leave_button_visible": {
            "type": "noul",
            "instructions": "Is a LEAVE MATCH button visible?",
        },
    }

    client = JevClient(cfg)
    observation = client.ask(frame, questions, context="A synthetic Fortnite lobby test image.")
    print("HTTP 200")
    print(json.dumps(
        {"model": observation.model, "screen": observation.screen,
         "screen_confidence": observation.screen_confidence,
         "usage": observation.usage, "answers": observation.answers},
        ensure_ascii=False, indent=2,
    ))
    print()
    for name, answer in observation.answers.items():
        if answer.get("type") == "box":
            box = answer["box"]
            cx = (box["left"] + box["right"]) / 2
            cy = (box["top"] + box["bottom"]) / 2
            usable = observation.usable_box(name, min_confidence=cfg.confidence.box,
                                            min_presence=cfg.confidence.presence)
            print(f"{name:22s} centre=({cx:.3f},{cy:.3f}) "
                  f"conf={answer.get('confidence')} usable={usable is not None}")
    print(f"\ntotal calls={client.calls} cost=${client.total_cost:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
