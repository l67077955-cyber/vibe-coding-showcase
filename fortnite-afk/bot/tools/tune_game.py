#!/usr/bin/env python
"""Measure the sensitivity of whatever game is on screen.

Different games map mouse counts to camera angle very differently. The bot
should not ship a table of guesses: it can probe once, watch how far the world
slides, and write the measured `turn.px_per_screen` into config.json.

    python tools/tune_game.py --scene fortnite --sens 0.0034
    python tools/tune_game.py --scene fortnite --sens 0.0017 --write

`sens` is only understood by the local test page; it simulates a game with
different mouse sensitivity so the measurement can be checked against a known
ground truth (half the sens should measure twice the px_per_screen).

Exit codes: 0 = measured, 2 = probe failed (no shift / weak match), 3 = setup.
"""
from __future__ import annotations

import argparse
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
TOOLS = ROOT / "tools"
for entry in (str(ROOT), str(TOOLS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import web_chest_test as harness  # noqa: E402
from afk.autotune import measure_sensitivity  # noqa: E402
from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.win32 import enable_dpi_awareness, make_input  # noqa: E402

OUT = ROOT / "logs" / "autotune"
PAGE = ROOT / "web" / "fortnite_chest.html"


def launch(exe: Path, scene: str, sens: float, out_dir: Path, log) -> tuple:
    import subprocess
    import tempfile

    url = f"{PAGE.as_uri()}?scene={scene}&sens={sens}"
    profile = Path(tempfile.gettempdir()) / f"forweb-tune-{harness.os.getpid()}"
    harness.shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True, exist_ok=True)
    stderr_file = open(out_dir / "browser.log", "wb")  # noqa: SIM115
    cmd = [str(exe), f"--app={url}", "--window-size=1280,800",
           f"--user-data-dir={profile}", *harness.BROWSER_FLAGS]
    log(f"[setup] url={url}")
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=stderr_file, close_fds=True)
    return proc, profile, stderr_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", default="fortnite")
    p.add_argument("--sens", type=float, default=0.0034,
                   help="page-side sensitivity to simulate (radians per mouse px)")
    p.add_argument("--delta", type=int, default=180, help="probe mouse delta in px")
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    p.add_argument("--write", action="store_true",
                   help="write the measured value into config.json")
    args = p.parse_args(argv)

    enable_dpi_awareness()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUT / f"{stamp}_{args.scene}_sens{args.sens:g}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = harness.Reporter(out_dir)

    exe = harness.find_browser(args.browser)
    proc = profile = stderr_file = None
    hwnd = None
    capture = None
    results = []
    try:
        proc, profile, stderr_file = launch(exe, args.scene, args.sens, out_dir, log)
        hwnd, _cls, _title = harness.locate_window(proc.pid, log)
        harness.fit_window(hwnd, log)
        time.sleep(0.8)
        cfg = load_config(ROOT / "config.json")
        inputs = make_input(cfg, hwnd, __import__("random").Random())
        capture = ScreenCapture(max_width=cfg.capture.max_width)
        rect = harness.capture_rect(hwnd)
        inputs.click(rect.left + rect.width // 2, rect.top + rect.height // 2)
        time.sleep(0.6)

        for trial in range(1, args.trials + 1):
            harness.ensure_focus(hwnd, log)
            before = capture.grab(harness.capture_rect(hwnd))
            delta = args.delta if trial % 2 else -args.delta
            # Split the probe across a few ticks: a single 180 px jump can be
            # coalesced by the OS and under-measure the real sensitivity.
            for _ in range(6):
                inputs.move_relative(delta // 6, 0)
                time.sleep(0.02)
            time.sleep(0.45)
            after = capture.grab(harness.capture_rect(hwnd))
            m = measure_sensitivity(before, after, delta)
            m["trial"] = trial
            m["delta"] = delta
            results.append(m)
            log(f"[trial {trial}] delta={delta:+d} shift={m['shift']:+.4f} "
                f"conf={m['confidence']:.2f} -> px_per_screen={m['px_per_screen']} "
                f"({m['reason']})")
            time.sleep(0.3)
    except harness.SetupError as exc:
        print(f"setup error: {exc}", file=sys.stderr)
        return 3
    finally:
        if capture is not None:
            capture.close()
        harness.force_close(hwnd, proc)
        if stderr_file is not None:
            try:
                stderr_file.close()
            except Exception:
                pass
        harness.remove_profile(profile, log)

    good = [r["px_per_screen"] for r in results if r["ok"]]
    print()
    print(f"{'trial':<7}{'delta':>7}{'shift':>10}{'conf':>7}{'px/screen':>12}")
    print("-" * 44)
    for r in results:
        print(f"{r['trial']:<7}{r['delta']:>+7}{r['shift']:>+10.4f}"
              f"{r['confidence']:>7.2f}{r['px_per_screen']:>12}")
    if not good:
        print("\nno usable measurement; the page did not turn (pointer lock?)")
        (out_dir / "tune.json").write_text(
            json.dumps({"sens": args.sens, "results": results}, indent=2), encoding="utf-8")
        return 2

    k = round(statistics.median(good), 3)
    print("-" * 44)
    print(f"median px_per_screen = {k}")
    print(f"page sens            = {args.sens:g} rad/px")
    print(f"one full screen pan  = {k:.0f} mouse px")
    payload = {"scene": args.scene, "sens": args.sens, "px_per_screen": k,
               "trials": results}
    (out_dir / "tune.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.write:
        path = ROOT / "config.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        data.setdefault("turn", {})["px_per_screen"] = k
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"wrote turn.px_per_screen={k} -> {path}")
    print(f"raw: {out_dir / 'tune.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
