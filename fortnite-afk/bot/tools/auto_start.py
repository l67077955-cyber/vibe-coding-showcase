#!/usr/bin/env python
"""Let Jev decide what to click until a match starts, then move.

Screen capture in, SendInput out, no window handles. Every iteration asks the
model what screen this is, which button advances the goal, and where that
button is; the code clicks exactly that box.

    python tools/auto_start.py --act --move-seconds 6
    python tools/auto_start.py --dry-run --steps 4
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from afk import cloud  # noqa: E402
from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.explore import frame_signature, signature_similarity  # noqa: E402
from afk.geometry import Rect, box_center_screen  # noqa: E402
from afk.jev import JevClient, JevError, TransportError  # noqa: E402
from afk.uiagent import UI_START_QUESTIONS  # noqa: E402
from afk.win32 import InputController, enable_dpi_awareness  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

CONTEXT = (
    "The player wants to be inside a match as fast as possible. "
    "This may be the Fortnite lobby, an island page, a mode picker, matchmaking, "
    "or already live gameplay. Pick the one button that gets closer to playing."
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--steps", type=int, default=10)
    p.add_argument("--act", action="store_true", help="actually click (default: dry run)")
    p.add_argument("--move-seconds", type=float, default=6.0,
                   help="after a match starts, walk for this long")
    p.add_argument("--out", default="")
    args = p.parse_args(argv)

    enable_dpi_awareness()
    cloud.keep_awake(True)
    cfg = load_config(ROOT / "config.json")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else ROOT / "logs" / "auto_start" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    rect = Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    capture = ScreenCapture(cfg.capture.max_width)
    client = JevClient(cfg)
    inputs = InputController(dry_run=not args.act, rng=random.Random(), key_mode=cfg.key_mode)
    steps: list[dict] = []
    in_match = False

    print(f"screen   : {rect.width}x{rect.height}")
    print(f"input    : {'SendInput (LIVE)' if args.act else 'dry-run'}")
    print(f"handles  : none")
    print()

    try:
        index = 0
        black_streak = 0
        queue_waits = 0
        while index < args.steps:
            index += 1
            frame = capture.grab(rect)
            frame.save_png(out_dir / f"step_{index:02d}.png")
            if cloud.mean_luma(frame) < cfg.cloud.black_frame_min_luma:
                black_streak += 1
                print(f"[{index:02d}] black frame ({black_streak}); waiting for the load")
                inputs.move_relative(40, 20)
                time.sleep(2.0)
                index -= 1  # loading does not consume a decision
                if black_streak > 20:
                    break
                continue
            black_streak = 0

            try:
                obs = client.ask(frame, UI_START_QUESTIONS, context=CONTEXT)
            except (JevError, TransportError) as exc:
                print(f"[{index:02d}] model error: {exc}")
                time.sleep(2.0)
                continue

            screen, screen_conf = obs.choice("screen")
            action, action_conf = obs.choice("target_action")
            box = obs.usable_box("target_button", min_confidence=0.25,
                                 min_presence=0.40, allow_null=True,
                                 null_value=0.5, max_side=0.95)
            print(f"[{index:02d}] screen={screen}({screen_conf:.2f}) "
                  f"action={action}({action_conf:.2f}) "
                  f"box={'yes' if box else 'no'}")

            steps.append({"index": index, "screen": screen, "action": action,
                          "box": None if box is None else
                          [round(box.left, 3), round(box.top, 3),
                           round(box.right, 3), round(box.bottom, 3)],
                          "png": f"step_{index:02d}.png"})

            if screen == "match":
                in_match = True
                break
            if screen == "queue" and action in ("wait", "none"):
                # Matchmaking can take a minute or two. Waiting is progress, so
                # it must not consume a decision step.
                print("       queueing; waiting for a match")
                time.sleep(4.0)
                index -= 1
                queue_waits += 1
                if queue_waits > 25:
                    break
                continue
            if action in ("wait", "none") or box is None:
                time.sleep(1.2)
                continue

            x, y = box_center_screen(box, rect)
            print(f"       -> {'click' if args.act else 'would click'} "
                  f"{action} at ({x},{y})")
            if not args.act:
                time.sleep(1.0)
                continue

            # A click on an inactive window is sometimes consumed by the
            # activation itself, and the model's box can sit a few pixels above
            # the label. Try three heights inside the model's own box, then
            # re-ask, instead of trusting a single event or a fixed coordinate.
            before = frame_signature(frame)
            changed = False
            xs, ys = box_center_screen(box, rect)
            box_h = max(6, int(box.height * rect.height))
            for attempt, dy in enumerate((0, int(box_h * 0.25), int(box_h * 0.35)), 1):
                inputs.click(xs, min(rect.bottom - 1, ys + dy))
                time.sleep(1.2)
                probe = capture.grab(rect)
                if cloud.mean_luma(probe) < cfg.cloud.black_frame_min_luma:
                    # Loading screens go black; that is success, not failure.
                    print(f"          attempt {attempt}: black frame (loading)")
                    changed = True
                    break
                similarity = signature_similarity(before, frame_signature(probe))
                print(f"          attempt {attempt}: screen similarity {similarity:.3f}")
                if similarity < 0.995:
                    changed = True
                    break
            if not changed:
                print("          three clicks changed nothing; re-asking the model")

        if in_match and args.move_seconds > 0:
            print(f"[move] walking for {args.move_seconds:.0f}s")
            for key in (["w"], ["w", "d"], ["w", "a"], ["w"]):
                inputs.key_down(key[0])
                if len(key) > 1:
                    inputs.key_down(key[1])
                time.sleep(max(0.6, args.move_seconds / 4))
                for k in reversed(key):
                    inputs.key_up(k)
            frame = capture.grab(rect)
            frame.save_png(out_dir / "after_move.png")
            print("[move] done, frame saved")
    finally:
        inputs.release_all()
        client.close()
        capture.close()

    (out_dir / "run.json").write_text(
        json.dumps({"act": args.act, "in_match": in_match, "steps": steps},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result: {'IN MATCH' if in_match else 'NOT IN MATCH'} -> {out_dir}")
    return 0 if in_match else 2


if __name__ == "__main__":
    raise SystemExit(main())
