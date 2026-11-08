"""Win32 plumbing: window lookup, DPI, client rect, SendInput keys/mouse, panic key.

Deliberately dependency-free (ctypes only). Fortnite reads keyboard input via
scan codes, so keys are injected as KEYEVENTF_SCANCODE rather than virtual-key
messages; that is also what most working game macros do.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import random
import time

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
GA_ROOT = 2
SW_RESTORE = 9

user32.SendInput.argtypes = (wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wt.UINT
user32.MapVirtualKeyW.argtypes = (wt.UINT, wt.UINT)
user32.MapVirtualKeyW.restype = wt.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetForegroundWindow.restype = wt.HWND
user32.GetAncestor.argtypes = (wt.HWND, wt.UINT)
user32.GetAncestor.restype = wt.HWND
user32.ClientToScreen.argtypes = (wt.HWND, ctypes.POINTER(POINT))
user32.ClientToScreen.restype = wt.BOOL
user32.GetClientRect.argtypes = (wt.HWND, ctypes.POINTER(RECT))
user32.GetClientRect.restype = wt.BOOL
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = (wt.HWND,)
user32.SetForegroundWindow.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.POINTER(wt.DWORD))
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = (wt.DWORD, wt.DWORD, wt.BOOL)
user32.AttachThreadInput.restype = wt.BOOL
user32.BringWindowToTop.argtypes = (wt.HWND,)
user32.BringWindowToTop.restype = wt.BOOL
user32.SetActiveWindow.argtypes = (wt.HWND,)
user32.SetActiveWindow.restype = wt.HWND
user32.SetFocus.argtypes = (wt.HWND,)
user32.SetFocus.restype = wt.HWND
kernel32.GetCurrentThreadId.restype = wt.DWORD
user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
user32.GetCursorPos.restype = wt.BOOL
user32.PostMessageW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.PostMessageW.restype = wt.BOOL
user32.IsWindow.argtypes = (wt.HWND,)
user32.IsWindow.restype = wt.BOOL
user32.ScreenToClient.argtypes = (wt.HWND, ctypes.POINTER(POINT))
user32.ScreenToClient.restype = wt.BOOL
user32.FindWindowW.argtypes = (wt.LPCWSTR, wt.LPCWSTR)
user32.FindWindowW.restype = wt.HWND
user32.EnumWindows.argtypes = (WNDENUMPROC, wt.LPARAM)
user32.EnumWindows.restype = wt.BOOL
user32.GetClassNameW.argtypes = (wt.HWND, wt.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wt.HWND, wt.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = (wt.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = (wt.HWND,)
user32.IsWindowVisible.restype = wt.BOOL
user32.IsIconic.argtypes = (wt.HWND,)
user32.IsIconic.restype = wt.BOOL
user32.ShowWindow.argtypes = (wt.HWND, ctypes.c_int)
user32.ShowWindow.restype = wt.BOOL
user32.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
user32.SetProcessDPIAware.restype = wt.BOOL

VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)

EXTENDED = {"left", "up", "right", "down"}


def enable_dpi_awareness() -> None:
    """Without this, coordinates are virtualised on scaled displays and every click is off."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            log.warning("Could not enable DPI awareness; clicks may be offset on scaled displays")


def _vk(key: str) -> int:
    k = key.lower()
    if k in VK:
        return VK[k]
    if len(k) == 1:
        return ord(k.upper())
    raise ValueError(f"Unsupported key: {key!r}")


def _send_key(vk: int, up: bool, mode: str = "both") -> None:
    scan = user32.MapVirtualKeyW(vk, 0)  # MAPVK_VK_TO_VSC
    if mode == "scancode":
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        w_vk, w_scan = 0, scan
    elif mode == "virtualkey":
        flags = KEYEVENTF_KEYUP if up else 0
        w_vk, w_scan = vk, 0
    else:  # both: virtual key + scan code, no SCANCODE flag -> WM_CHAR works too
        flags = KEYEVENTF_KEYUP if up else 0
        w_vk, w_scan = vk, scan
    if _name_for_vk(vk) in EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=w_vk, wScan=w_scan, dwFlags=flags, time=0, dwExtraInfo=0)
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _name_for_vk(vk: int) -> str:
    for name, value in VK.items():
        if value == vk:
            return name
    return ""


def key_is_down(key: str) -> bool:
    return bool(user32.GetAsyncKeyState(_vk(key)) & 0x8000)


def find_window(class_name: str = "UnrealWindow", title_substr: str = "Fortnite") -> int | None:
    """Find the visible game window by class, then by title substring."""
    hwnd = user32.FindWindowW(class_name, None) if class_name else 0
    if hwnd and user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if title_substr.lower() in title.value.lower():
            return int(hwnd)

    found: list[int] = []

    @WNDENUMPROC
    def _enum(hwnd_, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd_):
            return True
        if class_name:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_, buf, 256)
            if buf.value != class_name:
                return True
        length = user32.GetWindowTextLengthW(hwnd_)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd_, title, length + 1)
        if title_substr.lower() in title.value.lower():
            found.append(int(hwnd_))
        return True

    user32.EnumWindows(_enum, 0)
    return found[0] if found else None


def is_foreground(hwnd: int) -> bool:
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    return fg == hwnd or user32.GetAncestor(fg, GA_ROOT) == user32.GetAncestor(hwnd, GA_ROOT)


def focus_window(hwnd: int) -> bool:
    """Bring the game forward, bypassing the foreground-lock when possible.

    A plain SetForegroundWindow is often denied for a background script. The
    AttachThreadInput dance is the standard workaround and is what makes cloud
    desktops (where another console may hold focus) usable.
    """
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        foreground = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(foreground, None)
        our_thread = kernel32.GetCurrentThreadId()
        attached = False
        if fg_thread and fg_thread != our_thread:
            attached = bool(user32.AttachThreadInput(our_thread, fg_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        if attached:
            user32.AttachThreadInput(our_thread, fg_thread, False)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def is_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


def client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Return (left, top, width, height) of the window's client area in screen pixels."""
    rc = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        raise ctypes.WinError(ctypes.get_last_error())
    width, height = rc.right - rc.left, rc.bottom - rc.top
    if width <= 0 or height <= 0:
        raise RuntimeError("Fortnite window has no client area (minimised?)")
    pt = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        raise ctypes.WinError(ctypes.get_last_error())
    return pt.x, pt.y, width, height


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


class InputController:
    """Human-ish keyboard/mouse injector with a dry-run mode and stuck-key cleanup."""

    def __init__(self, dry_run: bool = False, rng: random.Random | None = None,
                 key_mode: str = "both") -> None:
        self.dry_run = dry_run
        self.rng = rng or random.Random()
        self.key_mode = key_mode
        self._pressed: set[str] = set()

    # ---- keyboard -----------------------------------------------------
    def key_down(self, key: str) -> None:
        key = key.lower()
        if self.dry_run:
            log.info("[dry-run] key down %s", key)
            return
        _send_key(_vk(key), up=False, mode=self.key_mode)
        self._pressed.add(key)

    def key_up(self, key: str) -> None:
        key = key.lower()
        if self.dry_run:
            log.info("[dry-run] key up %s", key)
            return
        try:
            _send_key(_vk(key), up=True, mode=self.key_mode)
        finally:
            self._pressed.discard(key)

    def press(self, key: str, hold_s: float = 0.08) -> None:
        self.key_down(key)
        try:
            time.sleep(max(0.02, hold_s))
        finally:
            self.key_up(key)

    def hold(self, keys: list[str], hold_s: float) -> None:
        for key in keys:
            self.key_down(key)
        try:
            time.sleep(max(0.02, hold_s))
        finally:
            for key in reversed(keys):
                self.key_up(key)

    def release_all(self) -> None:
        for key in sorted(self._pressed):
            try:
                self.key_up(key)
            except Exception:
                pass
        self._pressed.clear()

    # ---- mouse --------------------------------------------------------
    def move_to(self, x: int, y: int) -> None:
        if self.dry_run:
            log.info("[dry-run] cursor -> (%d, %d)", x, y)
            return
        user32.SetCursorPos(int(x), int(y))

    def click(self, x: int, y: int, button: str = "left") -> None:
        if self.dry_run:
            log.info("[dry-run] click %s at (%d, %d)", button, x, y)
            return
        self.move_to(x, y)
        time.sleep(self.rng.uniform(0.04, 0.10))
        self.mouse_down(button)
        time.sleep(self.rng.uniform(0.04, 0.09))
        self.mouse_up(button)

    def mouse_down(self, button: str = "left") -> None:
        if self.dry_run:
            log.info("[dry-run] mouse %s down", button)
            return
        flag = MOUSEEVENTF_LEFTDOWN if button == "left" else 0x0008  # right down
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_up(self, button: str = "left") -> None:
        if self.dry_run:
            log.info("[dry-run] mouse %s up", button)
            return
        flag = MOUSEEVENTF_LEFTUP if button == "left" else 0x0010  # right up
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def move_relative(self, dx: int, dy: int) -> None:
        if self.dry_run:
            log.info("[dry-run] mouse move (%d, %d)", dx, dy)
            return
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx=int(dx), dy=int(dy), mouseData=0, dwFlags=MOUSEEVENTF_MOVE,
                            time=0, dwExtraInfo=0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class PostMessageInput:
    """Keyboard/mouse via PostMessage, for games that read window messages.

    Useful on cloud desktops that swallow SendInput keyboard events (Haima's
    filter did exactly that in testing). SDL/GLFW games such as Luanti accept
    this; Unreal/Fortnite may ignore it for raw gameplay input, so test with
    `keytest` and a dry run first.
    """

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONDOWN = 0x0204
    WM_RBUTTONUP = 0x0205

    def __init__(self, get_hwnd, dry_run: bool = False, rng: random.Random | None = None) -> None:
        self.get_hwnd = get_hwnd
        self.dry_run = dry_run
        self.rng = rng or random.Random()
        self._pressed: set[str] = set()
        self._cached_hwnd: int | None = None

    def _hwnd(self) -> int:
        if self._cached_hwnd and user32.IsWindow(self._cached_hwnd):
            return self._cached_hwnd
        hwnd = self.get_hwnd()
        if not hwnd:
            raise RuntimeError("PostMessage input: game window not found")
        self._cached_hwnd = int(hwnd)
        return self._cached_hwnd

    def _key(self, key: str, up: bool) -> None:
        vk = _vk(key)
        scan = user32.MapVirtualKeyW(vk, 0)
        lparam = 1 | (scan << 16) | (0xC0000000 if up else 0)
        user32.PostMessageW(self._hwnd(), self.WM_KEYUP if up else self.WM_KEYDOWN,
                            wt.WPARAM(vk), wt.LPARAM(lparam))

    def key_down(self, key: str) -> None:
        if self.dry_run:
            log.info("[dry-run] post key down %s", key)
            return
        self._key(key, False)
        self._pressed.add(key.lower())

    def key_up(self, key: str) -> None:
        if self.dry_run:
            log.info("[dry-run] post key up %s", key)
            return
        try:
            self._key(key, True)
        finally:
            self._pressed.discard(key.lower())

    def press(self, key: str, hold_s: float = 0.08) -> None:
        self.key_down(key)
        try:
            time.sleep(max(0.02, hold_s))
        finally:
            self.key_up(key)

    def hold(self, keys: list[str], hold_s: float) -> None:
        for key in keys:
            self.key_down(key)
        try:
            time.sleep(max(0.02, hold_s))
        finally:
            for key in reversed(keys):
                self.key_up(key)

    def release_all(self) -> None:
        for key in sorted(self._pressed):
            try:
                self.key_up(key)
            except Exception:
                pass
        self._pressed.clear()

    def click(self, x: int, y: int, button: str = "left") -> None:
        if self.dry_run:
            log.info("[dry-run] post click %s at (%d, %d)", button, x, y)
            return
        hwnd = self._hwnd()
        pt = POINT(int(x), int(y))
        user32.ScreenToClient(hwnd, ctypes.byref(pt))
        lparam = (pt.y << 16) | (pt.x & 0xFFFF)
        user32.PostMessageW(hwnd, self.WM_MOUSEMOVE, 0, lparam)
        time.sleep(self.rng.uniform(0.03, 0.08))
        down_msg = self.WM_LBUTTONDOWN if button == "left" else self.WM_RBUTTONDOWN
        up_msg = self.WM_LBUTTONUP if button == "left" else self.WM_RBUTTONUP
        user32.PostMessageW(hwnd, down_msg, 1 if button == "left" else 2, lparam)
        time.sleep(self.rng.uniform(0.04, 0.09))
        user32.PostMessageW(hwnd, up_msg, 0, lparam)

    def mouse_down(self, button: str = "left") -> None:
        if self.dry_run:
            log.info("[dry-run] post mouse %s down", button)
            return
        hwnd = self._hwnd()
        left, top, width, height = client_rect(hwnd)
        lparam = ((height // 2) << 16) | ((width // 2) & 0xFFFF)
        msg = self.WM_LBUTTONDOWN if button == "left" else self.WM_RBUTTONDOWN
        user32.PostMessageW(hwnd, msg, 1 if button == "left" else 2, lparam)

    def mouse_up(self, button: str = "left") -> None:
        if self.dry_run:
            log.info("[dry-run] post mouse %s up", button)
            return
        hwnd = self._hwnd()
        left, top, width, height = client_rect(hwnd)
        lparam = ((height // 2) << 16) | ((width // 2) & 0xFFFF)
        msg = self.WM_LBUTTONUP if button == "left" else self.WM_RBUTTONUP
        user32.PostMessageW(hwnd, msg, 0, lparam)

    def move_relative(self, dx: int, dy: int) -> None:
        if self.dry_run:
            log.info("[dry-run] post look (%d, %d)", dx, dy)
            return
        # Games using raw mouse input ignore this; SDL games may still accept it.
        hwnd = self._hwnd()
        pt = POINT(0, 0)
        user32.GetCursorPos(ctypes.byref(pt))
        pt.x += int(dx)
        pt.y += int(dy)
        user32.ScreenToClient(hwnd, ctypes.byref(pt))
        lparam = (pt.y << 16) | (pt.x & 0xFFFF)
        user32.PostMessageW(hwnd, self.WM_MOUSEMOVE, 0, lparam)


class HybridInput(PostMessageInput):
    """Keyboard via PostMessage, mouse via SendInput.

    The usual cloud-desktop split: real mouse injection works, synthetic
    keyboard events are filtered. Use this when `keytest` shows PostMessage
    keyboard is OK but SendInput keyboard is not.
    """

    def __init__(self, get_hwnd, dry_run: bool = False, rng: random.Random | None = None) -> None:
        super().__init__(get_hwnd, dry_run=dry_run, rng=rng)
        self._mouse = InputController(dry_run=dry_run, rng=rng)

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._mouse.click(x, y, button)

    def mouse_down(self, button: str = "left") -> None:
        self._mouse.mouse_down(button)

    def mouse_up(self, button: str = "left") -> None:
        self._mouse.mouse_up(button)

    def move_relative(self, dx: int, dy: int) -> None:
        self._mouse.move_relative(dx, dy)


def make_input(cfg, window, rng: random.Random | None = None):
    """Pick the configured input backend; all expose the same controller API."""
    rng = rng or random.Random()
    if cfg.input_backend == "postmessage":
        return PostMessageInput(lambda: window.find(), dry_run=cfg.safety.dry_run, rng=rng)
    if cfg.input_backend == "hybrid":
        return HybridInput(lambda: window.find(), dry_run=cfg.safety.dry_run, rng=rng)
    return InputController(dry_run=cfg.safety.dry_run, rng=rng, key_mode=cfg.key_mode)
