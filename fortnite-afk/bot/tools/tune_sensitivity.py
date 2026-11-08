#!/usr/bin/env python
"""Ask Jev to judge mouse sensitivity from a before/after frame pair.

Sensitivity is the mapping between mouse pixels and camera angle. One frame
cannot show it; two can. The probe turns the camera by a known delta, captures
before and after, and asks the model how far the view actually moved:

    none   -> the input did not reach the game, or sensitivity is far too low
    small  -> turn more per pixel (raise px_per_screen)
    good   -> leave it
    large  -> turn less per pixel (lower px_per_screen)

    python tools/tune_sensitivity.py --trials 3
    python tools/tune_sensitivity.py --write
"""
from __future__ import annotations

import argparse
import ctypes
import json
import statistics
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
from afk.geometry import Rect  # noqa: E402
from afk.jev import JevClient, JevError, TransportError  # noqa: E402
from afk.motion import plan_turn  # noqa: E402
from afk.uiagent import SENSITIVITY_QUESTIONS  # noqa: E402
from afk.win32 import InputController, enable_dpi_awareness  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

CONTEXT = (
    "This is a calibration probe, not gameplay. The mouse was moved by a fixed "
    "horizontal delta between the two frames. Judge only how far the view rotated."
)

FACTOR = {"none": 1.8, "small": 1.35, "good": 1.0, "large": 0.6}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--delta", type=int, default=240, help="probe mouse pixels")
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--write", action="store_true", help="write turning.px_per_screen")
    p.add_argument("--out", default="")
    args = p.parse_args(argv)

    enable_dpi_awareness()
    cloud.keep_awake(True)
    cfg = load_config(ROOT / "config.json")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else ROOT / "logs" / "sensitivity" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    rect = Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    capture = ScreenCapture(cfg.capture.max_width)
    client = JevClient(cfg)
    inputs = InputController(dry_run=False, key_mode=cfg.key_mode)
    scale = float(cfg.turn.px_per_screen)
    trials: list[dict] = []

    print(f"screen : {rect.width}x{rect.height}")
    print(f"probe  : {args.delta}px horizontal, start scale {scale:.2f}")
    print("click the game so it owns the mouse; starting in 6 seconds")
    time.sleep(6)

    try:
        for trial in range(1, args.trials + 1):
            before = capture.grab(rect)
            before.save_png(out_dir / f"before_{trial}.png")
            delta = int(args.delta * scale)
            for step in plan_turn(delta, cfg.turn):
                inputs.move_relative(step, 0)
                time.sleep(cfg.turn.tick_s)
            time.sleep(0.5)
            after = capture.grab(rect)
            after.save_png(out_dir / f"after_{trial}.png")

            try:
                obs = client.ask_pair(before, after, SENSITIVITY_QUESTIONS,
                                      context=CONTEXT)
            except (JevError, TransportError) as exc:
                print(f"[{trial}] model error: {exc}")
                continue
            shift, shift_conf = obs.choice("view_shift")
            direction, _ = obs.choice("turn_direction")
            factor = FACTOR.get(shift, 1.0)
            scale = max(0.25, min(8.0, scale * factor))
            print(f"[{trial}] delta={delta:+d}px view={shift}({shift_conf:.2f}) "
                  f"dir={direction} -> factor {factor} -> scale {scale:.2f}")
            trials.append({"trial": trial, "delta": delta, "view_shift": shift,
                           "confidence": shift_conf, "direction": direction,
                           "factor": factor, "scale": round(scale, 3)})
            time.sleep(1.0)
    finally:
        client.close()
        capture.close()

    usable = [t["scale"] for t in trials if t["view_shift"] in FACTOR]
    final = round(statistics.median(usable), 2) if usable else round(scale, 2)
    print(f"\nrecommended px_per_screen = {final}")
    (out_dir / "tune.json").write_text(
        json.dumps({"trials": trials, "recommended": final}, indent=2), encoding="utf-8")

    if args.write and usable:
        path = ROOT / "config.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        data.setdefault("turn", {})["px_per_screen"] = final
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"wrote turn.px_per_screen={final} -> {path}")
    print(f"raw: {out_dir / 'tune.json'}")
    return 0 if usable else 2


if __name__ == "__main__":
    raise SystemExit(main())
