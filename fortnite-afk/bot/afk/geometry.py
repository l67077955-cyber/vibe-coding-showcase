"""Geometry helpers: Jev returns boxes as fractions of the image, the game needs pixels."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Rect:
    """A rectangle in screen pixels (Win32 client-area coordinates already mapped)."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class Box:
    """Normalised box, 0..1, origin at the top-left of the image."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2.0, (self.top + self.bottom) / 2.0)

    def padded(self, amount: float) -> "Box":
        return Box(
            max(0.0, self.left - amount),
            max(0.0, self.top - amount),
            min(1.0, self.right + amount),
            min(1.0, self.bottom + amount),
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "left": round(self.left, 4),
            "top": round(self.top, 4),
            "right": round(self.right, 4),
            "bottom": round(self.bottom, 4),
        }


def parse_box(value: Any) -> Box | None:
    """Turn an API box answer into a validated Box.

    Jev occasionally returns a box with swapped edges or values a hair outside
    0..1. We normalise those, but reject anything degenerate or wildly out of
    range instead of clicking a random spot.
    """
    if not isinstance(value, Mapping):
        return None
    try:
        left = float(value["left"])
        top = float(value["top"])
        right = float(value["right"])
        bottom = float(value["bottom"])
    except (KeyError, TypeError, ValueError):
        return None

    values = (left, top, right, bottom)
    if any(v != v or v in (float("inf"), float("-inf")) for v in values):  # NaN/inf
        return None
    if min(values) < -0.25 or max(values) > 1.25:
        return None

    if left > right:
        left, right = right, left
    if top > bottom:
        top, bottom = bottom, top

    left, right = max(0.0, left), min(1.0, right)
    top, bottom = max(0.0, top), min(1.0, bottom)
    box = Box(left, top, right, bottom)
    if box.width < 0.004 or box.height < 0.004:
        return None
    return box


def box_to_screen(box: Box, rect: Rect) -> tuple[int, int, int, int]:
    """Map a normalised box onto a screen rectangle, returning pixel edges."""
    left = rect.left + round(box.left * rect.width)
    top = rect.top + round(box.top * rect.height)
    right = rect.left + round(box.right * rect.width)
    bottom = rect.top + round(box.bottom * rect.height)
    left = max(rect.left, min(left, rect.right - 1))
    top = max(rect.top, min(top, rect.bottom - 1))
    right = max(rect.left + 1, min(right, rect.right))
    bottom = max(rect.top + 1, min(bottom, rect.bottom))
    return left, top, right, bottom


def box_center_screen(box: Box, rect: Rect) -> tuple[int, int]:
    left, top, right, bottom = box_to_screen(box, rect)
    return (left + right) // 2, (top + bottom) // 2
