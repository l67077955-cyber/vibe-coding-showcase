"""Zero-dependency screen capture using GDI (BitBlt/StretchBlt) + a stdlib PNG writer.

Works on borderless / windowed-fullscreen Fortnite. Exclusive fullscreen can
return a black frame; the README tells the user to switch display mode.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Rect
from .png import encode_rgb, png_size

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
HALFTONE = 4

HDC = wt.HDC
HBITMAP = wt.HBITMAP
HGDIOBJ = wt.HANDLE


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [("rgbBlue", ctypes.c_ubyte), ("rgbGreen", ctypes.c_ubyte),
                ("rgbRed", ctypes.c_ubyte), ("rgbReserved", ctypes.c_ubyte)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


gdi32.CreateCompatibleDC.argtypes = (HDC,)
gdi32.CreateCompatibleDC.restype = HDC
gdi32.CreateCompatibleBitmap.argtypes = (HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = HBITMAP
gdi32.SelectObject.argtypes = (HDC, HGDIOBJ)
gdi32.SelectObject.restype = HGDIOBJ
gdi32.DeleteObject.argtypes = (HGDIOBJ,)
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteDC.argtypes = (HDC,)
gdi32.DeleteDC.restype = wt.BOOL
gdi32.StretchBlt.argtypes = (HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wt.DWORD)
gdi32.StretchBlt.restype = wt.BOOL
gdi32.SetStretchBltMode.argtypes = (HDC, ctypes.c_int)
gdi32.SetStretchBltMode.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = (HDC, HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wt.UINT)
gdi32.GetDIBits.restype = ctypes.c_int
user32.GetDC.argtypes = (wt.HWND,)
user32.GetDC.restype = HDC
user32.ReleaseDC.argtypes = (wt.HWND, HDC)
user32.ReleaseDC.restype = ctypes.c_int


@dataclass
class Frame:
    width: int
    height: int
    rgb: bytearray | None  # top-down RGB24, None for a pre-encoded image
    rect: Rect  # screen-space rectangle this frame covers
    scale: float  # width / original client width
    captured_at: float
    _encoded_png: bytes | None = field(default=None, repr=False)

    def png_bytes(self) -> bytes:
        if self._encoded_png is not None:
            return self._encoded_png
        if self.rgb is None:
            raise RuntimeError("frame has no pixels")
        return encode_rgb(self.width, self.height, self.rgb)

    def png_base64(self) -> str:
        return base64.b64encode(self.png_bytes()).decode("ascii")

    def save_png(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.png_bytes())
        return path

    @classmethod
    def from_png_file(cls, path: str | Path) -> "Frame":
        data = Path(path).read_bytes()
        width, height = png_size(data)
        return cls(width=width, height=height, rgb=None, rect=Rect(0, 0, width, height),
                   scale=1.0, captured_at=time.time(), _encoded_png=data)


class ScreenCapture:
    def __init__(self, max_width: int = 1280, inset_left: int = 0, inset_top: int = 0,
                 inset_right: int = 0, inset_bottom: int = 0) -> None:
        self.max_width = max_width
        self.insets = (inset_left, inset_top, inset_right, inset_bottom)

    def grab(self, rect: Rect) -> Frame:
        left = rect.left + self.insets[0]
        top = rect.top + self.insets[1]
        right = rect.right - self.insets[2]
        bottom = rect.bottom - self.insets[3]
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            raise RuntimeError("capture rectangle is empty; check capture insets")

        scale = min(1.0, self.max_width / width)
        out_w = max(1, round(width * scale))
        out_h = max(1, round(height * scale))

        screen_dc = user32.GetDC(None)
        if not screen_dc:
            raise ctypes.WinError(ctypes.get_last_error())
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, out_w, out_h)
        old_obj = None
        try:
            if not mem_dc or not bitmap:
                raise ctypes.WinError(ctypes.get_last_error())
            old_obj = gdi32.SelectObject(mem_dc, bitmap)
            gdi32.SetStretchBltMode(mem_dc, HALFTONE)
            ok = gdi32.StretchBlt(
                mem_dc, 0, 0, out_w, out_h,
                screen_dc, left, top, width, height, SRCCOPY,
            )
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            gdi32.SelectObject(mem_dc, old_obj)
            old_obj = None

            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = out_w
            bmi.bmiHeader.biHeight = -out_h  # top-down rows
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB
            buf = ctypes.create_string_buffer(out_w * out_h * 4)
            lines = gdi32.GetDIBits(mem_dc, bitmap, 0, out_h, buf, ctypes.byref(bmi),
                                    DIB_RGB_COLORS)
            if lines != out_h:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if old_obj:
                gdi32.SelectObject(mem_dc, old_obj)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)

        bgra = buf.raw
        rgb = bytearray(out_w * out_h * 3)
        rgb[0::3] = bgra[2::4]
        rgb[1::3] = bgra[1::4]
        rgb[2::3] = bgra[0::4]
        return Frame(width=out_w, height=out_h, rgb=rgb, rect=Rect(left, top, width, height),
                     scale=scale, captured_at=time.time())

    def close(self) -> None:  # symmetry with the old mss backend
        pass
