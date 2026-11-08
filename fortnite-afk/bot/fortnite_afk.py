"""Fortnite AFK farming loop for Zero Build squads, driven by Jev vision.

Zero third-party dependencies: runs with a plain CPython install or as the
frozen FortniteAFK.exe. See README.md.
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from afk.calibrate import calibrate
from afk.capture import ScreenCapture
from afk.config import (APP_DIR, Config, ConfigError, apply_overrides, config_summary,
                        load_config, resolve_api_key)
from afk.controller import AfkController, Fatal, GameWindow
from afk.geometry import Rect
from afk.jev import JevClient, JevError, check_api
from afk.vision import JevVision
from afk.win32 import (client_rect, enable_dpi_awareness, find_window,
                       is_foreground, is_minimized, make_input)

log = logging.getLogger("fortnite_afk")

BANNER = r"""
  ______          _   _             _        _    ______ _
 |  ____|         | | (_)           | |      / \  |  ____| |
 | |__ ___  _ __  | |_ _ _ __   ___ | |     /   \ | |__  | |
 |  __/ _ \| '__| | __| | '_ \ / _ \| |    / /_\ \|  __| | |
 | | | (_) | |    | |_| | | | |  __/| |   / _____ \ |  |_| |
 |_|  \___/|_|     \__|_|_| |_|\___||_|  /_/     \_\|  (___)

 Zero Build squads AFK loop - Jev vision clicks - F12 / Ctrl+C to stop
"""


def setup_logging(cfg: Config, level: str | None = None) -> Path:
    directory = Path(cfg.logging.dir)
    if not directory.is_absolute():
        directory = APP_DIR / directory
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / f"afk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, (level or cfg.logging.level).upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(file_handler)
    return log_file


def _client_and_vision(cfg: Config) -> tuple[JevClient, JevVision]:
    client = JevClient(cfg)
    return client, JevVision(cfg, client)


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    apply_overrides(cfg, dry_run=args.dry_run, max_cycles=args.cycles,
                    max_minutes=args.match_minutes)
    log_file = setup_logging(cfg, args.log_level)

    print(BANNER)
    print(f"config: {config_summary(cfg)}")
    print(f"log:    {log_file}")
    if cfg.safety.dry_run:
        print("DRY RUN: screenshots and Jev calls are real; no keys or clicks are sent.")
    print("Reminder: automation violates Epic's terms and can get the account banned.\n")

    client, vision = _client_and_vision(cfg)
    window = GameWindow(cfg)
    inputs = make_input(cfg, window, rng=random.Random())
    controller = AfkController(
        cfg,
        window=window,
        capture=ScreenCapture(
            cfg.capture.max_width, cfg.capture.inset_left, cfg.capture.inset_top,
            cfg.capture.inset_right, cfg.capture.inset_bottom,
        ),
        inputs=inputs,
        vision=vision,
        run_seconds=args.duration_minutes * 60.0 if args.duration_minutes else None,
    )
    summary = controller.run()
    print(f"\nDone: {summary.reason}")
    print(f"cycles={summary.cycles} jev_calls={summary.calls} cost=${summary.cost:.4f} "
          f"elapsed={(summary.ended_at - summary.started_at) / 60:.1f} min")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Offline state-machine demo: no game, no API, no dependencies."""
    from afk.sim import (FakeCapture, FakeInput, FakeWindow, MockGame, ScriptedVision,
                         VirtualClock)

    cfg = Config()
    cfg.mode.setup = "verify"
    cfg.timing.match_minutes = (0.2, 0.2)
    cfg.timing.lobby_cooldown_s = 1.0
    cfg.timing.match_check_s = 30.0
    cfg.timing.queue_poll_s = 2.0
    cfg.explore.enabled = True
    cfg.explore.interval_s = (1.0, 1.0)
    cfg.explore.look_every_s = (3.0, 5.0)
    cfg.safety.max_cycles = args.cycles
    cfg.safety.focus_on_start = False
    cfg.logging.save_frames = "off"
    setup_logging(cfg, "INFO")

    clock = VirtualClock()
    game = MockGame(clock)
    vision = ScriptedVision(game)
    inputs = FakeInput(clock, game)
    controller = AfkController(
        cfg, window=FakeWindow(), capture=FakeCapture(), inputs=inputs, vision=vision,
        clock=clock, sleeper=clock.sleep, panic=lambda: False, rng=random.Random(7),
    )
    print(BANNER)
    print(f"DEMO: simulated Fortnite, {args.cycles} cycle(s), virtual clock\n")
    summary = controller.run()
    print(f"\nDone: {summary.reason}; cycles={summary.cycles}; actions={len(inputs.actions)}")
    for action in inputs.actions:
        print(f"  {action[0]:6s} {action[1]}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    setup_logging(cfg, args.log_level)
    print(BANNER)
    print(f"Calibrating profile '{args.profile}'...\n")
    path = calibrate(cfg, args.profile, args.image)
    print(f"\nOpen this report in a browser: {path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    setup_logging(cfg, args.log_level)
    print(BANNER)
    print("Doctor\n------")
    problems = 0

    print(f"python: {sys.version.split()[0]}  frozen={getattr(sys, 'frozen', False)}")
    print(f"app dir: {APP_DIR}")
    print("third-party packages needed: none")

    from afk.cloud import mean_luma, session_summary

    info = session_summary()
    print(f"session: id={info['session_id']} remote={info['remote_session']} "
          f"state={info['connect_state']} input_desktop={info['input_desktop']}")
    print(f"display: {info['width']}x{info['height']} "
          f"virtual={info['virtual_width']}x{info['virtual_height']}")

    try:
        key = resolve_api_key(cfg)
        print(f"api key: found (len={len(key)}, source hidden)")
    except ConfigError as exc:
        print(f"api key: FAIL - {exc}")
        problems += 1

    if args.no_api:
        print("api call: skipped (--no-api)")
    else:
        ok, detail = check_api(cfg)
        print(f"api call: {'PASS' if ok else 'FAIL'} - {detail}")
        if not ok:
            problems += 1

    enable_dpi_awareness()
    hwnd = find_window(cfg.window_class, cfg.window_title)
    if not hwnd:
        print("game window: NOT FOUND (start Fortnite before a live run)")
    else:
        try:
            rect = client_rect(hwnd)
            print(f"game window: hwnd=0x{hwnd:X} rect={rect} "
                  f"foreground={is_foreground(hwnd)} minimised={is_minimized(hwnd)}")
            capture = ScreenCapture(cfg.capture.max_width)
            frame = capture.grab(Rect(*rect))
            out = APP_DIR / cfg.logging.dir / "doctor.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            frame.save_png(out)
            print(f"capture: PASS {frame.width}x{frame.height} luma={mean_luma(frame):.1f} -> {out}")
        except Exception as exc:
            print(f"capture: FAIL - {exc}")
            problems += 1

    print(f"\nresult: {'PASS' if problems == 0 else f'{problems} problem(s)'}")
    return 0 if problems == 0 else 1


def cmd_keytest(args: argparse.Namespace) -> int:
    from afk.keytest import key_test

    print(BANNER)
    print("Input backend test: a window will open and receive one W keypress.\n")
    results = key_test(args.key)
    sendinput = results.get("sendinput") or {}
    postmessage = results.get("postmessage") or {}
    send_ok = int(sendinput.get("keydown", 0)) > 0
    post_ok = int(postmessage.get("keydown", 0)) > 0
    print()
    if send_ok and int(sendinput.get("char", 0)) > 0:
        print("SendInput: OK (keydown + WM_CHAR). Use input_backend='sendinput'.")
    elif send_ok:
        print("SendInput: keydown arrives but WM_CHAR does not. Movement keys may work; "
              "text fields may not.")
    else:
        print("SendInput: no keydown reached the window. Try running as administrator, "
              "or use input_backend='postmessage'.")
    print("PostMessage: " + ("OK (keydown arrives)." if post_ok
                             else "FAILED; this session blocks direct window messages too."))
    return 0 if (send_ok or post_ok) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="FortniteAFK",
        description="Fortnite Zero Build squads AFK loop with Jev (TypeSafe) vision.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="start the AFK loop")
    run.add_argument("--config", default=None, help="path to config.json")
    run.add_argument("--dry-run", action="store_true", help="observe and log, never send input")
    run.add_argument("--cycles", type=int, default=None, help="stop after N matches")
    run.add_argument("--duration-minutes", type=float, default=None, help="stop after N minutes")
    run.add_argument("--match-minutes", type=float, default=None,
                     help="fixed match length before leaving (overrides config range)")
    run.add_argument("--log-level", default=None)
    run.set_defaults(func=cmd_run)

    demo = sub.add_parser("demo", help="offline state-machine demo (no game/API)")
    demo.add_argument("--cycles", type=int, default=2)
    demo.set_defaults(func=cmd_demo)

    cal = sub.add_parser("calibrate", help="test Jev on the current screen and save a report")
    cal.add_argument("--config", default=None)
    cal.add_argument("--profile",
                     choices=["lobby", "queue", "ingame", "menu", "results", "explore"],
                     default="lobby")
    cal.add_argument("--image", default=None, help="use a PNG file instead of the live game")
    cal.add_argument("--log-level", default=None)
    cal.set_defaults(func=cmd_calibrate)

    doc = sub.add_parser("doctor", help="check key, API, window and capture")
    doc.add_argument("--config", default=None)
    doc.add_argument("--no-api", action="store_true")
    doc.add_argument("--log-level", default=None)
    doc.set_defaults(func=cmd_doctor)

    kt = sub.add_parser("keytest", help="test SendInput/PostMessage keyboard delivery")
    kt.add_argument("--key", default="w")
    kt.set_defaults(func=cmd_keytest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    enable_dpi_awareness()
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except (Fatal, JevError) as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
