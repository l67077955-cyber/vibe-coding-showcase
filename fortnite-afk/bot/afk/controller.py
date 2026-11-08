"""The AFK state machine: lobby -> queue -> match (random movement) -> leave -> repeat."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .capture import Frame, ScreenCapture
from .config import APP_DIR, Config, config_summary
from .explore import describe, frame_signature, plan_explore, signature_similarity
from .geometry import Box, Rect, box_center_screen
from .jev import JevError, Observation
from .motion import CameraNoise, aim_px, jitter, plan_turn, turn_duration
from .win32 import InputController, key_is_down
from . import cloud

log = logging.getLogger(__name__)


class Pause(RuntimeError):
    """Transient condition: game not foreground, loading, etc."""


class Fatal(RuntimeError):
    """The script cannot continue safely without a human."""


class StopRequested(Exception):
    """Panic key, duration limit, or cycle limit reached."""


@dataclass
class RunSummary:
    reason: str
    cycles: int
    calls: int
    cost: float
    started_at: float
    ended_at: float


class AfkController:
    def __init__(
        self,
        cfg: Config,
        window: Any,
        capture: ScreenCapture,
        inputs: InputController,
        vision: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        panic: Callable[[], bool] | None = None,
        rng: random.Random | None = None,
        run_seconds: float | None = None,
    ) -> None:
        self.cfg = cfg
        self.window = window
        self.capture = capture
        self.inputs = inputs
        self.vision = vision
        self.clock = clock
        self.sleeper = sleeper
        self.panic = panic or (lambda: key_is_down(cfg.safety.panic_key))
        self.rng = rng or random.Random()
        self.run_seconds = run_seconds

        self.state = "lobby"
        self.state_entered = clock()
        self.hwnd: int | None = None
        self.last_frame: Frame | None = None
        self.started = clock()
        self.cycles = 0
        self._stop = False
        self._state_actions = 0
        self._consecutive_failures = 0
        self._mode_warnings = 0

        self.match_started = 0.0
        self.match_deadline = 0.0
        self.next_check = 0.0
        self.queue_started = 0.0
        self.leave_deadline = 0.0
        self.require_lobby_after = 0.0  # don't click PLAY before this time

        self._next_move = 0.0
        self._next_jump = 0.0
        self._next_look = 0.0
        self._next_crouch = 0.0
        self._last_move_keys: list[str] = []
        self._black_frames = 0
        self._next_explore = 0.0
        self._last_signature: tuple[int, ...] = ()
        self._stuck = 0
        self._last_move = ""
        self._chest_ready_at = 0.0
        self._interact_sig: tuple[int, ...] | None = None
        self._noise = CameraNoise(self.rng, self.cfg.turn)
        # Live aiming gain. Not a calibration constant: it is nudged by what the
        # last turn actually did to Jev's target box, so an unknown or changing
        # mouse sensitivity only changes the convergence speed.
        self._aim_gain = self.cfg.turn.gain
        self._last_aim: tuple[float, int] | None = None
        self._leaving_intent = False
        self._last_cloud_check = 0.0
        self._held_move: set[str] = set()
        self._held_started = 0.0
        if self.cfg.cloud.keep_awake:
            cloud.keep_awake(True)
            log.info("keep-awake enabled (display + system required)")

    # ------------------------------------------------------------------ run
    def run(self) -> RunSummary:
        log.info("Starting: %s", config_summary(self.cfg))
        reason = "stopped"
        try:
            self._wait_for_game()
            while True:
                self._check_stop()
                try:
                    next_state = self._step()
                    self._consecutive_failures = 0
                    self._go(next_state)
                except StopRequested:
                    raise
                except Pause as exc:
                    log.warning("paused: %s", exc)
                    self._sleep(2.0)
                except JevError as exc:
                    self._handle_error(exc)
                except Exception as exc:  # keep the farm alive through odd UI states
                    self._handle_error(exc)
                self._sleep(0.1)
        except StopRequested as exc:
            reason = str(exc) or "stop requested"
            log.info("Stop: %s", reason)
        except Fatal as exc:
            reason = f"fatal: {exc}"
            log.error("Fatal: %s", exc)
            raise
        finally:
            self.inputs.release_all()
            self._held_move.clear()
            self.capture.close()
            cloud.keep_awake(False)
            try:
                self.vision.close()
            except Exception:
                pass
            log.info(
                "Finished: %d match cycle(s), %d Jev call(s), $%.4f, %.1f min",
                self.cycles, getattr(self.vision, "calls", 0),
                getattr(self.vision, "total_cost", 0.0),
                (self.clock() - self.started) / 60.0,
            )
        return RunSummary(
            reason=reason,
            cycles=self.cycles,
            calls=getattr(self.vision, "calls", 0),
            cost=getattr(self.vision, "total_cost", 0.0),
            started_at=self.started,
            ended_at=self.clock(),
        )

    def _step(self) -> str:
        if self.state == "lobby":
            return self._step_lobby()
        if self.state == "queue":
            return self._step_queue()
        if self.state == "match":
            return self._step_match()
        if self.state == "menu":
            return self._step_menu()
        if self.state == "leaving":
            return self._step_leaving()
        if self.state == "results":
            return self._step_results()
        raise Fatal(f"unknown state {self.state}")

    def _go(self, state: str) -> None:
        if state != self.state:
            log.info("STATE %s -> %s", self.state, state)
            self.state = state
            self.state_entered = self.clock()
            self._state_actions = 0
            if state == "lobby":
                self._leaving_intent = False

    def _check_stop(self) -> None:
        if self._stop:
            raise StopRequested("already stopped")
        if self.panic():
            self._stop = True
            raise StopRequested(f"panic key {self.cfg.safety.panic_key.upper()} pressed")
        if self.run_seconds is not None and self.clock() - self.started >= self.run_seconds:
            raise StopRequested("run duration reached")
        if (
            self.cfg.safety.max_cycles
            and self.cycles >= self.cfg.safety.max_cycles
            and self.state == "lobby"
        ):
            raise StopRequested(f"completed {self.cycles} cycle(s)")

    def _handle_error(self, exc: Exception) -> None:
        self._release_movement()
        self._consecutive_failures += 1
        log.error("%s: %s (%d/%d)", type(exc).__name__, exc,
                  self._consecutive_failures, self.cfg.safety.max_consecutive_failures)
        if isinstance(exc, JevError) and exc.status in (401, 402):
            raise Fatal(str(exc))
        if self._consecutive_failures >= self.cfg.safety.max_consecutive_failures:
            raise Fatal(f"too many consecutive failures: {exc}")
        self._sleep(min(30.0, 3.0 * self._consecutive_failures))

    def _sleep(self, seconds: float) -> None:
        """Sleep in slices so F12 stays responsive during long waits."""
        if seconds <= 0:
            return
        end = self.clock() + seconds
        while self.clock() < end:
            if self.panic():
                self._stop = True
                raise StopRequested(f"panic key {self.cfg.safety.panic_key.upper()} pressed")
            self.sleeper(min(0.25, max(0.0, end - self.clock())))

    # --------------------------------------------------------------- window
    def _wait_for_game(self) -> None:
        deadline = self.clock() + 60.0
        while True:
            hwnd = self.window.find()
            if hwnd:
                self.hwnd = hwnd
                if getattr(self.window, "screen_only", False):
                    rect = self.window.client_rect()
                    log.info("screen-only mode: capturing %dx%d at (%d,%d); "
                             "no window handle is used", rect.width, rect.height,
                             rect.left, rect.top)
                else:
                    log.info("Fortnite window: hwnd=0x%X", hwnd)
                if self.cfg.safety.focus_on_start:
                    self.window.focus(hwnd)
                    self._sleep(1.0)
                if self.cfg.safety.require_foreground and not self.window.is_foreground(hwnd):
                    log.warning("Click the Fortnite window to bring it to the foreground; waiting...")
                return
            if self.clock() >= deadline:
                raise Fatal(
                    "Fortnite window not found. Start the game, or set window_class/window_title "
                    "in config.json."
                )
            log.info("Waiting for the Fortnite window...")
            self._sleep(3.0)

    def _ensure_foreground(self) -> None:
        if self.cfg.cloud.pause_when_disconnected:
            now = self.clock()
            if now - self._last_cloud_check >= 1.0:
                self._last_cloud_check = now
                state, name = cloud.connect_state()
                if state in (3, 4, 5, 7, 8):
                    raise Pause(f"cloud session is {name}; reconnect the cloud desktop")
                if not cloud.input_desktop_available():
                    raise Pause("input desktop is unavailable (workstation locked)")
        hwnd = self.hwnd or self.window.find()
        if not hwnd:
            self.hwnd = None
            raise Pause("Fortnite window not found")
        self.hwnd = hwnd
        if self.window.is_minimized(hwnd):
            raise Pause("Fortnite is minimised")
        if self.cfg.safety.require_foreground and not self.window.is_foreground(hwnd):
            raise Pause("Fortnite is not the foreground window")

    def _client_rect(self) -> Rect:
        assert self.hwnd is not None
        return self.window.client_rect(self.hwnd)

    def _observe(self, profile: str) -> Observation:
        self._ensure_foreground()
        frame = self.capture.grab(self._client_rect())
        self.last_frame = frame
        luma = cloud.mean_luma(frame)
        if luma < self.cfg.cloud.black_frame_min_luma:
            self._black_frames += 1
            log.warning("black/near-black frame: luma=%.1f (%d/%d)", luma,
                        self._black_frames, self.cfg.cloud.max_consecutive_black_frames)
            if self.cfg.logging.save_frames in ("all", "failures"):
                self._save_frame(frame, f"black_{self._black_frames}")
            if self._black_frames >= self.cfg.cloud.max_consecutive_black_frames:
                raise Fatal(
                    "screen capture is black. The cloud display is asleep, the remote session "
                    "lost its virtual display, or Fortnite is in exclusive fullscreen. "
                    "Reconnect the cloud desktop, set Fortnite to Windowed Fullscreen, and restart."
                )
            raise Pause("black frame from the cloud display")
        self._black_frames = 0
        if self.cfg.logging.save_frames == "all":
            self._save_frame(frame, profile)
        obs = self.vision.observe(profile, frame)
        if obs.screen_confidence < self.cfg.confidence.screen:
            log.warning("low screen confidence: %s %.2f (threshold %.2f)",
                        obs.screen, obs.screen_confidence, self.cfg.confidence.screen)
        return obs

    def _save_frame(self, frame: Frame, tag: str) -> None:
        try:
            directory = Path(self.cfg.logging.dir)
            if not directory.is_absolute():
                directory = APP_DIR / directory
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            path = frame.save_png(directory / f"frame_{stamp}_{tag}.png")
            log.info("saved frame %s", path)
        except Exception as exc:
            log.warning("could not save frame: %s", exc)

    # --------------------------------------------------------------- boxes
    def _box(self, obs: Observation, name: str) -> Box | None:
        return obs.usable_box(
            name,
            min_confidence=self.cfg.confidence.box,
            min_presence=self.cfg.confidence.presence,
            allow_null=self.cfg.confidence.allow_null,
            null_value=self.cfg.confidence.null_value,
            max_side=self.cfg.confidence.max_box_side,
        )

    def _click_box(self, obs: Observation, name: str, label: str) -> bool:
        if self.last_frame is None:
            return False
        box = self._box(obs, name)
        conf = 0.0
        if box is None:
            # No coordinates, no colour heuristics, no fallback area: if the
            # model cannot point at the button, nothing is clicked.
            return False
        _, conf = obs.raw_box(name)
        x, y = box_center_screen(box, self.last_frame.rect)
        x += self.rng.randint(-2, 2)
        y += self.rng.randint(-2, 2)
        x = max(self.last_frame.rect.left, min(x, self.last_frame.rect.right - 1))
        y = max(self.last_frame.rect.top, min(y, self.last_frame.rect.bottom - 1))
        log.info("CLICK %-16s at (%d,%d) conf=%.2f", label, x, y, conf)
        self.inputs.click(x, y)
        self._state_actions += 1
        self._mode_warnings = 0
        return True

    def _fail(self, reason: str) -> None:
        self._state_actions += 1
        log.warning("%s (action %d/%d)", reason, self._state_actions,
                    self.cfg.timing.max_actions_per_state)
        if self._state_actions >= self.cfg.timing.max_actions_per_state:
            raise Fatal(f"giving up in state '{self.state}': {reason}")
        self._sleep(self.cfg.timing.action_settle_s)

    # --------------------------------------------------------------- lobby
    def _step_lobby(self) -> str:
        obs = self._observe("lobby")
        log.info("lobby observation: screen=%s conf=%.2f", obs.screen, obs.screen_confidence)

        if obs.screen == "matchmaking":
            self.queue_started = self.clock()
            return "queue"
        if obs.screen in ("in_match", "eliminated"):
            self._enter_match()
            return "match"
        if obs.screen == "esc_menu":
            return "menu"
        if obs.screen == "results":
            return "results"
        if obs.screen != "lobby":
            log.info("not in a known lobby screen (%s); waiting", obs.screen)
            self._sleep(self.cfg.timing.lobby_poll_s)
            return "lobby"

        if self.clock() < self.require_lobby_after:
            self._sleep(self.cfg.timing.lobby_cooldown_s)
            return "lobby"

        if not self._ensure_mode(obs):
            return "lobby"

        if not self._click_box(obs, "play_button", "PLAY"):
            self._fail("PLAY button not found/confident enough")
            return "lobby"

        self.queue_started = self.clock()
        self._sleep(self.cfg.timing.action_settle_s)
        return "queue"

    def _ensure_mode(self, obs: Observation) -> bool:
        setup = self.cfg.mode.setup
        if setup == "off":
            return True

        problems: list[str] = []
        mode, mode_conf = obs.choice("selected_mode")
        if self.cfg.mode.zero_build and (mode != "zero_build" or mode_conf < 0.45):
            problems.append(f"mode={mode} ({mode_conf:.2f})")
        squad, squad_conf = obs.choice("squad_size")
        if self.cfg.mode.squads and (squad != "squads" or squad_conf < 0.45):
            problems.append(f"squad={squad} ({squad_conf:.2f})")
        fill, fill_conf = obs.choice("fill_state")
        if self.cfg.mode.fill and (fill != "on" or fill_conf < 0.45):
            problems.append(f"fill={fill} ({fill_conf:.2f})")

        if not problems:
            self._mode_warnings = 0
            return True

        detail = ", ".join(problems)
        if setup == "verify":
            self._mode_warnings += 1
            log.warning(
                "MODE CHECK FAILED: %s. Set ZERO BUILD + SQUADS + FILL manually in the lobby, "
                "or set mode.setup to 'auto' after calibrating. (%d/8)",
                detail, self._mode_warnings,
            )
            if self._mode_warnings >= 8:
                raise Fatal(
                    "the selected mode is not ZERO BUILD + SQUADS + FILL; fix it manually "
                    "or use mode.setup='auto'"
                )
            self._sleep(3.0)
            return False

        # auto: click one control per observation, then re-check from a fresh frame
        self._state_actions += 1
        if self._state_actions > self.cfg.timing.max_actions_per_state:
            raise Fatal(f"could not set the mode automatically: {detail}")
        log.info("auto mode setup: %s", detail)
        if mode != "zero_build" and self._click_box(obs, "zero_build_tile", "ZERO BUILD"):
            self._sleep(self.cfg.timing.action_settle_s)
            return False
        if squad != "squads":
            if self._click_box(obs, "squads_option", "SQUADS option"):
                self._sleep(self.cfg.timing.action_settle_s)
                return False
            if self._click_box(obs, "squad_control", "squad selector"):
                self._sleep(self.cfg.timing.action_settle_s)
                return False
        if fill != "on" and self._click_box(obs, "fill_toggle", "FILL toggle"):
            self._sleep(self.cfg.timing.action_settle_s)
            return False
        self._fail(f"mode controls not found: {detail}")
        return False

    # --------------------------------------------------------------- queue
    def _step_queue(self) -> str:
        elapsed = self.clock() - self.queue_started
        if elapsed > self.cfg.timing.queue_timeout_s:
            obs = self._observe("queue")
            if self._click_box(obs, "cancel_button", "CANCEL"):
                self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
                return "lobby"
            raise Fatal("matchmaking timed out and no CANCEL button was found")

        obs = self._observe("queue")
        log.info("queue observation: screen=%s conf=%.2f (%.0fs)",
                 obs.screen, obs.screen_confidence, elapsed)
        if obs.screen in ("in_match", "eliminated"):
            self._enter_match()
            return "match"
        if obs.screen == "lobby":
            if elapsed < 10.0:
                self._sleep(2.0)
                return "queue"
            log.warning("returned to lobby without a match; requeueing")
            self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
            return "lobby"
        if obs.screen == "esc_menu":
            return "menu"
        if obs.screen == "results":
            return "results"

        # matchmaking / loading / unknown: keep waiting
        self._sleep(self.cfg.timing.queue_poll_s)
        return "queue"

    # --------------------------------------------------------------- match
    def _enter_match(self) -> None:
        self.match_started = self.clock()
        minutes = self.rng.uniform(*self.cfg.timing.match_minutes)
        self.match_deadline = self.match_started + minutes * 60.0
        self.next_check = self.match_started + max(20.0, self.cfg.timing.match_check_s)
        self.cycles += 1
        self._schedule_afk(self.match_started, first=True)
        self._next_explore = self.match_started + 1.0
        self._last_signature = ()
        self._stuck = 0
        self._last_move = ""
        self._chest_ready_at = 0.0
        log.info("MATCH %d started; leaving in %.1f min", self.cycles, minutes)

    def _schedule_afk(self, now: float, first: bool = False) -> None:
        afk = self.cfg.afk
        self._next_move = now + self.rng.uniform(4.0, 12.0)
        self._next_jump = now + self.rng.uniform(45.0, min(120.0, afk.jump_every_s[1]))
        self._next_look = now + self.rng.uniform(8.0, min(40.0, afk.look_every_s[1]))
        self._next_crouch = now + self.rng.uniform(60.0, min(180.0, afk.crouch_every_s[1]))

    def _step_match(self) -> str:
        now = self.clock()
        self._ensure_foreground()

        if now >= self.match_deadline:
            log.info("match deadline reached; leaving")
            return self._begin_leave()

        if self.cfg.explore.enabled:
            if now >= self._next_explore:
                obs = self._observe(self.cfg.explore.question_profile)
                log.info("explore observation: screen=%s conf=%.2f",
                         obs.screen, obs.screen_confidence)
                if obs.screen == "lobby":
                    self._release_movement()
                    self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
                    return "lobby"
                if obs.screen == "results":
                    self._release_movement()
                    return "results"
                if obs.screen == "esc_menu":
                    if self._leaving_intent:
                        self._release_movement()
                        return "menu"
                    log.info("unexpected pause menu during explore; resuming")
                    self._release_movement()
                    self.inputs.press("esc", 0.10)
                    self._sleep(0.8)
                    return "match"
                eliminated = obs.noul("eliminated")
                if obs.screen == "eliminated" or (eliminated is not None and eliminated >= 0.8):
                    log.info("player eliminated (noul=%s); leaving", eliminated)
                    return self._begin_leave()
                if obs.screen == "in_match":
                    self._explore_step(obs, now)
                else:
                    log.info("explore paused on screen=%s", obs.screen)
                self._next_explore = now + self.rng.uniform(*self.cfg.explore.interval_s)
            else:
                self._sleep(0.10)
            return "match"

        self._afk_tick(now)

        if now >= self.next_check:
            obs = self._observe("ingame")
            log.info("in-match check: screen=%s conf=%.2f", obs.screen, obs.screen_confidence)
            if obs.screen == "lobby":
                log.info("already back in the lobby")
                self._release_movement()
                self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
                return "lobby"
            if obs.screen == "results":
                self._release_movement()
                return "results"
            if obs.screen == "esc_menu":
                if self._leaving_intent:
                    self._release_movement()
                    return "menu"
                log.info("unexpected pause menu in match; resuming")
                self._release_movement()
                self.inputs.press("esc", 0.10)
                self._sleep(0.8)
                return "match"
            eliminated = obs.noul("eliminated")
            if obs.screen == "eliminated" or (eliminated is not None and eliminated >= 0.8):
                log.info("player eliminated (noul=%s); leaving", eliminated)
                return self._begin_leave()
            self.next_check = now + self.cfg.timing.match_check_s

        return "match"

    def _explore_step(self, obs: Observation, now: float) -> None:
        if self._held_move and now - self._held_started > self.cfg.explore.max_continuous_s:
            log.info("continuous movement timeout; releasing keys for a fresh decision")
            self._release_movement()

        signature = frame_signature(self.last_frame) if self.last_frame else ()
        if self._last_signature:
            similarity = signature_similarity(self._last_signature, signature)
            if (similarity >= self.cfg.explore.stuck_similarity
                    and self._last_move not in ("stop", "interact", "")):
                self._stuck += 1
            else:
                self._stuck = 0

        if self._stuck >= self.cfg.explore.stuck_limit:
            log.warning("stuck against geometry (similarity high); backing out and jumping")
            self._release_movement()
            self.inputs.hold(["s"], 0.55)
            self.inputs.press("space", 0.08)
            self.inputs.hold(["d"], 0.35)
            self._stuck = 0
            self._last_signature = ()
            self._last_move = "stuck-escape"
            return

        plan = plan_explore(obs, self.cfg, self.rng,
                            chest_ready=now >= self._chest_ready_at)
        self._adapt_aim(plan)
        # An interact that changed nothing on screen means we were out of range
        # (or facing the wrong thing). Trusting the model again would press E
        # forever, so override the next plan with "walk closer".
        if self._interact_sig is not None:
            change = signature_similarity(self._interact_sig, signature)
            self._interact_sig = None
            if change >= 0.995 and plan.action in ("interact", "attack", "aim"):
                log.info("previous interact changed nothing (similarity %.3f); "
                         "walking closer instead", change)
                plan = replace(plan, keys=["w"], action="move_forward",
                               interact=False, jump=False, hold_s=0.6,
                               hold_label="medium", continuous=True, aim_norm=0.0,
                               reason="interact had no effect -> advance")
        log.info("EXPLORE %s | %s", describe(plan), plan.reason)
        self._execute_plan(plan, now)
        if plan.interact:
            self._interact_sig = signature
        self._last_move = plan.action or plan.move
        self._last_signature = signature

    def _adapt_aim(self, plan) -> None:
        """React to whether the last turn actually helped.

        No absolute sensitivity is assumed. If the target moved closer to the
        centre the gain creeps up; if it did not, the gain is cut. The next
        decision re-reads the target, so a wrong gain costs one frame of
        convergence, never a lost target.
        """
        if self._last_aim is None:
            return
        before, turn = self._last_aim
        self._last_aim = None
        if not plan.aim_norm or abs(turn) < 30 or abs(before) < 0.05:
            return
        err_before, err_after = abs(before), abs(plan.aim_norm)
        old = self._aim_gain
        if err_after < err_before * 0.80:
            self._aim_gain = min(0.90, self._aim_gain * 1.10)
        elif err_after > err_before * 1.02:
            # Overshot, or the game needs much less mouse than we gave it.
            self._aim_gain = max(0.12, self._aim_gain * 0.55)
        if abs(self._aim_gain - old) > 1e-3:
            log.info("aim gain %.2f -> %.2f (target %.3f -> %.3f)",
                     old, self._aim_gain, err_before, err_after)

    def _turn_by(self, dx_px: int) -> None:
        """Turn in many small eased mouse steps instead of one snap.

        A 300 px jump in a single SendInput lands as an instant camera whip;
        the same 300 px spread over ~24 ticks eases in and out like a hand
        moving a mouse. `smooth_turn=false` restores the old one-shot move.
        """
        if not dx_px:
            return
        if not self.cfg.explore.smooth_turn:
            nx, ny = self._noise.step(0.05)
            self.inputs.move_relative(dx_px + nx, ny)
            return
        steps = plan_turn(dx_px, self.cfg.turn)
        for delta in steps:
            nx, ny = self._noise.step(self.cfg.turn.tick_s)
            self.inputs.move_relative(delta + nx, ny)
            self._sleep(jitter(self.cfg.turn.tick_s, self.rng, 0.20))
        log.debug("turn %+d px over %d ticks (%.2fs)", dx_px, len(steps),
                  turn_duration(steps, self.cfg.turn))

    def _execute_plan(self, plan, now: float) -> None:
        """Turn one Jev plan into inputs, honouring operation/hold/repeat/continuous."""
        aim_dx = 0
        if plan.aim_norm and self.last_frame is not None:
            aim_dx = aim_px(0.5 + plan.aim_norm, self.last_frame.width,
                            self.cfg.turn, gain=self._aim_gain)
            self._last_aim = (plan.aim_norm, aim_dx)

        # Real players rarely stand still to turn: the movement keys go down
        # first, then the camera swings while the character is already walking.
        # Discontinuous actions (interact / jump / click / discrete taps) keep
        # the old order, because those need a stable base.
        walking = bool(plan.keys and plan.continuous and not plan.interact
                       and not plan.jump and not plan.mouse)
        if walking:
            self._set_movement(plan.keys, now)
        if aim_dx:
            self._turn_by(aim_dx)

        if plan.mouse:
            self._release_movement()
            if self.last_frame is None:
                return
            x = self.last_frame.rect.left + self.last_frame.rect.width // 2
            y = self.last_frame.rect.top + self.last_frame.rect.height // 2
            for _ in range(plan.repeat):
                if plan.hold_s <= 0.2:
                    self.inputs.click(x, y, button=plan.mouse)
                else:
                    self.inputs.mouse_down(plan.mouse)
                    try:
                        self._sleep(jitter(plan.hold_s, self.rng, 0.10))
                    finally:
                        self.inputs.mouse_up(plan.mouse)
                self._sleep(0.08)
            return

        if plan.interact:
            self._release_movement()
            for _ in range(plan.repeat):
                self.inputs.hold(plan.keys, jitter(plan.hold_s, self.rng, 0.08))
                self._sleep(0.10)
            self._chest_ready_at = now + self.cfg.explore.chest_cooldown_s
            return

        if plan.jump:
            self._release_movement()
            for _ in range(plan.repeat):
                if plan.keys:
                    self.inputs.key_down("w")
                    try:
                        self.inputs.press("space", 0.08)
                        self._sleep(0.18)
                    finally:
                        self.inputs.key_up("w")
                else:
                    self.inputs.press("space", 0.08)
                self._sleep(0.12)
            if plan.look_dx:
                self._turn_by(plan.look_dx)
            return

        if plan.keys:
            if plan.continuous:
                self._set_movement(plan.keys, now)
            else:
                self._release_movement()
                for _ in range(plan.repeat):
                    self.inputs.hold(plan.keys, jitter(plan.hold_s, self.rng, 0.10))
                    self._sleep(jitter(0.08, self.rng, 0.30))
        else:
            self._release_movement()

        if plan.look_dx:
            self._turn_by(plan.look_dx)
        elif not plan.aim_norm:
            # Idle gaze: even when the plan is "hold W", the hand keeps drifting.
            nx, ny = self._noise.step(0.10)
            if nx or ny:
                self.inputs.move_relative(nx, ny)

    def _set_movement(self, keys: list[str], now: float) -> None:
        new = {key.lower() for key in keys}
        old = set(self._held_move)
        for key in old - new:
            self.inputs.key_up(key)
        for key in new - old:
            self.inputs.key_down(key)
        self._held_move = new
        self._held_started = now

    def _release_movement(self) -> None:
        for key in sorted(self._held_move):
            try:
                self.inputs.key_up(key)
            except Exception:
                pass
        self._held_move.clear()

    def _afk_tick(self, now: float) -> None:
        afk = self.cfg.afk
        if now >= self._next_move:
            keys = self._pick_move_keys()
            hold = self.rng.uniform(*afk.move_hold_s)
            log.info("AFK move %s for %.2fs", "+".join(keys), hold)
            self.inputs.hold(keys, hold)
            self._last_move_keys = keys
            if self.rng.random() < afk.jump_with_move:
                self.inputs.press("space", 0.08)
            self._next_move = now + self.rng.uniform(*afk.move_every_s)
        if now >= self._next_jump:
            log.info("AFK jump")
            self.inputs.press("space", 0.08)
            self._next_jump = now + self.rng.uniform(*afk.jump_every_s)
        if now >= self._next_look:
            dx = self.rng.randint(-320, 320)
            dy = self.rng.randint(-110, 110)
            log.info("AFK look (%d, %d)", dx, dy)
            self.inputs.move_relative(dx, dy)
            self._next_look = now + self.rng.uniform(*afk.look_every_s)
        if now >= self._next_crouch:
            log.info("AFK crouch")
            self.inputs.hold(["ctrl"], 0.35)
            self._next_crouch = now + self.rng.uniform(*afk.crouch_every_s)

    def _pick_move_keys(self) -> list[str]:
        """Random short move, biased against repeating the previous direction."""
        pairs = [["w"], ["a"], ["s"], ["d"], ["w", "a"], ["w", "d"], ["s", "a"], ["s", "d"]]
        opposite = {"w": "s", "s": "w", "a": "d", "d": "a"}
        if self._last_move_keys and self.rng.random() < 0.40:
            return [opposite.get(k, k) for k in self._last_move_keys]
        return list(self.rng.choice(pairs))

    def _begin_leave(self) -> str:
        self.leave_deadline = self.clock() + self.cfg.timing.leave_timeout_s
        self._leaving_intent = True
        self._release_movement()
        log.info("opening pause menu (Esc)")
        self.inputs.press("esc", 0.10)
        self._sleep(self.cfg.timing.action_settle_s)
        return "menu"

    def _step_menu(self) -> str:
        if not self._leaving_intent:
            log.info("pause menu without leave intent; pressing Esc to go back")
            self.inputs.press("esc", 0.10)
            self._sleep(self.cfg.timing.action_settle_s)
            return "lobby"
        obs = self._observe("menu")
        log.info("menu observation: screen=%s conf=%.2f", obs.screen, obs.screen_confidence)
        if obs.screen == "lobby":
            self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
            return "lobby"
        if obs.screen == "results":
            return "results"
        if obs.screen == "in_match":
            log.info("pause menu is not open; pressing Esc again")
            self.inputs.press("esc", 0.10)
            self._sleep(self.cfg.timing.action_settle_s)
            return "menu"

        if self._click_box(obs, "confirm_button", "CONFIRM LEAVE"):
            return "leaving"
        if self._click_box(obs, "leave_button", "LEAVE MATCH"):
            self._sleep(self.cfg.timing.action_settle_s)
            # confirmation may already be visible on the next frame
            return "leaving"
        if self._box(obs, "return_lobby_button") is not None:
            if self._click_box(obs, "return_lobby_button", "RETURN TO LOBBY"):
                return "leaving"
        self._fail("leave/confirm button not found in the pause menu")
        return "menu"

    def _step_leaving(self) -> str:
        if self.clock() > self.leave_deadline:
            raise Fatal("timed out waiting for the lobby after leaving the match")
        obs = self._observe("menu")
        log.info("leaving observation: screen=%s conf=%.2f", obs.screen, obs.screen_confidence)
        if obs.screen == "lobby":
            self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
            log.info("back in lobby; next cycle in %.0fs", self.cfg.timing.lobby_cooldown_s)
            return "lobby"
        if obs.screen == "results":
            return "results"
        if obs.screen == "esc_menu":
            if self._click_box(obs, "confirm_button", "CONFIRM LEAVE"):
                return "leaving"
            if self._click_box(obs, "leave_button", "LEAVE MATCH"):
                return "leaving"
            self._fail("pause menu still open after leave; no button found")
            return "menu"
        if self._click_box(obs, "confirm_button", "CONFIRM LEAVE"):
            return "leaving"
        self._sleep(2.5)
        return "leaving"

    def _step_results(self) -> str:
        obs = self._observe("results")
        log.info("results observation: screen=%s conf=%.2f", obs.screen, obs.screen_confidence)
        if obs.screen == "lobby":
            self.require_lobby_after = self.clock() + self.cfg.timing.lobby_cooldown_s
            return "lobby"
        if self._click_box(obs, "return_lobby_button", "RETURN TO LOBBY"):
            self._sleep(self.cfg.timing.action_settle_s)
            return "leaving"
        if self._click_box(obs, "play_again_button", "PLAY AGAIN"):
            self.queue_started = self.clock()
            self._sleep(self.cfg.timing.action_settle_s)
            return "queue"
        self._fail("RETURN TO LOBBY / PLAY AGAIN button not found on the results screen")
        return "results"
