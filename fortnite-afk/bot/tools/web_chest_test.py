#!/usr/bin/env python
"""End-to-end chest loop against the local HTML stand-in page (web/fortnite_chest.html).

Why this exists: the Fortnite pipeline cannot be tested on a machine without the
game, and "the script ran" is not evidence. This test launches a real Chromium
window (Edge or Chrome, app mode, no address bar) pointed at a tiny local page
whose window title encodes the game state:

    FORWEB chest | far            chest out of reach
    FORWEB chest | IN RANGE (E)   pressing E opens it
    FORWEB chest | OPENED         it is open

then runs the exact production path - screen capture -> Jev vision model ->
SendInput keys - and proves the chest opened by reading the window title back.
No clicking on faith: the only thing that can flip the title to OPENED is the
interacted E key that the model chose.

Two modes:
  --baseline   no model calls: hold W in 0.5 s slices until IN RANGE, press E
               once. Proves the page + keyboard + capture path independently.
  (default)    Jev decides each step via afk.explore.plan_explore.

Examples:
  python tools/web_chest_test.py --baseline --scene fortnite --browser edge
  python tools/web_chest_test.py --scene fortnite --steps 12
  python tools/web_chest_test.py --scene dungeon --no-jev --show

Exit codes: 0 = chest opened, 2 = failed, 3 = setup error (no browser/window).
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import html as html_mod
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

try:  # Windows consoles default to cp936; screenshots paths and models emit UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - only if stdout is already closed
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from afk.capture import Frame, ScreenCapture  # noqa: E402
from afk.config import ConfigError, load_config  # noqa: E402
from afk.explore import (describe, frame_signature, plan_explore,  # noqa: E402
                         signature_similarity)
from afk.motion import CameraNoise, aim_px, plan_turn  # noqa: E402
from afk.geometry import Rect  # noqa: E402
from afk.jev import JevClient, JevError, TransportError  # noqa: E402
from afk.screens import questions_for  # noqa: E402
from afk.win32 import (RECT, WNDENUMPROC, client_rect, enable_dpi_awareness,  # noqa: E402
                       find_window, focus_window, is_foreground, make_input,
                       user32, window_title)

# SetWindowPos / SystemParametersInfoW are not prototyped in afk.win32; without
# argtypes, ctypes would truncate the 64-bit HWND and the screen RECT pointer.
user32.SetWindowPos.argtypes = (wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT)
user32.SetWindowPos.restype = wt.BOOL
user32.SystemParametersInfoW.argtypes = (wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT)
user32.SystemParametersInfoW.restype = wt.BOOL

PAGE = ROOT / "web" / "fortnite_chest.html"
OUT_ROOT = ROOT / "logs" / "web_chest"
DEV_ROOT = ROOT / "logs" / "web_chest_dev"

TITLE_TOKEN = "FORWEB"
CHROMIUM_CLASS = "Chrome_WidgetWin"

BROWSER_PATHS: dict[str, list[str]] = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
}

# Chromium flags: a throwaway profile keeps first-run/sign-in/session-restore
# chrome out of the picture, and app mode removes the address bar and tabs.
BROWSER_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-session-crashed-bubble",
    "--disable-features=Translate",
    "--disable-extensions",
    "--disable-sync",
]

CONTEXT = (
    "Goal: reach the chest and open it. This is a simple first-person test scene "
    "inside a browser window: a corridor recedes to a vanishing point, a chest sits "
    "ahead, and a hint line is drawn near the bottom. Walk forward while the chest is "
    "small and distant; once the chest is large and close (it fills much of the lower "
    "middle of the view) choose the interact action to open it. Do not back up or turn "
    "away unless something blocks the path. Do not press interact while the chest is "
    "still far away."
)


class SetupError(RuntimeError):
    """No browser, no window, no page: nothing was tested."""


# --------------------------------------------------------------------------- io
class Reporter:
    """Console log + a matching run.log, so the console tail is reproducible."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.lines: list[str] = []
        self.log_path = out_dir / "run.log"

    def __call__(self, message: str = "") -> None:
        print(message, flush=True)
        self.lines.append(message)

    def flush(self) -> None:
        try:
            self.log_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def mmss(elapsed: float) -> str:
    total = max(0, int(elapsed))
    return f"{total // 60:02d}:{total % 60:02d}"


# ------------------------------------------------------------------- windowing
def _window_info(hwnd: int) -> tuple[str, str, int]:
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return title.value, cls.value, int(pid.value)


def enum_titled(substr: str) -> list[tuple[int, str, str, int]]:
    """Every visible top-level window whose title contains `substr`.

    Needed because afk.win32.find_window() returns the first title match with no
    class or process filter, and Chromium family windows are class
    `Chrome_WidgetWin_1`. We keep the class and pid here so the caller can pick
    the window that actually belongs to the browser we just launched.
    """
    found: list[tuple[int, str, str, int]] = []
    needle = substr.lower()

    @WNDENUMPROC
    def _enum(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        title, cls, pid = _window_info(hwnd)
        if title and needle in title.lower():
            found.append((int(hwnd), cls, title, pid))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def locate_window(proc_pid: int, log: Reporter, timeout: float = 25.0) -> tuple[int, str, str]:
    """Poll for the app window; prefer the one owned by the browser we started."""
    deadline = time.monotonic() + timeout
    seen_classes: set[str] = set()
    while time.monotonic() < deadline:
        candidates = enum_titled(TITLE_TOKEN)
        if candidates:
            for hwnd, cls, title, pid in candidates:
                seen_classes.add(cls)
            mine = [c for c in candidates if c[3] == proc_pid]
            chromium = [c for c in candidates if c[1].startswith(CHROMIUM_CLASS)]
            pick = (mine or chromium or candidates)[0]
            hwnd, cls, title, pid = pick
            if not cls.startswith(CHROMIUM_CLASS):
                log(f"[setup] WARNING: title match has class {cls!r}, not a Chromium class; "
                    f"continuing because no better candidate exists")
            log(f"[setup] window hwnd=0x{hwnd:X} class={cls!r} pid={pid} title={title!r}")
            # Cross-check the shared helper so a divergence is visible in the log.
            shared = find_window(class_name="", title_substr=TITLE_TOKEN)
            log(f"[setup] afk.win32.find_window(class_name='') -> "
                f"{'0x%X' % shared if shared else 'None'}"
                f"{' (same window)' if shared == hwnd else ''}")
            return hwnd, cls, title
        time.sleep(0.35)

    detail = f" (classes seen for that title: {sorted(seen_classes)})" if seen_classes else ""
    raise SetupError(f"no visible window titled *{TITLE_TOKEN}* within {timeout:.0f}s{detail}")


def ensure_focus(hwnd: int, log: Reporter) -> bool:
    """Focus the window and confirm it is foreground before any injection."""
    for attempt in (1, 2):
        focus_window(hwnd)
        time.sleep(0.15)
        if is_foreground(hwnd):
            return True
        log(f"    focus lost (attempt {attempt}/2); retrying")
        time.sleep(0.25)
    return is_foreground(hwnd)


SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SPI_GETWORKAREA = 0x0030


def work_area() -> Rect:
    rc = RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0):
        return Rect(rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)
    return Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def fit_window(hwnd: int, log: Reporter, want_w: int = 1280, want_h: int = 800) -> None:
    """Place the app window fully inside the work area.

    Edge sizes app windows in DIPs, so at 150% scaling `--window-size=1280,800`
    can land larger than the physical screen. Off-screen pixels capture as junk
    (taskbar, stale desktop), so we pin the window to the work area in physical
    pixels after launch and let the page reflow.
    """
    area = work_area()
    width = min(want_w, max(480, area.width - 40))
    height = min(want_h, max(360, area.height - 40))
    ok = user32.SetWindowPos(hwnd, None, area.left + 20, area.top + 20, width, height,
                             SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.35)
    log(f"[setup] window placed at ({area.left + 20},{area.top + 20}) "
        f"{width}x{height} physical (work area {area.width}x{area.height}, ok={bool(ok)})")


def capture_rect(hwnd: int) -> Rect:
    """Client rect, clamped to the physical screen so BitBlt never reads past it."""
    left, top, width, height = client_rect(hwnd)
    screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    if left < 0 or top < 0 or left + width > screen_w or top + height > screen_h:
        left = max(0, min(left, screen_w - 1))
        top = max(0, min(top, screen_h - 1))
        width = max(1, min(width, screen_w - left))
        height = max(1, min(height, screen_h - top))
    return Rect(left, top, width, height)


# -------------------------------------------------------------------- browser
def find_browser(name: str) -> Path:
    tried = BROWSER_PATHS.get(name, [])
    for raw in tried:
        path = Path(raw)
        if path.exists():
            return path
    raise SetupError(f"{name} not found; tried:\n  " + "\n  ".join(tried))


def launch_browser(exe: Path, scene: str, out_dir: Path,
                   log: Reporter) -> tuple[subprocess.Popen, Path, object]:
    url = f"{PAGE.as_uri()}?scene={scene}"
    profile = Path(tempfile.gettempdir()) / f"forweb-{os.getpid()}"
    shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True, exist_ok=True)
    stderr_file = open(out_dir / "browser.log", "wb")  # noqa: SIM115 - closed in cleanup
    cmd = [
        str(exe),
        f"--app={url}",
        "--window-size=1280,800",
        f"--user-data-dir={profile}",
        *BROWSER_FLAGS,
    ]
    log(f"[setup] browser={exe}")
    log(f"[setup] profile={profile}")
    log(f"[setup] url={url}")
    print("[setup] launching: " + subprocess.list2cmdline(cmd), flush=True)
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=stderr_file, close_fds=True)
    except OSError as exc:
        stderr_file.close()
        raise SetupError(f"could not launch {exe}: {exc}") from exc
    log(f"[setup] pid={proc.pid}")
    return proc, profile, stderr_file


def kill_tree(pid: int) -> None:
    if pid <= 0:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
    except (OSError, subprocess.SubprocessError):
        pass


def force_close(hwnd: int | None, proc: subprocess.Popen | None) -> None:
    """The browser spawns renderer children; /T is what actually clears the windows."""
    if proc is not None and proc.poll() is None:
        kill_tree(proc.pid)
    if hwnd and user32.IsWindow(hwnd):
        _title, _cls, pid = _window_info(hwnd)
        if pid and pid != os.getpid():
            kill_tree(pid)
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        if not hwnd or not user32.IsWindow(hwnd):
            return
        time.sleep(0.2)


def remove_profile(profile: Path | None, log: Reporter) -> None:
    """Chromium holds file locks for a moment after taskkill; retry briefly."""
    if profile is None:
        return
    for attempt in (1, 2, 3, 4):
        if not profile.exists():
            return
        shutil.rmtree(profile, ignore_errors=True)
        if not profile.exists():
            return
        time.sleep(0.5 * attempt)
    if profile.exists():
        log(f"[cleanup] temp profile left behind (locked): {profile}")


def tail_browser_log(out_dir: Path, log: Reporter, lines: int = 12) -> None:
    path = out_dir / "browser.log"
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    tail = text[-lines:]
    if tail:
        log("[setup] browser.log tail:")
        for line in tail:
            log(f"    {line}")


# --------------------------------------------------------------------- capture
def grab_step(capture: ScreenCapture, hwnd: int, out_dir: Path, index: int) -> tuple[Frame, str]:
    rect = capture_rect(hwnd)
    frame = capture.grab(rect)
    name = f"step_{index:02d}.png"
    frame.save_png(out_dir / name)
    return frame, name


def summarize_obs(obs) -> dict:
    """Raw answers, trimmed to what is worth keeping in decisions.json."""
    return {
        "screen": obs.screen,
        "screen_confidence": round(obs.screen_confidence, 3),
        "screen_probabilities": obs.screen_probabilities,
        "model": obs.model,
        "usage": obs.usage,
        "answers": obs.answers,
    }


def ask_with_retry(client: JevClient, frame: Frame, questions: dict, log: Reporter):
    for attempt in (1, 2):
        started = time.monotonic()
        log("[jev] asking...")
        try:
            obs = client.ask(frame, questions, context=CONTEXT)
        except (JevError, TransportError) as exc:
            log(f"[jev] error (attempt {attempt}/2 after {time.monotonic() - started:.1f}s): {exc}")
            if attempt == 2:
                raise
            time.sleep(1.5)
            continue
        log(f"[jev] answered in {time.monotonic() - started:.1f}s "
            f"(screen={obs.screen} {obs.screen_confidence:.2f}, calls={client.calls})")
        return obs
    raise JevError("unreachable")


# -------------------------------------------------------------------- baseline
def run_baseline(hwnd: int, inputs, capture: ScreenCapture, out_dir: Path, log: Reporter,
                 steps: list[dict], t_run: float, walk_seconds: float = 20.0) -> tuple[bool, str]:
    """Hold W in 0.5 s slices until the title says IN RANGE, then press E once."""
    index = 0
    index += 1
    _frame, png = grab_step(capture, hwnd, out_dir, index)
    title = window_title(hwnd)
    steps.append({"index": index, "time": mmss(time.monotonic() - t_run), "title": title,
                  "plan_line": "baseline: capture start", "reason": "state at launch", "png": png})
    log(f"[b{index}] {mmss(time.monotonic() - t_run)} title={title!r}")

    if "OPENED" in title:
        return True, "already OPENED before any input (stale page?)"

    walked = 0
    last_title = title
    deadline = time.monotonic() + walk_seconds
    while "IN RANGE" not in title and time.monotonic() < deadline:
        if not ensure_focus(hwnd, log):
            return False, "lost foreground focus before the walk; refusing to type blind"
        inputs.hold(["w"], 0.5)
        time.sleep(0.12)
        title = window_title(hwnd)
        walked += 1
        log(f"[walk {walked:02d}] {mmss(time.monotonic() - t_run)} title={title!r}")
        if "OPENED" in title:
            index += 1
            _f, png = grab_step(capture, hwnd, out_dir, index)
            steps.append({"index": index, "time": mmss(time.monotonic() - t_run), "title": title,
                          "plan_line": "baseline: walked", "reason": "title already OPENED",
                          "png": png})
            return True, f"OPENED while walking after {walked} slices (page opened on W?)"
        last_title = title

    index += 1
    _f, png = grab_step(capture, hwnd, out_dir, index)
    steps.append({"index": index, "time": mmss(time.monotonic() - t_run), "title": title,
                  "plan_line": f"baseline: walk {walked} x 0.5s W",
                  "reason": "reached IN RANGE" if "IN RANGE" in title else "walk budget exhausted",
                  "png": png})
    log(f"[b{index}] {mmss(time.monotonic() - t_run)} title={title!r} "
        f"after {walked} walk slices")

    if "IN RANGE" not in title:
        return False, (f"title never said IN RANGE after {walked} W slices "
                       f"({walk_seconds:.0f}s); last title={title!r}")

    if not ensure_focus(hwnd, log):
        return False, "lost foreground focus before pressing E"
    log("[baseline] in range -> pressing E once")
    inputs.press("e", 0.12)
    time.sleep(1.2)
    title = window_title(hwnd)
    index += 1
    _f, png = grab_step(capture, hwnd, out_dir, index)
    steps.append({"index": index, "time": mmss(time.monotonic() - t_run), "title": title,
                  "plan_line": "baseline: press E (0.12s)", "reason": "in range",
                  "png": png})
    log(f"[b{index}] {mmss(time.monotonic() - t_run)} title={title!r} after E")
    if "OPENED" in title:
        return True, "E opened the chest on the first press"
    return False, f"E did not open the chest; title={title!r}"


# ------------------------------------------------------------------ jev phase
def run_jev(hwnd: int, inputs, capture: ScreenCapture, cfg, out_dir: Path, log: Reporter,
            steps: list[dict], t_run: float, args, state: dict) -> tuple[bool, str]:
    """Capture -> ask Jev -> plan_explore -> inject -> read the title back."""
    client: JevClient | None = None
    try:
        client = JevClient(cfg)
    except ConfigError as exc:
        raise SetupError(f"Jev client not configured: {exc}") from exc

    questions = questions_for(cfg.explore.question_profile)
    rng = random.Random()
    state["model"] = cfg.model
    noise = CameraNoise(rng, cfg.turn)

    last_interact_at = -999.0
    last_interact_sig: tuple[int, ...] | None = None
    held_keys: set[str] = set()
    ever_interact = False
    opened = False
    failure = ""
    no_progress = 0
    last_sig: tuple[int, ...] = ()

    for step in range(1, args.steps + 1):
        if not ensure_focus(hwnd, log):
            failure = "lost foreground focus; refusing to inject input blind"
            break

        frame, png = grab_step(capture, hwnd, out_dir, step)
        title_before = window_title(hwnd)

        try:
            obs = ask_with_retry(client, frame, questions, log)
        except (JevError, TransportError) as exc:
            failure = f"Jev failed twice: {exc}"
            log(f"[{step}] {failure}")
            break
        state["calls"] = client.calls
        state["cost"] = client.total_cost

        chest_ready = (time.monotonic() - last_interact_at) >= 5.0
        plan = plan_explore(obs, cfg, rng, chest_ready=chest_ready)
        # Same guard as the production controller: if the last E changed nothing
        # on screen we were out of range, so walk closer instead of pressing
        # again. Without it the model happily presses E forever at 4 m.
        if last_interact_sig is not None:
            change = signature_similarity(last_interact_sig, frame_signature(frame))
            last_interact_sig = None
            if change >= 0.995 and plan.action in ("interact", "attack", "aim"):
                log(f"[{step}] previous interact changed nothing "
                    f"(similarity {change:.3f}); walking closer")
                plan = replace(plan, keys=["w"], action="move_forward",
                               interact=False, jump=False, hold_s=0.6,
                               hold_label="medium", continuous=True, aim_norm=0.0,
                               reason="interact had no effect -> advance")
        plan_line = describe(plan)
        log(f"[{step}] {mmss(time.monotonic() - t_run)} title={title_before} "
            f"plan={plan_line} | {plan.reason}")

        note = ""
        if not ensure_focus(hwnd, log):
            failure = "lost foreground focus before injection"
            break

        rect = capture_rect(hwnd)
        cx, cy = rect.left + rect.width // 2, rect.top + rect.height // 2
        try:
            if plan.interact:
                ever_interact = True
                last_interact_at = time.monotonic()
                last_interact_sig = frame_signature(frame)
                held_keys.clear()
                inputs.release_all()
                inputs.press("e", 0.12)
                note = "pressed E, settling 1.2s"
                time.sleep(1.2)
            else:
                if plan.keys and plan.continuous:
                    # Mirror the production controller: keep the direction held
                    # across decisions and only diff the key set. Releasing and
                    # re-pressing every step is what made the bot look robotic.
                    new = {k.lower() for k in plan.keys}
                    for key in held_keys - new:
                        inputs.key_up(key)
                    for key in new - held_keys:
                        inputs.key_down(key)
                    held_keys.clear()
                    held_keys.update(new)
                    note = f"continuous {sorted(new)}"
                else:
                    if held_keys:
                        held_keys.clear()
                        inputs.release_all()
                    if plan.keys:
                        slice_s = max(0.05, min(plan.hold_s, 0.9))
                        repeat = max(1, min(3, plan.repeat or 1))
                        if slice_s * repeat > 1.6:
                            slice_s = 1.6 / repeat
                        for _ in range(repeat):
                            inputs.hold(list(plan.keys), slice_s)
                            time.sleep(0.05)
                        note = f"held {plan.keys} {slice_s:.2f}s x{repeat}"
                if plan.jump:
                    inputs.press("space", 0.08)
                    note = (note + "; jumped").strip("; ")
                if plan.look_dx or plan.aim_norm:
                    # Same eased turn as the production controller: aim at the
                    # object Jev found, then apply any explicit look request.
                    turn_px = 0
                    if plan.aim_norm:
                        turn_px += aim_px(0.5 + plan.aim_norm, frame.width, cfg.turn)
                    if plan.look_dx:
                        turn_px += plan.look_dx
                    if turn_px:
                        if cfg.explore.smooth_turn:
                            ticks = plan_turn(turn_px, cfg.turn)
                            for delta in ticks:
                                nx, ny = noise.step(cfg.turn.tick_s)
                                inputs.move_relative(delta + nx, ny)
                                time.sleep(cfg.turn.tick_s)
                            note = (note + f"; turn {turn_px}px/{len(ticks)} ticks").strip("; ")
                        else:
                            inputs.move_relative(turn_px, 0)
                            note = (note + f"; turn {turn_px}px").strip("; ")
                    else:
                        nx, ny = noise.step(0.10)
                        if nx or ny:
                            inputs.move_relative(nx, ny)
                            note = (note + f"; gaze {nx:+d}").strip("; ")
                elif plan.keys:
                    # Idle gaze drift while just walking: hands are never still.
                    nx, ny = noise.step(0.10)
                    if nx or ny:
                        inputs.move_relative(nx, ny)
                if plan.mouse:
                    inputs.click(cx, cy, button=plan.mouse)
                    note = (note + f"; click {plan.mouse}").strip("; ")
        except Exception as exc:  # noqa: BLE001 - never lose the report over an input error
            failure = f"input error: {exc}"
            log(f"[{step}] {failure}")
            break

        time.sleep(0.18)
        title_after = window_title(hwnd)
        log(f"[{step}] -> title={title_after} ({note or 'no input'})")

        sig = frame_signature(frame)
        similarity = signature_similarity(last_sig, sig) if last_sig else 0.0
        last_sig = sig

        entry = {
            "index": step,
            "time": mmss(time.monotonic() - t_run),
            "title": title_after,
            "title_before": title_before,
            "png": png,
            "plan_line": plan_line,
            "plan": asdict(plan),
            "reason": plan.reason,
            "note": note,
            "action_executed": "interact" if plan.interact else (plan.action or plan.move),
            "observation": summarize_obs(obs),
        }
        steps.append(entry)

        if "OPENED" in title_after:
            opened = True
            log(f"[{step}] CHEST OPENED")
            break

        # Guard rail: title unchanged *and* the frame did not move at all.
        moved = plan.keys or plan.jump or plan.look_dx or plan.mouse
        if title_after == title_before and similarity >= 0.99 and moved:
            no_progress += 1
        else:
            no_progress = 0
        if no_progress >= 3:
            log(f"  WARNING: {no_progress} consecutive steps with no title change and an "
                f"identical frame while choosing movement - the model may be stuck on a wall")
            no_progress = 0

    if held_keys:
        held_keys.clear()
        try:
            inputs.release_all()
        except Exception:  # noqa: BLE001 - cleanup must not mask the verdict
            pass

    if opened:
        return True, "the model chose interact and the chest opened"

    if failure:
        return False, failure
    if not ever_interact:
        return False, "model never chose interact"
    return False, (f"interact chosen but the title never reached OPENED "
                   f"after {args.steps} steps")


# ------------------------------------------------------------------ capture-only
def run_capture_only(hwnd: int, capture: ScreenCapture, out_dir: Path, log: Reporter,
                     steps: list[dict], t_run: float, count: int) -> tuple[bool, str]:
    title = window_title(hwnd)
    for step in range(1, count + 1):
        if not ensure_focus(hwnd, log):
            return False, "lost foreground focus while capturing"
        _frame, png = grab_step(capture, hwnd, out_dir, step)
        title = window_title(hwnd)
        log(f"[{step}] {mmss(time.monotonic() - t_run)} title={title} plan=capture-only | "
            f"no model, no input")
        steps.append({"index": step, "time": mmss(time.monotonic() - t_run), "title": title,
                      "plan_line": "capture only (no model, no input)",
                      "reason": "diagnostic run", "png": png})
        time.sleep(0.8)
        if "OPENED" in title:
            return True, "capture-only run, page was already OPENED"
    return False, "capture-only run: no input was sent, so the chest cannot open"


# ---------------------------------------------------------------------- report
def build_report(out_dir: Path, meta: dict, steps: list[dict], opened: bool,
                 note: str) -> Path:
    esc = html_mod.escape
    verdict_cls = "pass" if opened else "fail"
    verdict_text = "CHEST OPENED" if opened else "FAIL"
    cards = []
    for step in steps:
        img = step.get("png")
        img_html = (f"<img src='{esc(img)}' alt='step {step.get('index')}'>"
                    if img else "")
        extra = ""
        if step.get("note"):
            extra += f"<div class='reason'><b>sent:</b> {esc(step['note'])}</div>"
        if step.get("title_before") and step.get("title_before") != step.get("title"):
            extra += (f"<div class='reason'><b>title before:</b> "
                      f"{esc(step['title_before'])}</div>")
        cards.append(
            "<div class='card'>"
            f"{img_html}"
            f"<div class='head'>[{step.get('index')}] {esc(step.get('time', ''))} "
            f"&middot; title=<span class='t'>{esc(step.get('title', ''))}</span></div>"
            "<div class='body'>"
            f"<div><b>plan:</b> <code>{esc(step.get('plan_line', '-'))}</code></div>"
            f"<div class='reason'><b>reason:</b> {esc(step.get('reason', ''))}</div>"
            f"{extra}"
            "</div></div>"
        )

    extra_meta = ""
    if meta.get("calls"):
        extra_meta = (f", model=<code>{esc(str(meta.get('model', '')))}</code>, "
                      f"calls={meta['calls']}, cost=${meta.get('cost', 0.0):.5f}")
    page = f"""<!doctype html><meta charset="utf-8">
<title>Web chest test &mdash; {esc(meta.get('scene', ''))} ({esc(meta.get('mode', ''))})</title>
<style>
 body{{background:#12161e;color:#e8edf5;font:14px/1.55 "Segoe UI",Arial,sans-serif;
      margin:0;padding:26px 28px 48px}}
 h1{{font-size:20px;margin:0 0 6px}}
 .meta{{color:#8fa0b8;font-size:13px;margin-bottom:14px}}
 .verdict{{margin:18px 0 10px;padding:18px 22px;border-radius:12px;font-size:27px;
           font-weight:700;letter-spacing:.6px}}
 .pass{{background:rgba(46,204,113,.13);border:1px solid #2ecc71;color:#7ee2a8}}
 .fail{{background:rgba(231,76,60,.13);border:1px solid #e74c3c;color:#ff9b8f}}
 .note{{color:#cbd5e1;margin:0 0 18px;white-space:pre-wrap}}
 .cmd{{padding:10px 14px;background:#0b0f15;border:1px solid #263041;border-radius:8px;
       font-family:Consolas,"Courier New",monospace;font-size:12.5px;overflow-x:auto;
       color:#9fb3cc;white-space:pre-wrap}}
 .card{{background:#151a23;border:1px solid #263041;border-radius:10px;margin:14px 0;
        overflow:hidden}}
 .card img{{display:block;width:620px;max-width:100%;border-bottom:1px solid #263041}}
 .head{{padding:9px 14px;border-bottom:1px solid #263041;
        font-family:Consolas,"Courier New",monospace;font-size:12.5px;color:#9fb3cc}}
 .head .t{{color:#e8edf5}}
 .body{{padding:10px 14px}}
 .reason{{color:#cbd5e1}}
 code{{color:#7ee2a8;background:#0b0f15;padding:1px 5px;border-radius:4px;
       font-family:Consolas,"Courier New",monospace}}
 small{{color:#8fa0b8}}
</style>
<h1>Web chest test &mdash; {esc(meta.get('scene', ''))}</h1>
<div class="meta">mode=<code>{esc(meta.get('mode', ''))}</code>, browser=<code>{esc(meta.get('browser', ''))}</code>,
window=<code>{esc(meta.get('window', ''))}</code>, client={esc(str(meta.get('client', '')))},
steps={len(steps)}{extra_meta}</div>
<div class="verdict {verdict_cls}">{verdict_text}</div>
<p class="note">{esc(note)}</p>
<div class="cmd">command: {esc(meta.get('command', ''))}</div>
{''.join(cards)}
"""
    path = out_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path


# ------------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="End-to-end chest test on a local HTML page.")
    parser.add_argument("--scene", choices=["fortnite", "dungeon"], default="fortnite",
                        help="passed to the page as ?scene=")
    parser.add_argument("--baseline", action="store_true",
                        help="no model calls: walk W then press E once")
    parser.add_argument("--steps", type=int, default=12, help="max Jev decisions")
    parser.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    parser.add_argument("--no-jev", action="store_true", help="capture + log only, no model, no input")
    parser.add_argument("--dry-run", action="store_true", help="capture + log only, no input")
    parser.add_argument("--show", action="store_true", help="leave the browser open afterwards")
    parser.add_argument("--pre-turn-ms", type=int, default=0,
                        help="hold ArrowLeft this long before the run, so the chest "
                             "starts off-centre and the aim path is exercised")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    t_run = time.monotonic()
    started = datetime.now()
    capture_only = args.no_jev or args.dry_run
    suffix = "_baseline" if (args.baseline and not capture_only) else ""
    out_dir = OUT_ROOT / f"{started:%Y%m%d_%H%M%S}_{args.scene}{suffix}"
    command = subprocess.list2cmdline([sys.executable, *sys.argv])
    short_command = (f"python tools/web_chest_test.py --scene {args.scene}"
                     + (" --baseline" if args.baseline else "")
                     + (f" --steps {args.steps}" if not args.baseline else "")
                     + f" --browser {args.browser}"
                     + (" --no-jev" if args.no_jev else "")
                     + (" --dry-run" if args.dry_run else "")
                     + (" --show" if args.show else ""))

    print("=" * 78)
    print("web chest test")
    print(f"command: {short_command}")
    print(f"argv:    {command}")
    print("=" * 78, flush=True)

    if not PAGE.exists():
        print(f"REFUSING TO START: page not found at {PAGE}", flush=True)
        print("Expected the local test page to exist (another agent writes it).", flush=True)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    DEV_ROOT.mkdir(parents=True, exist_ok=True)
    log = Reporter(out_dir)

    mode = "baseline" if (args.baseline and not capture_only) else (
        "capture-only" if capture_only else "jev")
    meta: dict = {
        "scene": args.scene,
        "mode": mode,
        "browser": args.browser,
        "command": short_command,
        "argv": command,
        "started": started.isoformat(timespec="seconds"),
        "steps_allowed": args.steps,
    }
    steps: list[dict] = []
    state: dict = {}
    opened = False
    note = ""
    hwnd: int | None = None
    proc: subprocess.Popen | None = None
    profile: Path | None = None
    stderr_file = None
    exit_code = 2

    try:
        enable_dpi_awareness()
        exe = find_browser(args.browser)
        proc, profile, stderr_file = launch_browser(exe, args.scene, out_dir, log)
        hwnd, cls, title = locate_window(proc.pid, log)
        meta["window"] = f"0x{hwnd:X} {cls}"
        meta["launch_title"] = title
        fit_window(hwnd, log)

        try:
            cfg = load_config()
        except ConfigError as exc:
            raise SetupError(f"config error: {exc}") from exc
        cfg.capture.max_width = 1280
        cfg.safety.dry_run = False
        if cfg.input_backend != "sendinput":
            log(f"[setup] input_backend={cfg.input_backend} -> forcing sendinput "
                f"(the browser needs real OS keystrokes)")
            cfg.input_backend = "sendinput"
        log(f"[setup] config: model={cfg.model} input={cfg.input_backend}/{cfg.key_mode} "
            f"explore.chest_cooldown={cfg.explore.chest_cooldown_s:.0f}s")

        rng = random.Random()
        inputs = make_input(cfg, hwnd, rng)
        capture = ScreenCapture(max_width=cfg.capture.max_width)
        cr = capture_rect(hwnd)
        meta["client"] = [cr.left, cr.top, cr.width, cr.height]

        if not ensure_focus(hwnd, log):
            raise SetupError("could not bring the browser window to the foreground")
        # One click at the client centre: Chromium only routes keydown to the page
        # once the document has focus, and a stray click does nothing on the page.
        rect = capture_rect(hwnd)
        inputs.click(rect.left + rect.width // 2, rect.top + rect.height // 2)
        time.sleep(0.3)

        if args.pre_turn_ms:
            # Rotate the camera so the chest starts off-centre; the aim path then
            # has to turn back toward it instead of finding it dead ahead.
            log(f"[run] pre-turn: holding ArrowLeft for {args.pre_turn_ms}ms")
            inputs.hold(["left"], args.pre_turn_ms / 1000.0)
            time.sleep(0.4)

        if capture_only:
            log("[run] capture-only: no model calls, no input")
            opened, note = run_capture_only(hwnd, capture, out_dir, log, steps, t_run,
                                            max(1, args.steps))
        elif args.baseline:
            log("[run] baseline: W in 0.5s slices until IN RANGE, then one E")
            opened, note = run_baseline(hwnd, inputs, capture, out_dir, log, steps, t_run)
        else:
            log(f"[run] jev: up to {args.steps} decisions")
            opened, note = run_jev(hwnd, inputs, capture, cfg, out_dir, log, steps,
                                   t_run, args, state)
            meta["model"] = state.get("model", cfg.model)
            meta["calls"] = state.get("calls", 0)
            meta["cost"] = state.get("cost", 0.0)
        try:
            inputs.release_all()
        except Exception:
            pass
    except SetupError as exc:
        note = f"setup error: {exc}"
        log(f"[setup] {note}")
        if proc is not None:
            tail_browser_log(out_dir, log)
        exit_code = 3
    except Exception:  # noqa: BLE001 - keep the report even on an unexpected crash
        note = "unexpected error:\n" + traceback.format_exc()
        log(note)
        exit_code = 2
    finally:
        try:
            if stderr_file is not None:
                stderr_file.close()
        except Exception:
            pass
        if args.show:
            log("[cleanup] --show: leaving the browser open for inspection")
        else:
            log("[cleanup] closing the browser")
            force_close(hwnd, proc)
            remove_profile(profile, log)
        log.flush()

    # ------------------------------------------------------------- verdict + report
    if exit_code == 3:
        print(f"VERDICT: SETUP ERROR ({note})", flush=True)
        return 3

    meta.setdefault("calls", 0)
    meta.setdefault("cost", 0.0)
    verdict_ok = opened
    if opened:
        exit_code = 0
    else:
        exit_code = 2

    report = None
    try:
        report = build_report(out_dir, meta, steps, opened, note)
    except Exception:  # noqa: BLE001 - a broken report must not mask the verdict
        print("could not write report.html:\n" + traceback.format_exc(), flush=True)

    decisions = {
        "scene": args.scene,
        "mode": mode,
        "verdict": "PASS" if opened else "FAIL",
        "note": note,
        "command": short_command,
        "browser": args.browser,
        "window": meta.get("window"),
        "client": meta.get("client"),
        "steps_allowed": args.steps,
        "steps": steps,
    }
    try:
        (out_dir / "decisions.json").write_text(
            json.dumps(decisions, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"could not write decisions.json: {exc}", flush=True)

    print("-" * 78)
    print(f"steps={len(steps)} note={note}")
    if report is not None:
        print(f"report: {report}")
    print(f"outdir: {out_dir}")
    print(f"VERDICT: {'PASS' if verdict_ok else 'FAIL'}")
    print("-" * 78, flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
