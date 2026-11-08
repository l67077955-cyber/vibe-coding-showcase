"""`keytest`: compare SendInput vs PostMessage in this Windows/cloud session.

Cloud desktops (notably Haima) sometimes accept SendInput at the API level but
swallow the keyboard events before any window sees WM_KEYDOWN. This test opens
its own window, focuses it, sends W both ways, and counts the messages that
actually arrive. Mouse injection is tested separately by `demo`.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

from .win32 import InputController, PostMessageInput

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
SW_SHOW = 5
COLOR_WINDOW = 5
IDC_ARROW = 32512
ASFW_ANY = -1


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
user32.RegisterClassW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = (
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
)
user32.CreateWindowExW.restype = wt.HWND
user32.DefWindowProcW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.ShowWindow.argtypes = (wt.HWND, ctypes.c_int)
user32.UpdateWindow.argtypes = (wt.HWND,)
user32.SetForegroundWindow.argtypes = (wt.HWND,)
user32.SetFocus.argtypes = (wt.HWND,)
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.POINTER(wt.DWORD))
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = (wt.DWORD, wt.DWORD, wt.BOOL)
user32.AttachThreadInput.restype = wt.BOOL
user32.BringWindowToTop.argtypes = (wt.HWND,)
user32.SetActiveWindow.argtypes = (wt.HWND,)
user32.PostQuitMessage.argtypes = (ctypes.c_int,)
user32.PostMessageW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.AllowSetForegroundWindow.argtypes = (wt.DWORD,)
user32.LoadCursorW.argtypes = (wt.HINSTANCE, wt.LPCWSTR)
user32.LoadCursorW.restype = wt.HANDLE
user32.PeekMessageW.argtypes = (ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT)
user32.TranslateMessage.argtypes = (ctypes.POINTER(wt.MSG),)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wt.MSG),)
kernel32.GetModuleHandleW.argtypes = (wt.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wt.HINSTANCE
kernel32.GetCurrentThreadId.restype = wt.DWORD

_wndproc_ref = None


def _force_foreground(hwnd: int) -> tuple[bool, str]:
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
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
    time.sleep(0.25)
    ok = user32.GetForegroundWindow() == hwnd
    return ok, f"foreground_before={fg} foreground_after={user32.GetForegroundWindow()}"


def _pump(seconds: float) -> None:
    end = time.time() + seconds
    msg = wt.MSG()
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.005)


def key_test(key: str = "w") -> dict[str, object]:
    counts = {"keydown": 0, "keyup": 0, "char": 0}
    hwnd_out: dict[str, int] = {}

    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_KEYDOWN:
            counts["keydown"] += 1
        elif msg == WM_KEYUP:
            counts["keyup"] += 1
        elif msg == WM_CHAR:
            counts["char"] += 1
        elif msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    global _wndproc_ref
    _wndproc_ref = WNDPROC(wndproc)
    hinst = kernel32.GetModuleHandleW(None)
    class_name = f"FortniteAfkKeyTest{int(time.time())}"
    wc = WNDCLASSW()
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = hinst
    wc.hCursor = user32.LoadCursorW(None, ctypes.cast(ctypes.c_void_p(IDC_ARROW), wt.LPCWSTR))
    wc.hbrBackground = wt.HBRUSH(COLOR_WINDOW + 1)
    wc.lpszClassName = class_name
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise ctypes.WinError(ctypes.get_last_error())

    hwnd = user32.CreateWindowExW(
        0, class_name, "Fortnite AFK - input backend test", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        260, 240, 520, 180, None, None, hinst, None,
    )
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    user32.AllowSetForegroundWindow(wt.DWORD(ASFW_ANY))
    focused, focus_detail = _force_foreground(hwnd)
    print(f"test window hwnd={hwnd} focused={focused} ({focus_detail})")

    results: dict[str, object] = {"focused": focused}
    for label, sender in (
        ("sendinput", InputController()),
        ("postmessage", PostMessageInput(lambda: hwnd)),
    ):
        for k in counts:
            counts[k] = 0
        _pump(0.15)
        try:
            sender.press(key, 0.10)
        except Exception as exc:
            print(f"{label}: error {exc}")
            results[label] = {"error": str(exc)}
            continue
        _pump(0.45)
        results[label] = dict(counts)
        print(f"{label:12s} keydown={counts['keydown']} keyup={counts['keyup']} "
              f"char={counts['char']}")

    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    _pump(0.4)
    return results


if __name__ == "__main__":
    key_test()
