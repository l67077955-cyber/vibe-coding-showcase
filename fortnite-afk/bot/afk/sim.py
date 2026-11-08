"""Offline simulation used by `demo` and the unit tests.

A tiny fake Fortnite: a lobby with buttons, a queue that resolves after a few
seconds, a match where Esc opens the pause menu, and a leave confirmation.
No game, no API, no screenshots — it exercises the exact controller code path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capture import Frame
from .geometry import Box, Rect
from .jev import Observation

W, H = 1280, 720

BOXES = {
    "play": Box(0.78, 0.77, 0.96, 0.95),
    "leave": Box(0.35, 0.38, 0.65, 0.47),
    "confirm": Box(0.52, 0.55, 0.68, 0.64),
    "return": Box(0.60, 0.75, 0.90, 0.85),
    "zero_build": Box(0.40, 0.20, 0.62, 0.45),
    "fill": Box(0.12, 0.55, 0.32, 0.65),
    "squad": Box(0.05, 0.55, 0.11, 0.65),
    "squads_option": Box(0.05, 0.68, 0.15, 0.74),
    "cancel": Box(0.44, 0.15, 0.56, 0.22),
}


@dataclass
class VirtualClock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.001, seconds)

    def advance(self, seconds: float) -> None:
        self.now += seconds


class MockGame:
    def __init__(self, clock: VirtualClock) -> None:
        self.clock = clock
        self.state = "lobby"
        self.queue_at = 0.0
        self.loading_until = 0.0
        self.clicks: list[tuple[float, float]] = []
        self.escapes = 0
        self.leave_to_results = False

    def update(self) -> None:
        if self.state == "queue" and self.clock.now - self.queue_at >= 4.0:
            self.state = "match"
        if self.state == "loading" and self.clock.now >= self.loading_until:
            self.state = "lobby"

    @staticmethod
    def _inside(box: Box, x: float, y: float) -> bool:
        nx, ny = x / W, y / H
        return box.left <= nx <= box.right and box.top <= ny <= box.bottom

    def click_at(self, x: float, y: float) -> None:
        self.clicks.append((x, y))
        if self.state == "lobby" and self._inside(BOXES["play"], x, y):
            self.state = "queue"
            self.queue_at = self.clock.now
        elif self.state == "menu" and self._inside(BOXES["leave"], x, y):
            self.state = "confirm"
        elif self.state == "confirm" and self._inside(BOXES["confirm"], x, y):
            if self.leave_to_results:
                self.state = "results"
            else:
                self.state = "loading"
                self.loading_until = self.clock.now + 3.0
        elif self.state in ("results", "confirm") and self._inside(BOXES["return"], x, y):
            self.state = "loading"
            self.loading_until = self.clock.now + 2.0

    def escape(self) -> None:
        self.escapes += 1
        if self.state == "match":
            self.state = "menu"


class ScriptedVision:
    def __init__(self, game: MockGame) -> None:
        self.game = game
        self.calls = 0
        self.total_cost = 0.0
        self.explore_calls = 0
        self._last_state = game.state

    @staticmethod
    def _box(answers: dict[str, Any], name: str, box: Box, conf: float = 0.95,
             visible: bool = True) -> None:
        if not visible:
            return
        answers[name] = {"type": "box", "box": box.as_dict(), "confidence": conf}
        answers[name + "_visible"] = {"type": "noul", "noul": 1.0}

    @staticmethod
    def _choice(answers: dict[str, Any], name: str, value: str, conf: float = 0.9) -> None:
        answers[name] = {"type": "choice", "choice": value, "confidence": conf,
                         "probabilities": {value: conf}}

    def _explore_answers(self) -> dict[str, Any]:
        """Scripted walk -> open -> obstacle -> attack -> strafe sequence (v2 action schema)."""
        i = self.explore_calls
        self.explore_calls += 1
        answers: dict[str, Any] = {}
        answers["path"] = {"type": "choice", "choice": "clear", "confidence": 0.9,
                           "probabilities": {}}
        answers["target_visible"] = {"type": "noul", "noul": 0.0}
        answers["target_kind"] = {"type": "choice", "choice": "none", "confidence": 0.9,
                                  "probabilities": {}}
        answers["target_distance"] = {"type": "choice", "choice": "unclear",
                                      "confidence": 0.9, "probabilities": {}}
        answers["interact_ready"] = {"type": "noul", "noul": 0.0}
        answers["hold"] = {"type": "choice", "choice": "medium", "confidence": 0.9,
                           "probabilities": {}}
        answers["repeat"] = {"type": "choice", "choice": "once", "confidence": 0.9,
                             "probabilities": {}}
        if i == 0:
            self._choice(answers, "action", "move_forward")
            answers["target_visible"] = {"type": "noul", "noul": 0.92}
            answers["target_kind"] = {"type": "choice", "choice": "chest", "confidence": 0.9,
                                      "probabilities": {}}
            answers["target_distance"] = {"type": "choice", "choice": "far",
                                          "confidence": 0.9, "probabilities": {}}
            self._box(answers, "target", Box(0.46, 0.50, 0.54, 0.60))
        elif i == 1:
            self._choice(answers, "action", "interact")
            answers["hold"] = {"type": "choice", "choice": "long", "confidence": 0.9,
                               "probabilities": {}}
            answers["target_visible"] = {"type": "noul", "noul": 0.95}
            answers["target_kind"] = {"type": "choice", "choice": "chest", "confidence": 0.9,
                                      "probabilities": {}}
            answers["target_distance"] = {"type": "choice", "choice": "near",
                                          "confidence": 0.9, "probabilities": {}}
            answers["interact_ready"] = {"type": "noul", "noul": 0.92}
            self._box(answers, "target", Box(0.40, 0.34, 0.60, 0.72))
        elif i == 2:
            self._choice(answers, "action", "move_forward")
            answers["path"] = {"type": "choice", "choice": "low", "confidence": 0.9,
                               "probabilities": {}}
            answers["obstacle_ahead"] = {"type": "noul", "noul": 0.91}
        elif i == 3:
            self._choice(answers, "action", "attack")
            answers["hold"] = {"type": "choice", "choice": "short", "confidence": 0.9,
                               "probabilities": {}}
            answers["repeat"] = {"type": "choice", "choice": "twice", "confidence": 0.9,
                                 "probabilities": {}}
        else:
            self._choice(answers, "action", "move_forward_left")
            answers["hold"] = {"type": "choice", "choice": "short", "confidence": 0.9,
                               "probabilities": {}}
            answers["repeat"] = {"type": "choice", "choice": "three_times",
                                 "confidence": 0.9, "probabilities": {}}
        answers["hazard_ahead"] = {"type": "noul", "noul": 0.0}
        answers["look_around"] = {"type": "noul", "noul": 0.0}
        answers["eliminated"] = {"type": "noul", "noul": 0.0}
        return answers

    def observe(self, profile: str, frame: Frame) -> Observation:
        self.game.update()
        self.calls += 1
        answers: dict[str, Any] = {}
        state = self.game.state
        if state == "match" and self._last_state != "match":
            self.explore_calls = 0
        self._last_state = state
        if state == "lobby":
            screen = "lobby"
            self._choice(answers, "selected_mode", "zero_build")
            self._choice(answers, "squad_size", "squads")
            self._choice(answers, "fill_state", "on")
            self._box(answers, "play_button", BOXES["play"])
            self._box(answers, "zero_build_tile", BOXES["zero_build"])
            self._box(answers, "squad_control", BOXES["squad"])
            self._box(answers, "fill_toggle", BOXES["fill"])
        elif state == "queue":
            screen = "matchmaking"
            self._box(answers, "cancel_button", BOXES["cancel"])
        elif state == "match":
            screen = "in_match"
            if profile.startswith("explore"):
                answers.update(self._explore_answers())
            else:
                answers["eliminated"] = {"type": "noul", "noul": 0.0}
        elif state == "menu":
            screen = "esc_menu"
            self._box(answers, "leave_button", BOXES["leave"])
            answers["confirm_button_visible"] = {"type": "noul", "noul": 0.0}
        elif state == "confirm":
            screen = "esc_menu"
            self._box(answers, "confirm_button", BOXES["confirm"])
            answers["leave_button_visible"] = {"type": "noul", "noul": 0.0}
        elif state == "results":
            screen = "results"
            self._box(answers, "return_lobby_button", BOXES["return"])
            self._box(answers, "play_again_button", Box(0.62, 0.55, 0.88, 0.65))
        else:  # loading
            screen = "other"
        answers["screen"] = {
            "type": "choice", "choice": screen, "confidence": 0.99,
            "probabilities": {screen: 0.99},
        }
        return Observation(screen=screen, screen_confidence=0.99,
                           screen_probabilities={screen: 0.99}, answers=answers)


class FakeWindow:
    def find(self) -> int:
        return 1

    def is_foreground(self, hwnd: int) -> bool:
        return True

    def is_minimized(self, hwnd: int) -> bool:
        return False

    def focus(self, hwnd: int) -> bool:
        return True

    def client_rect(self, hwnd: int) -> Rect:
        return Rect(0, 0, W, H)


class FakeCapture:
    def grab(self, rect: Rect) -> Frame:
        return Frame(width=W, height=H, rgb=None, rect=rect, scale=1.0, captured_at=0.0)

    def close(self) -> None:
        pass


class FakeInput:
    def __init__(self, clock: VirtualClock, game: MockGame) -> None:
        self.clock = clock
        self.game = game
        self.actions: list[tuple[str, Any]] = []

    def click(self, x: int, y: int, button: str = "left") -> None:
        self.actions.append(("click", (x, y)))
        self.game.click_at(x, y)

    def key_down(self, key: str) -> None:
        self.actions.append(("down", key))

    def key_up(self, key: str) -> None:
        self.actions.append(("up", key))

    def mouse_down(self, button: str = "left") -> None:
        self.actions.append(("mouse_down", button))

    def mouse_up(self, button: str = "left") -> None:
        self.actions.append(("mouse_up", button))

    def press(self, key: str, hold_s: float = 0.08) -> None:
        self.actions.append(("press", key))
        self.clock.advance(hold_s)
        if key.lower() in ("esc", "escape"):
            self.game.escape()

    def hold(self, keys: list[str], hold_s: float) -> None:
        self.actions.append(("hold", tuple(keys)))
        self.clock.advance(hold_s)

    def move_relative(self, dx: int, dy: int) -> None:
        self.actions.append(("look", (dx, dy)))
        self.clock.advance(0.02)

    def release_all(self) -> None:
        pass
