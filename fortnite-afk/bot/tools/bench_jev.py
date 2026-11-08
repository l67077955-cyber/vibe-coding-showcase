#!/usr/bin/env python
"""Latency A/B for the Jev call, measured on the live 3D page.

Three things decide how long one decision takes:

  1. connection   a fresh TLS handshake per call (urllib) vs a reused socket
  2. image size   PNG pixels + base64 + upload; 1280 -> 768 is 64% fewer pixels
  3. output tokens  every question the model must answer is generated one
                    token at a time, so the 18-question profile is slower than
                    the 12-question one the in-match loop actually reads

This script holds each variable constant while sweeping the others, on the same
window and the same scene, and prints median/p90 per variant. Run it with the
API key in OPENROUTER_API_KEY.

    python tools/bench_jev.py --calls 3
    python tools/bench_jev.py --calls 5 --profile explore,explore_fast
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
from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.jev import JevClient  # noqa: E402
from afk.screens import questions_for  # noqa: E402
from afk.win32 import enable_dpi_awareness, window_title  # noqa: E402

OUT = ROOT / "logs" / "bench"


def measure(client: JevClient, frame, questions, calls: int) -> dict:
    times, http, encode, tokens = [], [], [], []
    for _ in range(calls):
        obs = client.ask(frame, questions)
        times.append(obs.timings["total_ms"])
        http.append(obs.timings["http_ms"])
        encode.append(obs.timings["encode_ms"])
        tokens.append(obs.usage.get("output_tokens") or 0)
    return {
        "total_median": round(statistics.median(times)),
        "total_min": round(min(times)),
        "total_max": round(max(times)),
        "http_median": round(statistics.median(http)),
        "encode_median": round(statistics.median(encode)),
        "out_tokens": round(statistics.median(tokens)) if tokens else 0,
        "calls": calls,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--calls", type=int, default=3, help="calls per variant")
    p.add_argument("--scene", default="fortnite")
    p.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    p.add_argument("--profile", default="explore,explore_fast")
    p.add_argument("--widths", default="1280,960,768")
    p.add_argument("--keepalive", action="store_true", default=True)
    args = p.parse_args(argv)

    enable_dpi_awareness()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUT / f"{stamp}_latency"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = harness.Reporter(out_dir)

    cfg = load_config(ROOT / "config.json")
    client = JevClient(cfg)
    exe = harness.find_browser(args.browser)
    proc = profile_dir = stderr_file = None
    hwnd = None
    capture = None
    rows: list[dict] = []
    try:
        proc, profile_dir, stderr_file = harness.launch_browser(exe, args.scene, out_dir, log)
        hwnd, _cls, _title = harness.locate_window(proc.pid, log)
        harness.fit_window(hwnd, log)
        time.sleep(0.8)
        harness.ensure_focus(hwnd, log)

        profiles = [name.strip() for name in args.profile.split(",") if name.strip()]
        widths = [int(w) for w in args.widths.split(",") if w.strip()]

        # Warm the socket once so the first (cold) call is not attributed to a
        # variant. It is reported separately as `cold`.
        cold_capture = ScreenCapture(max_width=widths[0])
        cold_frame = cold_capture.grab(harness.capture_rect(hwnd))
        cold = measure(client, cold_frame, questions_for(profiles[-1]), 1)
        rows.append({"variant": "cold-first-call", "width": widths[0],
                     "profile": profiles[-1], "keepalive": True, **cold})
        cold_capture.close()
        log(f"[cold] {cold}")

        for width in widths:
            capture = ScreenCapture(max_width=width)
            frame = capture.grab(harness.capture_rect(hwnd))
            for name in profiles:
                q = questions_for(name)
                client.use_keepalive = args.keepalive
                warm = measure(client, frame, q, args.calls)
                rows.append({"variant": f"{name}@{width}px+keepalive",
                             "width": width, "profile": name,
                             "keepalive": True, **warm})
                log(f"[{name}@{width} keepalive] {warm}")

                client.use_keepalive = False
                plain = measure(client, frame, q, args.calls)
                rows.append({"variant": f"{name}@{width}px+newconn",
                             "width": width, "profile": name,
                             "keepalive": False, **plain})
                log(f"[{name}@{width} newconn] {plain}")
                client.use_keepalive = True
            capture.close()
            capture = None
    finally:
        client.close()
        if capture is not None:
            capture.close()
        harness.force_close(hwnd, proc)
        if stderr_file is not None:
            try:
                stderr_file.close()
            except Exception:
                pass
        harness.remove_profile(profile_dir, log)

    base = next((r for r in rows if r["variant"].startswith("explore@")), None)
    print()
    header = f"{'variant':<34}{'median':>9}{'min':>8}{'max':>8}{'http':>8}{'encode':>8}{'out tok':>9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['variant']:<34}{r['total_median']:>8}ms{r['total_min']:>7}ms"
              f"{r['total_max']:>7}ms{r['http_median']:>7}ms{r['encode_median']:>7}ms"
              f"{r['out_tokens']:>9}")
    if base:
        print("-" * len(header))
        for r in rows:
            if r is base:
                continue
            delta = base["total_median"] - r["total_median"]
            pct = delta / base["total_median"] * 100 if base["total_median"] else 0
            print(f"{r['variant']:<34}{delta:>+7}ms vs baseline ({pct:+.0f}%)")

    payload = {"when": stamp, "model": cfg.model, "rows": rows}
    (out_dir / "latency.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nraw: {out_dir / 'latency.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
