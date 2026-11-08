#!/usr/bin/env python
"""Layered session loop: judge -> act -> calibrate -> next match.

Why layers instead of one giant question set:

* The **judge** answers one cheap question ("where are we?") with a tiny
  question set. It runs every cycle and must be fast and stable.
* The **actor** only runs after the judge has picked a branch. In a match it
  gets the gameplay questions; outside a match it gets the UI questions
  (which button advances us toward the next game). One model call each, but
  each call sees only the questions that make sense for that branch.
* The **sensitivity probe** asks the model to compare a before/after pair and
  say whether the view turned too little or too much. It runs occasionally,
  not every step, because it costs a second call.

The loop keeps cycling through results -> lobby -> PLAY, so a finished match
does not strand the bot.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import sys
import time
from dataclasses import replace
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from afk import cloud, screens  # noqa: E402
from afk.calibration import clamp as clamp_scale  # noqa: E402
from afk.calibration import load_scale, save_scale  # noqa: E402
from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.explore import (describe, frame_signature, plan_explore,  # noqa: E402
                         signature_similarity)
from afk.geometry import Rect, box_center_screen  # noqa: E402
from afk.jev import JevClient, JevError, TransportError  # noqa: E402
from afk.motion import CameraNoise, aim_px, aim_py, plan_turn  # noqa: E402
from afk.screens import menu_questions, questions_for  # noqa: E402
from afk.uiagent import (DROP_QUESTIONS, SENSITIVITY_QUESTIONS,  # noqa: E402
                         UI_START_QUESTIONS)
from afk.win32 import InputController, enable_dpi_awareness  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

JUDGE_QUESTIONS = {
    "screen": {
        "type": "choice",
        "instructions": (
            "One question only: which exact game state is on screen? Judge from "
            "the whole image, including any streaming or browser chrome. Pick the "
            "most specific state that fits."
        ),
        "criteria": {
            "bus": "On the battle bus / flying ship: the island is below, a minimap is shown, and there may be a 'Space to jump' prompt.",
            "skydive": "Free-falling high above the ground with no glider open.",
            "glide": "Descending under a glider or parachute.",
            "in_match": "Standing on the ground in live gameplay: terrain at eye level, weapon and HUD visible.",
            "lobby": "The main lobby with a big PLAY button and no searching timer.",
            "queue": "Matchmaking inside the lobby: a Finding Server timer and a CANCEL button.",
            "results": "End-of-match recap with placement, XP, or a RETURN TO LOBBY / CONTINUE button.",
            "eliminated": "Eliminated or spectating: a death message or another player's camera, no control of the character.",
            "loading": "A pure loading screen with no world visible.",
            "other": "Island pages, store, settings, error dialogs, desktop, or anything else.",
        },
    },
    "drop_now": {
        "type": "noul",
        "instructions": (
            "If the player is on the bus: is the island close enough that jumping now "
            "would land on it? False while it is still far away."
        ),
    },
}


class Session:
    def __init__(self, args) -> None:
        self.args = args
        self.cfg = load_config(ROOT / "config.json")
        self.rect = Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        self.capture = ScreenCapture(self.cfg.capture.max_width)
        self.depth = max(1, int(getattr(args, "depth", 1)))
        # One keep-alive connection per in-flight request: a socket can only
        # carry one HTTP request at a time, so pipelining needs separate
        # clients rather than one shared connection.
        self.clients = [JevClient(self.cfg) for _ in range(self.depth)]
        self.client = self.clients[0]
        self.inputs = InputController(dry_run=not args.act, key_mode=self.cfg.key_mode)
        self.noise = CameraNoise(random.Random(), self.cfg.turn)
        self.aim_gain = self.cfg.turn.gain
        # Fixed sensitivity: the persisted number is used as-is for every turn.
        # `--calibrate` re-enables the adaptive probe; by default the bot does
        # not spend a model call re-measuring the camera mid-match.
        default_scale = float(self.cfg.turn.px_per_screen)
        if getattr(args, "scale", None):
            self.scale = clamp_scale(args.scale)
            save_scale(self.scale, source="cli")
        else:
            self.scale = load_scale(default_scale)
        self.turn_cfg = replace(self.cfg.turn, px_per_screen=self.scale)
        self.held: set[str] = set()
        self.steps: list[dict] = []
        self.in_match_steps = 0
        self.last_sig: tuple[int, ...] = ()
        self.where = "lobby"
        self.pool = ThreadPoolExecutor(max_workers=self.depth)
        # (frame, future) pairs currently at the model, oldest first.
        self.inflight: list[tuple[object, object, float, int | None]] = []
        self.submitted = 0
        self.last_submit_at: float | None = None
        self.no_move = 0
        self.leave_attempts = 0
        self.bus_steps = 0
        self.chest_ready_at = 0.0
        self.last_sim = None
        self.last_action = ""
        self.same_action = 0

    # ---------------------------------------------------------------- input
    def release(self) -> None:
        for key in list(self.held):
            self.inputs.key_up(key)
        self.held.clear()

    def turn(self, dx: int, dy: int = 0) -> None:
        sx = plan_turn(dx, self.turn_cfg) if dx else []
        sy = plan_turn(dy, self.turn_cfg) if dy else []
        for i in range(max(len(sx), len(sy))):
            nx, ny = self.noise.step(self.turn_cfg.tick_s)
            self.inputs.move_relative((sx[i] if i < len(sx) else 0) + nx,
                                      (sy[i] if i < len(sy) else 0) + ny)
            time.sleep(self.turn_cfg.tick_s)

    def click_box(self, box) -> tuple[int, int]:
        x, y = box_center_screen(box, self.rect)
        self.inputs.click(x, y)
        return x, y

    # ----------------------------------------------------------------- judge
    def judge(self, frame):
        obs = self.client.ask(frame, JUDGE_QUESTIONS,
                              context="Routing decision only.")
        return obs.screen, obs.screen_confidence, obs

    # ------------------------------------------------------------- in match
    def ask_match(self, client, frame):
        """Fire the gameplay question for `frame` (runs on a worker thread)."""
        self.in_match_steps += 1
        return client.ask(frame, questions_for(self.cfg.explore.question_profile))

    def submit_match(self, frame):
        """Queue one gameplay question on a free client/connection."""
        client = self.clients[self.submitted % len(self.clients)]
        now = time.monotonic()
        gap = None if self.last_submit_at is None else round(
            (now - self.last_submit_at) * 1000)
        self.last_submit_at = now
        self.submitted += 1
        return self.pool.submit(self.ask_match, client, frame), now, gap

    def pump_match(self, frame) -> dict:
        """Keep `depth` gameplay questions in flight, apply the oldest answer.

        One request takes seconds, so waiting for it before looking at the next
        frame caps the bot at one decision per round trip. With two requests in
        flight a fresh decision lands every latency/2, and each plan is based on
        a frame from about one round trip ago - the same staleness as before,
        but there is always another answer already on the way.
        """
        if not self.submitted:
            # Cold start: a second identical request would just return the same
            # answer, so the pipeline warms up with one call.
            self.inflight.append((frame, *self.submit_match(frame)))
        else:
            while len(self.inflight) < self.depth:
                shot = self.capture.grab(self.rect)
                self.inflight.append((shot, *self.submit_match(shot)))

        shot, future, sent_at, gap = self.inflight.pop(0)
        obs = future.result()
        plan, conf = self.plan_from(obs, shot)
        record = self.execute_plan(plan, shot)
        record.update({"action_conf": round(conf, 3),
                       "screen": obs.screen,
                       "screen_conf": round(obs.screen_confidence, 3),
                       "api_age_ms": round((time.monotonic() - sent_at) * 1000),
                       "http_ms": round(float(obs.timings.get("http_ms", 0))),
                       "req_gap_ms": gap})
        if self.args.calibrate and self.in_match_steps % self.args.probe_every == 0:
            self.probe_sensitivity()
        return record

    def plan_from(self, obs, frame):
        plan = plan_explore(obs, self.cfg, random.Random(),
                            chest_ready=time.monotonic() >= self.chest_ready_at)
        _, conf = obs.choice("action")
        return plan, conf

    def execute_plan(self, plan, frame) -> dict:
        """Apply a plan. Runs while the next model call is already in flight."""
        sim = (round(signature_similarity(self.last_sig, frame_signature(frame)), 4)
               if self.last_sig else None)
        self.last_sig = frame_signature(frame)
        self.last_sim = sim

        # Same verb three decisions in a row while the picture barely changes:
        # the plan is not working (usually jumping at a wall the model believes
        # is low). Turn away so the next answer sees a different view.
        if plan.action and plan.action == self.last_action and sim is not None and sim >= 0.90:
            self.same_action += 1
        else:
            self.same_action = 1
        self.last_action = plan.action
        if self.same_action >= 3:
            self.same_action = 0
            self.release()
            self.turn(random.choice((-1, 1)) * random.randint(220, 320))
            return {"layer": "match", "plan": "stuck escape", "keys": [],
                    "similarity": sim, "merged": [],
                    "reason": f"{plan.action} repeated with no progress"}

        # Start the legs before the camera: holding W/D first and turning
        # second means the character walks a curve. Turning first and moving
        # after looks like a turret rotating in place, and wastes the whole
        # turn as dead time.
        if plan.keys and plan.continuous:
            new = {k.lower() for k in plan.keys}
            for key in self.held - new:
                self.inputs.key_up(key)
            for key in new - self.held:
                self.inputs.key_down(key)
            self.held = new

        if plan.aim_norm or plan.aim_norm_y:
            dx = aim_px(0.5 + plan.aim_norm, frame.width, self.turn_cfg,
                        gain=self.aim_gain) if plan.aim_norm else 0
            dy = aim_py(0.5 + plan.aim_norm_y, frame.height, self.turn_cfg,
                        gain=self.aim_gain) if plan.aim_norm_y else 0
            self.turn(dx, dy)
        elif plan.look_dx:
            # look_left / look_right are planned as a pixel delta on the same
            # eased profile as aiming. Without this branch the camera never
            # actually moved and every scan decision was a no-op.
            self.turn(plan.look_dx)
        if plan.interact:
            self.release()
            self.inputs.press(self.cfg.explore.interact_key, 0.12)
            # One press per chest. The model keeps seeing the same box while the
            # open animation runs, and hammering E on it burns whole decisions.
            self.chest_ready_at = time.monotonic() + 3.0
        elif plan.jump:
            self.inputs.press("space", 0.08)
        elif plan.mouse:
            cx, cy = self.rect.left + self.rect.width // 2, self.rect.top + self.rect.height // 2
            if plan.hold_s <= 0.2:
                self.inputs.click(cx, cy, button=plan.mouse)
            else:
                self.inputs.mouse_down(plan.mouse)
                time.sleep(min(plan.hold_s, 1.2))
                self.inputs.mouse_up(plan.mouse)
        elif plan.keys and plan.continuous:
            new = {k.lower() for k in plan.keys}
            for key in self.held - new:
                self.inputs.key_up(key)
            for key in new - self.held:
                self.inputs.key_down(key)
            self.held = new
        elif plan.keys:
            self.release()
            self.inputs.hold(list(plan.keys), min(plan.hold_s, 1.2))
        else:
            self.release()

        return {"layer": "match", "plan": describe(plan),
                "keys": sorted(self.held), "similarity": sim,
                "merged": plan.merged, "reason": plan.reason}

    def refocus(self) -> bool:
        """Bring the game back without touching a single window handle.

        Alt+Tab is the one window switcher that runs on SendInput alone: no
        enumeration, no process handle, nothing to open. The bot taps it and
        asks the judge whether the picture now shows the game; anything that is
        not the game means another tap. If the game already had focus (the
        character was just stuck), the first tap moves away, the judge says so,
        and the next tap comes straight back.
        """
        self.release()
        baseline = frame_signature(self.capture.grab(self.rect))
        for attempt in range(1, 5):
            self.inputs.key_down("alt")
            self.inputs.press("tab", 0.05)
            self.inputs.key_up("alt")
            time.sleep(0.8)
            probe = self.capture.grab(self.rect)
            sig = frame_signature(probe)
            if signature_similarity(baseline, sig) >= 0.98:
                continue  # the switch did not happen; keep cycling
            baseline = sig
            try:
                where, conf, _ = self.judge(probe)
            except (JevError, TransportError) as exc:
                print(f"        refocus: judge failed ({exc})")
                return False
            if where not in ("other", "loading"):
                print(f"        refocus: back on the game ({where} {conf:.2f}) "
                      f"after {attempt} Alt+Tab")
                return True
        print("        refocus: could not reach the game with Alt+Tab")
        return False

    # ------------------------------------------------------------ out match
    def step_leave(self, frame) -> dict:
        """Eliminated / results: get out through the pause menu.

        The generic UI question set has no "leave match" action, so this uses
        the menu set: confirm an open dialog first, then Leave Match, then the
        results screen's Return to Lobby. Esc opens the pause menu when the
        death screen has no clickable button yet.
        """
        obs = self.client.ask(frame, menu_questions(),
                              context="We are out of the match and want the lobby.")
        # Stay in this layer for the next few steps even if the judge sees the
        # pause menu as "other": it belongs to leaving, not to the lobby flow.
        self.leave_attempts = 3
        screen, _ = obs.choice("screen")
        for action, name in (("confirm", "confirm_button"),
                             ("leave", "leave_button"),
                             ("return", "return_lobby_button")):
            box = obs.usable_box(name, min_confidence=0.30, min_presence=0.45,
                                 allow_null=False, max_side=0.95)
            if box is not None:
                x, y = self.click_box(box)
                time.sleep(1.2)
                return {"layer": "leave", "screen": screen, "action": action,
                        "note": f"clicked {action} at ({x},{y})"}
        before = self.capture.grab(self.rect)
        self.inputs.press("esc", 0.10)
        time.sleep(1.0)
        after = self.capture.grab(self.rect)
        if signature_similarity(frame_signature(before),
                                frame_signature(after)) >= 0.99:
            # Esc changed nothing at all. Either the death screen ignores it or
            # the key never reached the game; Alt+Tab tells the two apart.
            print("        Esc had no visible effect; checking focus")
            if self.refocus():
                return {"layer": "leave", "screen": screen, "action": "refocus",
                        "note": "Esc did nothing; refocused the game"}
        return {"layer": "leave", "screen": screen, "action": "esc",
                "note": "no button: pressed Esc to open the pause menu"}

    def step_drop(self, frame) -> dict:
        """Bus / free-fall / glider handling - the part that was missing.

        The judge puts all of these under "loading", which used to mean "wait
        forever". The drop layer asks where in the drop we are and either jumps
        off the bus or steers toward the ground.
        """
        obs = self.client.ask(frame, DROP_QUESTIONS,
                              context="The player must get from the bus to the ground.")
        phase, phase_conf = obs.choice("phase")
        drop_now = obs.noul("drop_now") or 0.0
        note = f"phase={phase} drop_now={drop_now:.2f}"
        if phase == "bus" and drop_now >= 0.40:
            self.inputs.press("space", 0.08)
            note = "jumped off the bus (Space)"
        elif phase in ("skydive", "glide"):
            if not self.held:
                self.inputs.key_down("w")
                self.held = {"w"}
            self.turn(0, 45)  # look down a little while falling
            note = f"{phase}: holding W and looking down"
        elif phase == "ground":
            self.where = "in_match"
            note = "landed -> in_match"
        else:
            time.sleep(1.0)
        return {"layer": "drop", "phase": phase, "confidence": round(phase_conf, 3),
                "drop_now": round(drop_now, 2), "note": note,
                "screen": "loading", "screen_conf": 1.0}

    def step_ui(self, frame) -> dict:
        obs = self.client.ask(frame, UI_START_QUESTIONS,
                              context="We want the next match. Pick the one button.")
        screen, _ = obs.choice("screen")
        action, action_conf = obs.choice("target_action")
        # Only trust a box when the model actually named an action. Answering
        # "none" still produces a box sometimes, and clicking those is how the
        # bot used to end up poking empty corners of the death screen.
        box = None
        if action not in (None, "none", "wait") and action_conf >= 0.20:
            box = obs.usable_box("target_button", min_confidence=0.25,
                                 min_presence=0.40, allow_null=False,
                                 max_side=0.95)
        note = "no box"
        if box is not None:
            x, y = self.click_box(box)
            note = f"clicked {action} at ({x},{y})"
            time.sleep(1.2)
        else:
            # Outermost fallback: we are not in a match and the model could not
            # point at a button. Never sit still - try the keyboard confirms a
            # console player would use, alternating so a focused default button
            # eventually gets activated.
            if screen == "results":
                self.inputs.press("esc", 0.10)
                note = "results with no button: pressed Esc"
            elif screen in ("lobby", "island", "map_ready", "queue", "other"):
                key = "enter" if len(self.steps) % 2 == 0 else "space"
                self.inputs.press(key, 0.08)
                note = f"no button: pressed {key} to confirm the default action"
            time.sleep(1.5)
        return {"layer": "ui", "screen": screen, "action": action,
                "action_conf": round(action_conf, 3), "note": note}

    # ------------------------------------------------------- sensitivity
    def probe_sensitivity(self) -> None:
        before = self.capture.grab(self.rect)
        delta = int(240 * self.scale)
        self.turn(delta)
        time.sleep(0.4)
        after = self.capture.grab(self.rect)
        try:
            obs = self.client.ask_pair(before, after, SENSITIVITY_QUESTIONS,
                                       context="Calibration probe: how far did the view turn?")
        except (JevError, TransportError) as exc:
            print(f"    sensitivity probe failed: {exc}")
            return
        shift, conf = obs.choice("view_shift")
        factor = {"none": 1.8, "small": 1.35, "good": 1.0, "large": 0.6}.get(shift, 1.0)
        self.scale = clamp_scale(self.scale * factor)
        self.turn_cfg = replace(self.turn_cfg, px_per_screen=self.scale)
        # Persist immediately: the next launch (and the next match) starts from
        # this number even if this process is killed mid-session.
        saved = save_scale(self.scale, view_shift=shift, confidence=conf,
                           source="session_loop")
        print(f"    sensitivity: view={shift}({conf:.2f}) -> px_per_screen "
              f"{self.scale:.2f} (saved, {saved['probes']} probes)")
        self.steps.append({"layer": "sensitivity", "view_shift": shift,
                           "confidence": round(conf, 3), "scale": round(self.scale, 2)})

    # ------------------------------------------------------------------ run
    def run(self) -> int:
        out_dir = Path(self.args.out) if self.args.out else (
            ROOT / "logs" / "session" / datetime.now().strftime("%Y%m%d_%H%M%S"))
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"session -> {out_dir}")
        print(f"sensitivity: {self.scale:.2f} px/screen (fixed"
              f"{', calibrating' if self.args.calibrate else ''})")
        print(f"pipeline depth: {self.depth} "
              f"({'one decision per round trip' if self.depth == 1 else 'overlapping requests'})")
        print("click the game now; starting in 6 seconds "
              "(if it is still in the background I will try Alt+Tab)")
        time.sleep(6)
        try:
            start_where, _, _ = self.judge(self.capture.grab(self.rect))
            if start_where in ("other", "loading"):
                self.refocus()
        except (JevError, TransportError) as exc:
            print(f"startup focus check failed: {exc}")

        try:
            for cycle in range(1, self.args.cycles + 1):
                frame = self.capture.grab(self.rect)
                frame.save_png(out_dir / f"cycle_{cycle:03d}.png")
                if cloud.mean_luma(frame) < self.cfg.cloud.black_frame_min_luma:
                    print(f"[{cycle:03d}] black frame; waking")
                    self.inputs.move_relative(30, 10)
                    time.sleep(2.0)
                    continue
                try:
                    if self.where == "in_match":
                        record = self.pump_match(frame)
                        where = record.get("screen") or "in_match"
                        # The in-match question set answers "other" whenever the
                        # frame does not look like any listed state - a vehicle
                        # close-up, a half-covered screen, a wall. That is still
                        # the match: only death / results / menu end it.
                        if where in ("other", "loading"):
                            where = "in_match"
                        conf = float(record.get("screen_conf") or 0.0)
                    else:
                        self.inflight.clear()
                        # Precise state layer: one call that names the exact
                        # screen, including bus / skydive / glide, which a
                        # generic "loading" bucket used to swallow.
                        where, conf, job = self.judge(frame)
                        if where == "lobby":
                            self.leave_attempts = 0
                        if where == "bus":
                            self.bus_steps += 1
                            drop_now = job.noul("drop_now") or 0.0
                            # The model reads drop_now around 0.25-0.35 for most
                            # of the ride, so a 0.40 gate never fired and the bot
                            # rode to the end. Jump at 0.25, and force it after
                            # eight decisions so one low reading cannot trap it.
                            if drop_now >= 0.25 or self.bus_steps >= 8:
                                self.inputs.press("space", 0.08)
                                note = (f"jumped off the bus (drop_now {drop_now:.2f}, "
                                        f"step {self.bus_steps})")
                            else:
                                note = (f"waiting on the bus (drop_now {drop_now:.2f}, "
                                        f"step {self.bus_steps})")
                            record = {"layer": "drop", "drop_now": round(drop_now, 2),
                                      "note": note}
                        elif where in ("skydive", "glide"):
                            if not self.held:
                                self.inputs.key_down("w")
                                self.held = {"w"}
                            self.turn(0, 45)
                            record = {"layer": "drop", "note": f"{where}: W + look down"}
                        elif where in ("queue", "loading"):
                            record = {"layer": "wait", "note": where}
                            time.sleep(1.0)
                        elif where in ("eliminated", "results"):
                            record = self.step_leave(frame)
                        elif where == "other" and self.leave_attempts > 0:
                            self.leave_attempts -= 1
                            record = self.step_leave(frame)
                        else:
                            record = self.step_ui(frame)
                        if where != "bus":
                            self.bus_steps = 0
                except (JevError, TransportError) as exc:
                    print(f"[{cycle:03d}] error: {exc}")
                    time.sleep(1.5)
                    continue

                self.where = where
                print(f"[{cycle:03d}] route: {where} ({conf:.2f})")
                # Input-delivery check: holding movement keys while the picture
                # is frozen almost always means the keys are going to another
                # window, not to the game.
                sim = record.get("similarity")
                if self.held and sim is not None and sim >= 0.99:
                    self.no_move += 1
                else:
                    self.no_move = 0
                if self.no_move >= 3:
                    # Typing into whatever else is focused is worse than doing
                    # nothing: release everything, try to get the game back,
                    # and only then resume.
                    print("        input paused: keys are held but the frame is frozen.")
                    self.no_move = 0
                    if self.refocus():
                        self.inflight.clear()
                        continue
                    print("        click the game window to resume; nothing is being sent.")
                    self.release()
                    self.inflight.clear()
                    baseline = frame_signature(frame)
                    for _ in range(30):
                        time.sleep(1.0)
                        probe = self.capture.grab(self.rect)
                        if signature_similarity(baseline, frame_signature(probe)) < 0.98:
                            print("        screen changed again; resuming")
                            break
                    continue
                record.update({"cycle": cycle, "judge": where,
                               "judge_conf": round(conf, 3)})
                self.steps.append(record)
                print(f"        {record}")
                if self.args.cycles and cycle >= self.args.cycles:
                    break
        except KeyboardInterrupt:
            print("stopped")
        finally:
            self.release()
            self.pool.shutdown(wait=False, cancel_futures=True)
            for client in self.clients:
                client.close()
            self.capture.close()
            (out_dir / "session.json").write_text(
                json.dumps({"steps": self.steps, "scale": self.scale},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"session log: {out_dir / 'session.json'}")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cycles", type=int, default=200)
    p.add_argument("--act", action="store_true", help="send input (default: observe)")
    p.add_argument("--probe-every", type=int, default=10,
                   help="in-match steps between sensitivity probes (needs --calibrate)")
    p.add_argument("--calibrate", action="store_true",
                   help="re-enable the adaptive sensitivity probe (default: fixed scale)")
    p.add_argument("--depth", type=int, default=2,
                   help="gameplay requests kept in flight; 1 = wait for each answer")
    p.add_argument("--out", default="")
    p.add_argument("--scale", type=float, default=None,
                   help="override and persist px_per_screen (mouse px per screen width)")
    args = p.parse_args(argv)
    enable_dpi_awareness()
    cloud.keep_awake(True)
    return Session(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
