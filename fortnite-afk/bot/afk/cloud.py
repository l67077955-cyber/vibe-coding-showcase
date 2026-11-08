"""Cloud-PC readiness helpers: session state, black-frame detection, keep-awake.

Haima/cloud desktops can disconnect the console, lock the workstation, or switch
to a virtual display that renders black. Clicking blind there is how accounts
get lost, so every frame is checked before the controller acts.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

from .capture import Frame

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)

WTS_CURRENT_SERVER_HANDLE = None
WTS_CONNECT_STATE = 8  # WTSConnectState
DESKTOP_SWITCHDESKTOP = 0x0100

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_AWAYMODE_REQUIRED = 0x00000040

CONNECT_STATES = {
    0: "active",
    1: "connected",
    2: "connect-query",
    3: "shadow",
    4: "disconnected",
    5: "idle",
    6: "listen",
    7: "reset",
    8: "down",
    9: "init",
}

user32.OpenInputDesktop.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
user32.OpenInputDesktop.restype = wt.HANDLE
user32.CloseDesktop.argtypes = (wt.HANDLE,)
user32.CloseDesktop.restype = wt.BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
kernel32.SetThreadExecutionState.argtypes = (wt.DWORD,)
kernel32.SetThreadExecutionState.restype = wt.DWORD
kernel32.ProcessIdToSessionId.argtypes = (wt.DWORD, ctypes.POINTER(wt.DWORD))
kernel32.ProcessIdToSessionId.restype = wt.BOOL
wtsapi32.WTSQuerySessionInformationW.argtypes = (
    wt.HANDLE, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD)
)
wtsapi32.WTSQuerySessionInformationW.restype = wt.BOOL
wtsapi32.WTSFreeMemory.argtypes = (ctypes.c_void_p,)
wtsapi32.WTSFreeMemory.restype = None


def session_id() -> int:
    sid = wt.DWORD()
    if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(sid)):
        return -1
    return int(sid.value)


def connect_state() -> tuple[int, str]:
    """WTS connect state for the current session (active/disconnected/...)."""
    pointer = ctypes.c_void_p()
    needed = wt.DWORD()
    ok = wtsapi32.WTSQuerySessionInformationW(
        WTS_CURRENT_SERVER_HANDLE, session_id(), WTS_CONNECT_STATE,
        ctypes.byref(pointer), ctypes.byref(needed),
    )
    if not ok or not pointer:
        return -1, "unknown"
    try:
        value = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int)).contents.value
    finally:
        wtsapi32.WTSFreeMemory(pointer)
    return value, CONNECT_STATES.get(value, f"state-{value}")


def is_remote_session() -> bool:
    return bool(user32.GetSystemMetrics(0x1000))  # SM_REMOTESESSION


def input_desktop_available() -> bool:
    """False when the workstation is locked / on the Winlogon desktop."""
    handle = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not handle:
        return False
    user32.CloseDesktop(handle)
    return True


def screen_metrics() -> dict[str, int]:
    return {
        "width": user32.GetSystemMetrics(0),
        "height": user32.GetSystemMetrics(1),
        "virtual_width": user32.GetSystemMetrics(78),
        "virtual_height": user32.GetSystemMetrics(79),
    }


def mean_luma(frame: Frame) -> float:
    """Approximate brightness (0..255), sampled on a stride for speed."""
    rgb = frame.rgb
    if not rgb:
        return 255.0
    pixel_count = len(rgb) // 3
    step = max(3, (pixel_count // 3000) * 3)
    total = 0
    count = 0
    for i in range(0, len(rgb) - 2, step):
        total += (rgb[i] * 299 + rgb[i + 1] * 587 + rgb[i + 2] * 114) // 1000
        count += 1
    return total / max(1, count)


def keep_awake(enable: bool) -> bool:
    flags = ES_CONTINUOUS
    if enable:
        flags |= ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    return bool(kernel32.SetThreadExecutionState(flags))


def session_summary() -> dict[str, object]:
    state, name = connect_state()
    metrics = screen_metrics()
    return {
        "session_id": session_id(),
        "remote_session": is_remote_session(),
        "connect_state": name,
        "input_desktop": input_desktop_available(),
        **metrics,
    }
