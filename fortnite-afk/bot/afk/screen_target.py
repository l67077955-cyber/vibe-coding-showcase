"""The only target the controller is allowed to use: the screen itself.

There is no window lookup here on purpose. The old controller called
FindWindow/EnumWindows, read the client rect, checked the foreground window and
called SetForegroundWindow. All of that needs an HWND for the game, which this
build deliberately never obtains.

Instead the target is a fixed screen rectangle (the whole screen by default, or
`capture.region`), and the controller simply captures it. You keep the game
focused yourself; the black-frame guard is the only sanity check left.
"""
from __future__ import annotations

import ctypes

from .config import Config
from .geometry import Rect

user32 = ctypes.WinDLL("user32", use_last_error=True)


class ScreenTarget:
    """Duck-types the old GameWindow so the state machine is unchanged."""

    screen_only = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # The controller treats a truthy result as "the game is there".
    def find(self) -> int:
        return 1

    def is_foreground(self, _hwnd: int) -> bool:
        return True

    def is_minimized(self, _hwnd: int) -> bool:
        return False

    def focus(self, _hwnd: int) -> bool:
        return True

    def client_rect(self, _hwnd: int = 0) -> Rect:
        region = self.cfg.capture.region
        if region:
            return Rect(*region)
        return Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
