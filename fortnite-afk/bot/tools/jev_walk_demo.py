"""Live Jev walk demo in an open-source 3D game (Luanti / Minetest).

Each step: capture the game window -> Jev chooses forward/left/right/backward/
jump from the first-person view -> send the key via PostMessage or SendInput.
Saves every frame and builds an HTML contact sheet, so the decisions are
auditable rather than a claim.

Example (after starting Luanti in a world):
  python tools/jev_walk_demo.py --title Luanti --steps 8 --goal "walk toward the nearest tree"
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from afk.capture import Frame, ScreenCapture  # noqa: E402
from afk.config import Config  # noqa: E402
from afk.explore import frame_signature, signature_similarity  # noqa: E402
from afk.geometry import Rect, parse_box  # noqa: E402
from afk.jev import JevClient  # noqa: E402
from afk.png import draw_rect  # noqa: E402
from afk.win32 import (InputController, PostMessageInput, client_rect, enable_dpi_awareness,
                       find_window, focus_window, is_foreground)  # noqa: E402

MOVES = {
    "forward": ["w"],
    "forward_left": ["w", "a"],
    "forward_right": ["w", "d"],
    "left": ["a"],
    "right": ["d"],
    "backward": ["s"],
    "jump": ["w"],
    "stop": [],
}

QUESTIONS = {
    "screen": {
        "type": "choice",
        "instructions": "Which screen is shown?",
        "criteria": {
            "in_game": "A live 3D game view with terrain, blocks, trees or a HUD.",
            "menu": "A main menu, world selection screen, or settings dialog.",
            "loading": "A loading screen or mostly black screen.",
            "other": "Anything else.",
        },
    },
    "move": {
        "type": "choice",
        "instructions": (
            "You control the player in this first-person 3D view. The player is at the "
            "bottom centre. Choose the single best next movement to make progress toward "
            "the goal stated in the text. Prefer a clear route; avoid walking into walls, "
            "cliffs, water or lava."
        ),
        "criteria": {
            "forward": "The path straight ahead is clear.",
            "forward_left": "Move diagonally forward-left around an obstacle or toward a target on the left.",
            "forward_right": "Move diagonally forward-right around an obstacle or toward a target on the right.",
            "left": "Strafe left because the target is left or forward is blocked.",
            "right": "Strafe right because the target is right or forward is blocked.",
            "backward": "Back away from a wall, cliff, water, lava or dead end.",
            "jump": "A low block, step or ledge ahead can be climbed by jumping while moving forward.",
            "stop": "No safe movement; look around instead.",
        },
    },
    "target_visible": {
        "type": "noul",
        "instructions": "Is the goal object described in the text clearly visible in this view?",
    },
    "target": {
        "type": "box",
        "instructions": "the goal object described in the text, or the most promising landmark",
    },
    "path_clear": {
        "type": "noul",
        "instructions": "Is the path straight ahead clear of walls, dense blocks, cliffs, water and lava?",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="Luanti")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--goal", default="walk toward the nearest tree")
    parser.add_argument("--backend", choices=["postmessage", "sendinput"], default="postmessage")
    parser.add_argument("--hold", type=float, default=0.7)
    parser.add_argument("--pause", type=float, default=0.9)
    parser.add_argument("--out", default="logs/walk_demo")
    args = parser.parse_args()
    enable_dpi_awareness()

    hwnd = None
    for _ in range(30):
        hwnd = find_window("", args.title)
        if hwnd:
            break
        time.sleep(1)
    if not hwnd:
        print(f"window containing {args.title!r} not found", file=sys.stderr)
        return 2
    print(f"window hwnd=0x{hwnd:X} title contains {args.title!r} "
          f"foreground={is_foreground(hwnd)}")
    focus_window(hwnd)

    cfg = Config()
    cfg.logging.save_frames = "off"
    client = JevClient(cfg)
    capture = ScreenCapture(cfg.capture.max_width)
    if args.backend == "postmessage":
        inputs = PostMessageInput(lambda: hwnd)
    else:
        inputs = InputController()

    out_dir = ROOT / args.out / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    frames: list[str] = []
    last_sig: tuple[int, ...] = ()
    stuck = 0
    context = (
        f"Goal: {args.goal}. This is a first-person view; the player is at the bottom "
        f"centre. Choose one movement that gets closer to the goal without getting stuck."
    )

    for step in range(1, args.steps + 1):
        focused = focus_window(hwnd)
        time.sleep(0.2)
        rect = Rect(*client_rect(hwnd))
        frame = capture.grab(rect)
        obs = client.ask(frame, QUESTIONS, context=context)
        if obs.screen in ("menu", "loading"):
            print(f"[{step}] screen={obs.screen}; pressing Esc to resume")
            inputs.press("esc", 0.10)
            time.sleep(1.0)
            continue
        move, conf = obs.choice("move")
        target_presence = obs.noul("target_visible")
        target_box, target_conf = obs.raw_box("target")
        path_clear = obs.noul("path_clear")
        sig = frame_signature(frame)
        changed = signature_similarity(last_sig, sig) if last_sig else 1.0
        last_sig = sig
        stuck = stuck + 1 if changed >= 0.995 else 0

        annotated = frame
        if frame.rgb is not None and target_box is not None:
            rgb = bytearray(frame.rgb)
            draw_rect(rgb, frame.width, frame.height, target_box, color=(40, 220, 120))
            annotated = Frame(frame.width, frame.height, rgb, frame.rect, frame.scale,
                              frame.captured_at)
        png_name = f"step_{step:02d}.png"
        annotated.save_png(out_dir / png_name)
        frames.append(png_name)

        keys = MOVES.get(move or "", [])
        print(f"[{step}] move={move} conf={conf:.2f} target={target_presence} "
              f"path_clear={path_clear} changed={changed:.3f} stuck={stuck} focus={focused}")
        if stuck >= 2:
            print("  RECOVER: back up, jump and strafe")
            inputs.hold(["s"], 0.55)
            inputs.press("space", 0.08)
            inputs.hold(["d"], 0.40)
            stuck = 0
            last_sig = ()
        elif keys:
            if move == "jump":
                inputs.key_down("w")
                try:
                    inputs.press("space", 0.08)
                    time.sleep(0.2)
                finally:
                    inputs.key_up("w")
            else:
                inputs.hold(keys, args.hold)
        elif move == "stop":
            inputs.hold(["s"], 0.45)
            inputs.move_relative(220 if step % 2 else -220, 0)

        rows.append(
            "<tr>"
            f"<td><img src='{png_name}'></td>"
            f"<td>{step}</td><td>{html.escape(str(move))}<br><small>conf {conf:.2f}</small></td>"
            f"<td>target={target_presence}<br>path_clear={path_clear}<br>"
            f"target_box_conf={target_conf}</td>"
            f"<td>{changed:.3f}</td>"
            "</tr>"
        )
        time.sleep(args.pause)

    page = f"""<!doctype html><meta charset="utf-8">
<title>Jev walk demo</title>
<style>
 body{{background:#12161e;color:#e8edf5;font:14px/1.5 "Segoe UI",Arial,sans-serif;margin:24px}}
 td{{vertical-align:top;padding:8px;border-bottom:1px solid #263041}}
 img{{width:480px;border:1px solid #2b3444;display:block}}
 small{{color:#8fa0b8}} table{{border-collapse:collapse}}
 h1{{font-size:20px}} code{{color:#7ee2a8}}
</style>
<h1>Jev walks in Luanti &mdash; {html.escape(args.goal)}</h1>
<p>backend=<code>{args.backend}</code>, model=<code>{html.escape(cfg.model)}</code>,
frames={len(frames)}, cost=${client.total_cost:.5f}.
Each row is one Jev decision; the image is the exact frame sent. "changed" compares the
8x8 luma signature with the previous frame (1.0 = identical).</p>
<table><tr><th>frame</th><th>step</th><th>decision</th><th>signals</th><th>changed</th></tr>
{''.join(rows)}</table>
"""
    (out_dir / "report.html").write_text(page, encoding="utf-8")
    (out_dir / "decisions.json").write_text(json.dumps(
        {"goal": args.goal, "backend": args.backend, "frames": frames,
         "cost": client.total_cost, "calls": client.calls}, indent=2), encoding="utf-8")
    print(f"report: {out_dir / 'report.html'}")
    print(f"calls={client.calls} cost=${client.total_cost:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
