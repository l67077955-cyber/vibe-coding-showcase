#!/usr/bin/env python
"""Handle-free runner: screen capture in, SendInput out, nothing else.

The normal controller finds the game window, reads its client rect, checks that
it is foreground and focuses it. All of that needs an HWND. This runner is for
setups where touching a window handle is not allowed:

    no FindWindow / EnumWindows / OpenProcess / ReadProcessMemory
    no PostMessage (it needs a handle by definition)
    no window title, no client rect, no focus check

What is left is exactly two OS calls: a GDI blit of a screen rectangle, and
SendInput for keys/mouse. You keep the game focused yourself; the runner only
looks at pixels and, with --act, types into whatever is in front.

    python tools/screen_only_loop.py --dry-run --steps 6
    python tools/screen_only_loop.py --region 0,0,1280,720 --steps 0 --act

Exit codes: 0 = finished, 2 = model/setup failure.
"""
from __future__ import annotations

import argparse
import json
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

import ctypes  # noqa: E402
import ctypes.wintypes as wt  # noqa: E402
import random  # noqa: E402

from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.explore import (describe, frame_signature, plan_explore,  # noqa: E402
                         signature_similarity)
from afk.geometry import Rect  # noqa: E402
from afk.jev import JevClient, JevError, TransportError  # noqa: E402
from afk.motion import CameraNoise, aim_px, aim_py, plan_turn  # noqa: E402
from afk.screens import questions_for  # noqa: E402
from afk.win32 import InputController, enable_dpi_awareness  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

CONTEXT = (
    "This is a full-screen capture of a game. You are the player. "
    "Choose the next operation from the options. If an interactive object is "
    "visible but far away, walk toward it; only choose interact when you are "
    "close enough that pressing the interact key would work."
)


def screen_rect(region: str | None) -> Rect:
    if region:
        parts = [int(p) for p in region.replace("x", ",").split(",")]
        if len(parts) != 4:
            raise SystemExit("--region must be x,y,w,h")
        return Rect(*parts)
    return Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def mean_luma(frame) -> float:
    rgb = frame.rgb
    if not rgb:
        return 0.0
    step = max(3, (len(rgb) // 3 // 4000) * 3)
    total = 0
    count = 0
    for i in range(0, len(rgb) - 2, step):
        total += rgb[i] * 0.299 + rgb[i + 1] * 0.587 + rgb[i + 2] * 0.114
        count += 1
    return total / count if count else 0.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="", help="x,y,w,h; default is the whole screen")
    p.add_argument("--steps", type=int, default=6, help="0 = run until Ctrl+C")
    p.add_argument("--interval", type=float, default=0.0,
                   help="seconds between decisions; 0 = ask as fast as the model answers")
    p.add_argument("--act", action="store_true",
                   help="actually send keys/mouse (default: dry run, log only)")
    p.add_argument("--save-every", type=int, default=1, help="save every Nth frame")
    p.add_argument("--focus-game", action="store_true",
                   help="send one Alt+Tab at start so the game owns the keyboard; "
                        "this build never asks for a window handle")
    p.add_argument("--out", default="")
    args = p.parse_args(argv)

    enable_dpi_awareness()
    cfg = load_config(ROOT / "config.json")
    rect = screen_rect(args.region or None)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else ROOT / "logs" / "screen_only" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"region   : {rect.left},{rect.top} {rect.width}x{rect.height}")
    print(f"input    : {'SendInput (LIVE)' if args.act else 'dry-run (no input)'}")
    print(f"backend  : sendinput only (no PostMessage: it requires an HWND)")
    print(f"handles  : none - no FindWindow, no client rect, no focus check")
    print(f"out      : {out_dir}")
    print()

    capture = ScreenCapture(max_width=cfg.capture.max_width)
    client = JevClient(cfg)
    inputs = InputController(dry_run=not args.act, rng=random.Random(), key_mode=cfg.key_mode)
    questions = questions_for(cfg.explore.question_profile)
    rng = random.Random()
    noise = CameraNoise(rng, cfg.turn)
    aim_gain = cfg.turn.gain
    held: set[str] = set()
    steps: list[dict] = []
    last_interact_at = -999.0
    last_aim: tuple[float, int] | None = None
    last_sig: tuple[int, ...] = ()
    stuck = 0
    no_turn = 0
    turn_scale = 1.0
    started = time.monotonic()

    if args.focus_game:
        # Never Alt+Tab blindly: it lands on whatever window Windows remembers
        # and can put the terminal in front, where the keys go to a console.
        # Ask the person to click the game once instead; no window handles and
        # no guessing.
        print("focus: click the game window now - starting in 8 seconds")
        for left in range(8, 0, -1):
            print(f"  {left}...", end="\r", flush=True)
            time.sleep(1.0)
        print("focus: starting; every key now goes to the foreground window")

    try:
        index = 0
        end_streak = 0
        while args.steps == 0 or index < args.steps:
            index += 1
            frame = capture.grab(rect)
            sig = frame_signature(frame)
            luma = mean_luma(frame)
            stamp_t = time.monotonic() - started
            if luma < cfg.cloud.black_frame_min_luma:
                print(f"[{index:02d}] {stamp_t:6.1f}s black frame (luma {luma:.1f}); "
                      f"not asking, not acting")
                steps.append({"index": index, "luma": round(luma, 1),
                              "skipped": "black frame"})
                time.sleep(1.0)
                continue

            png = ""
            if args.save_every and index % args.save_every == 0:
                png = f"step_{index:02d}.png"
                frame.save_png(out_dir / png)

            t0 = time.monotonic()
            try:
                obs = client.ask(frame, questions, context=CONTEXT)
            except (JevError, TransportError) as exc:
                print(f"[{index:02d}] model error: {exc}")
                steps.append({"index": index, "error": str(exc)})
                time.sleep(2.0)
                continue
            api_s = time.monotonic() - t0

            chest_ready = (time.monotonic() - last_interact_at) >= cfg.explore.chest_cooldown_s
            plan = plan_explore(obs, cfg, rng, chest_ready=chest_ready)
            _, action_conf = obs.choice("action")
            similarity = (round(signature_similarity(last_sig, sig), 4)
                          if last_sig else None)
            last_sig = sig
            print(f"[{index:02d}] {stamp_t:6.1f}s luma={luma:5.1f} api={api_s:4.2f}s "
                  f"act={action_conf:.2f} sim={similarity if similarity is not None else '-'} "
                  f"| {describe(plan)} | {plan.reason}")

            if last_aim is not None and plan.aim_norm:
                before, turn = last_aim
                last_aim = None
                if abs(turn) >= 30 and abs(before) >= 0.05:
                    if abs(plan.aim_norm) < abs(before) * 0.80:
                        aim_gain = min(0.90, aim_gain * 1.10)
                    elif abs(plan.aim_norm) > abs(before) * 1.02:
                        aim_gain = max(0.12, aim_gain * 0.55)

            # Stuck against geometry: the frame stops changing while the plan
            # keeps walking. Back out, hop, and sweep the camera - without this
            # the bot grinds into a wall forever and never turns.
            moving = bool(plan.keys or plan.interact or plan.jump or plan.mouse)
            if similarity is not None and similarity >= 0.985 and moving:
                stuck += 1
            else:
                stuck = 0
            if stuck >= 2:
                stuck = 0
                no_turn = 0
                print("       stuck: backing out, jumping, scanning")
                if args.act:
                    for key in list(held):
                        inputs.key_up(key)
                    held.clear()
                    inputs.hold(["s"], 0.5)
                    inputs.press("space", 0.08)
                    inputs.hold(["d"], 0.35)
                    direction = 1 if index % 2 else -1
                    for delta in plan_turn(int(direction * 320 * turn_scale), cfg.turn):
                        nx, ny = noise.step(cfg.turn.tick_s)
                        inputs.move_relative(delta + nx, ny)
                        time.sleep(cfg.turn.tick_s)
                steps.append({"index": index, "time": round(stamp_t, 1),
                              "luma": round(luma, 1), "api_s": round(api_s, 2),
                              "screen": obs.screen, "action_conf": round(action_conf, 3),
                              "similarity": similarity, "keys": ["s", "d"],
                              "interact": False, "jump": True, "aim": 0.0, "aim_y": 0.0,
                              "plan": "stuck-escape + 320px scan",
                              "reason": "frame unchanged while moving"})
                continue

            # No target and no turn for a while: look around instead of
            # marching at the same wall forever.
            if plan.aim_norm or plan.aim_norm_y or plan.look_dx:
                no_turn = 0
            else:
                no_turn += 1
            if no_turn >= 6:
                no_turn = 0
                direction = 1 if index % 2 else -1
                print(f"       scan: no target for 6 steps, turning {direction * 280:+d}px")
                if args.act:
                    for delta in plan_turn(int(direction * 280 * turn_scale), cfg.turn):
                        nx, ny = noise.step(cfg.turn.tick_s)
                        inputs.move_relative(delta + nx, ny)
                        time.sleep(cfg.turn.tick_s)
                    probe = capture.grab(rect)
                    turned = signature_similarity(sig, frame_signature(probe))
                    if turned > 0.995:
                        turn_scale = min(4.0, turn_scale * 1.5)
                    elif turned < 0.90:
                        turn_scale = max(0.8, turn_scale * 0.85)
                    print(f"       turn_scale -> {turn_scale:.2f} (view change {turned:.3f})")

            if args.act:
                if plan.interact:
                    for key in list(held):
                        inputs.key_up(key)
                    held.clear()
                    inputs.press(cfg.explore.interact_key, 0.12)
                    last_interact_at = time.monotonic()
                elif plan.jump:
                    inputs.press("space", 0.08)
                elif plan.mouse:
                    # Left button fires, right button aims. Without this branch
                    # the model could choose attack and nothing would happen.
                    cx = rect.left + rect.width // 2
                    cy = rect.top + rect.height // 2
                    if plan.hold_s <= 0.2:
                        inputs.click(cx, cy, button=plan.mouse)
                    else:
                        inputs.mouse_down(plan.mouse)
                        time.sleep(min(plan.hold_s, 1.2))
                        inputs.mouse_up(plan.mouse)
                elif plan.keys and plan.continuous:
                    new = {k.lower() for k in plan.keys}
                    for key in held - new:
                        inputs.key_up(key)
                    for key in new - held:
                        inputs.key_down(key)
                    held = new
                elif plan.keys:
                    for key in list(held):
                        inputs.key_up(key)
                    held.clear()
                    inputs.hold(list(plan.keys), min(plan.hold_s, 1.2))

                if plan.aim_norm or plan.aim_norm_y or plan.look_dx:
                    turn_px = int(plan.look_dx or 0)
                    turn_py = 0
                    if plan.aim_norm:
                        turn_px = aim_px(0.5 + plan.aim_norm, frame.width,
                                         cfg.turn, gain=aim_gain)
                        last_aim = (plan.aim_norm, turn_px)
                    if plan.aim_norm_y:
                        turn_py = aim_py(0.5 + plan.aim_norm_y, frame.height,
                                         cfg.turn, gain=aim_gain)
                    steps_x = plan_turn(turn_px, cfg.turn) if turn_px else []
                    steps_y = plan_turn(turn_py, cfg.turn) if turn_py else []
                    for i in range(max(len(steps_x), len(steps_y))):
                        sx = steps_x[i] if i < len(steps_x) else 0
                        sy = steps_y[i] if i < len(steps_y) else 0
                        nx, ny = noise.step(cfg.turn.tick_s)
                        inputs.move_relative(sx + nx, sy + ny)
                        time.sleep(cfg.turn.tick_s)
                elif plan.keys and plan.continuous:
                    nx, ny = noise.step(0.10)
                    if nx or ny:
                        inputs.move_relative(nx, ny)

            steps.append({
                "index": index, "time": round(stamp_t, 1), "luma": round(luma, 1),
                "api_s": round(api_s, 2), "png": png,
                "screen": obs.screen, "action_conf": round(action_conf, 3),
                "similarity": similarity, "keys": list(plan.keys),
                "interact": bool(plan.interact), "jump": bool(plan.jump),
                "aim": round(plan.aim_norm, 3), "aim_y": round(plan.aim_norm_y, 3),
                "plan": describe(plan), "reason": plan.reason,
            })
            if args.interval > 0:
                time.sleep(args.interval)

            # Stop when the match is over instead of burning steps in a lobby.
            if obs.screen in ("eliminated", "results", "lobby"):
                end_streak += 1
                if end_streak >= 2:
                    print(f"match over: screen={obs.screen}; stopping")
                    break
            else:
                end_streak = 0
    except KeyboardInterrupt:
        print("\nstopped by user")
    finally:
        for key in list(held):
            try:
                inputs.key_up(key)
            except Exception:
                pass
        inputs.release_all()
        client.close()
        capture.close()

    (out_dir / "decisions.json").write_text(
        json.dumps({"region": [rect.left, rect.top, rect.width, rect.height],
                    "act": args.act, "steps": steps}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\ndecisions: {out_dir / 'decisions.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
