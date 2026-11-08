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
from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.explore import (describe, frame_signature, plan_explore,  # noqa: E402
                         signature_similarity)
from afk.geometry import Rect, box_center_screen  # noqa: E402
from afk.jev import JevClient, JevError, TransportError  # noqa: E402
from afk.motion import CameraNoise, aim_px, aim_py, plan_turn  # noqa: E402
from afk.screens import questions_for  # noqa: E402
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
        self.client = JevClient(self.cfg)
        self.inputs = InputController(dry_run=not args.act, key_mode=self.cfg.key_mode)
        self.noise = CameraNoise(random.Random(), self.cfg.turn)
        self.aim_gain = self.cfg.turn.gain
        self.scale = float(self.cfg.turn.px_per_screen)
        self.held: set[str] = set()
        self.steps: list[dict] = []
        self.in_match_steps = 0
        self.last_sig: tuple[int, ...] = ()
        self.where = "lobby"
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.prev = None
        self.no_move = 0
        self.last_sim = None

    # ---------------------------------------------------------------- input
    def release(self) -> None:
        for key in list(self.held):
            self.inputs.key_up(key)
        self.held.clear()

    def turn(self, dx: int, dy: int = 0) -> None:
        sx = plan_turn(dx, self.cfg.turn) if dx else []
        sy = plan_turn(dy, self.cfg.turn) if dy else []
        for i in range(max(len(sx), len(sy))):
            nx, ny = self.noise.step(self.cfg.turn.tick_s)
            self.inputs.move_relative((sx[i] if i < len(sx) else 0) + nx,
                                      (sy[i] if i < len(sy) else 0) + ny)
            time.sleep(self.cfg.turn.tick_s)

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
    def ask_match(self, frame):
        """Fire the gameplay question for `frame` (can run on a worker thread)."""
        self.in_match_steps += 1
        return self.client.ask(frame, questions_for(self.cfg.explore.question_profile))

    def plan_from(self, obs, frame):
        plan = plan_explore(obs, self.cfg, random.Random(), chest_ready=True)
        _, conf = obs.choice("action")
        return plan, conf

    def execute_plan(self, plan, frame) -> dict:
        """Apply a plan. Runs while the next model call is already in flight."""
        sim = (round(signature_similarity(self.last_sig, frame_signature(frame)), 4)
               if self.last_sig else None)
        self.last_sig = frame_signature(frame)
        self.last_sim = sim

        if plan.aim_norm or plan.aim_norm_y:
            dx = aim_px(0.5 + plan.aim_norm, frame.width, self.cfg.turn,
                        gain=self.aim_gain) if plan.aim_norm else 0
            dy = aim_py(0.5 + plan.aim_norm_y, frame.height, self.cfg.turn,
                        gain=self.aim_gain) if plan.aim_norm_y else 0
            self.turn(dx, dy)
        if plan.interact:
            self.release()
            self.inputs.press(self.cfg.explore.interact_key, 0.12)
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

    # ------------------------------------------------------------ out match
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
        box = obs.usable_box("target_button", min_confidence=0.25,
                             min_presence=0.40, allow_null=True,
                             null_value=0.5, max_side=0.95)
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
        self.scale = max(0.25, min(8.0, self.scale * factor))
        print(f"    sensitivity: view={shift}({conf:.2f}) -> px_per_screen {self.scale:.2f}")
        self.steps.append({"layer": "sensitivity", "view_shift": shift,
                           "confidence": round(conf, 3), "scale": round(self.scale, 2)})

    # ------------------------------------------------------------------ run
    def run(self) -> int:
        out_dir = Path(self.args.out) if self.args.out else (
            ROOT / "logs" / "session" / datetime.now().strftime("%Y%m%d_%H%M%S"))
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"session -> {out_dir}")
        print("click the game now; starting in 6 seconds")
        time.sleep(6)

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
                    obs = None
                    if self.where == "in_match":
                        # Pipeline: send the next question now, then spend the
                        # wait executing the previous plan. The character keeps
                        # moving while the model is thinking instead of after.
                        future = self.pool.submit(self.ask_match, frame)
                        if self.prev is not None:
                            prev_plan, prev_conf, prev_frame = self.prev
                            self.execute_plan(prev_plan, prev_frame)
                        obs = future.result()
                        plan, conf = self.plan_from(obs, frame)
                        self.prev = (plan, conf, frame)
                        where = obs.screen
                        record = {"layer": "match", "plan": describe(plan),
                                  "action_conf": round(conf, 3),
                                  "keys": sorted(self.held),
                                  "merged": plan.merged, "reason": plan.reason}
                        if self.in_match_steps % self.args.probe_every == 0:
                            self.probe_sensitivity()
                    else:
                        # Precise state layer: one call that names the exact
                        # screen, including bus / skydive / glide, which a
                        # generic "loading" bucket used to swallow.
                        where, conf, job = self.judge(frame)
                        if where == "bus":
                            drop_now = job.noul("drop_now") or 0.0
                            if drop_now >= 0.40:
                                self.inputs.press("space", 0.08)
                                note = f"jumped off the bus (drop_now {drop_now:.2f})"
                            else:
                                note = f"waiting on the bus (drop_now {drop_now:.2f})"
                            record = {"layer": "drop", "note": note}
                        elif where in ("skydive", "glide"):
                            if not self.held:
                                self.inputs.key_down("w")
                                self.held = {"w"}
                            self.turn(0, 45)
                            record = {"layer": "drop", "note": f"{where}: W + look down"}
                        elif where in ("queue", "loading"):
                            record = {"layer": "wait", "note": where}
                            time.sleep(1.0)
                        else:
                            record = self.step_ui(frame)
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
                    print("        WARNING: keys are held but the frame is not changing.")
                    print("        WARNING: the game is probably not the foreground window;")
                    print("        WARNING: click it once, then leave the keyboard alone.")
                    self.no_move = 0
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
            self.client.close()
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
                   help="in-match steps between sensitivity probes")
    p.add_argument("--out", default="")
    args = p.parse_args(argv)
    enable_dpi_awareness()
    cloud.keep_awake(True)
    return Session(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
