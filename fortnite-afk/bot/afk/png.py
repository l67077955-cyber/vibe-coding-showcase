"""Minimal pure-stdlib PNG writer (RGB, 8 bit) and rectangle overlay.

No Pillow, no numpy: Windows ships Python nowhere, but a frozen exe or a plain
CPython install can run this module with zero third-party packages.
"""
from __future__ import annotations

import struct
import zlib

from .geometry import Box


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_rgb(width: int, height: int, rgb: bytes | bytearray) -> bytes:
    """Encode raw top-down RGB24 pixels as a PNG."""
    stride = width * 3
    if len(rgb) != stride * height:
        raise ValueError(f"expected {stride * height} bytes, got {len(rgb)}")
    raw = bytearray((stride + 1) * height)
    src = memoryview(rgb)
    for y in range(height):
        dst = y * (stride + 1)
        raw[dst] = 0  # filter: None
        raw[dst + 1:dst + 1 + stride] = src[y * stride:(y + 1) * stride]
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def draw_rect(rgb: bytearray, width: int, height: int, box: Box,
              color: tuple[int, int, int] = (0, 255, 120), thickness: int = 3) -> None:
    """Draw a rectangle in-place on top-down RGB24 pixels."""
    left = max(0, min(width - 1, round(box.left * width)))
    right = max(0, min(width - 1, round(box.right * width)))
    top = max(0, min(height - 1, round(box.top * height)))
    bottom = max(0, min(height - 1, round(box.bottom * height)))
    stride = width * 3
    r, g, b = color
    for t in range(max(1, thickness)):
        for x in range(left, right + 1):
            for y in (top + t, bottom - t):
                if 0 <= y < height:
                    i = y * stride + x * 3
                    rgb[i:i + 3] = bytes((r, g, b))
        for y in range(top, bottom + 1):
            for x in (left + t, right - t):
                if 0 <= x < width:
                    i = y * stride + x * 3
                    rgb[i:i + 3] = bytes((r, g, b))
