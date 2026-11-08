"""Measure a game instead of assuming it: mouse sensitivity from the pixels.

Every game maps mouse counts to camera angle differently, and the mapping is
the one thing the bot cannot infer from a single screenshot. Rather than ship a
per-game table, the bot can probe: move the mouse by a known number of counts,
compare the frame before and after, and measure how far the world slid.

`px_per_screen` is the result: mouse counts needed to pan the view by one full
screen width. Feeding it back into `motion.aim_px` makes the same aiming code
work on a twitchy shooter and a slow third-person game.

Movement speed needs no such constant: the in-match loop is closed on the
picture ("walk, look, press E; if nothing changed, walk more"), so the same
code adapts to a sprint speed or a crawl. `estimate_closing_rate` is provided
for callers that want a predictive shortcut from the target-box growth.
"""
from __future__ import annotations

import math
from typing import Sequence

from .capture import Frame


def _profile(frame: Frame, cols: int = 96, row_lo: float = 0.20,
             row_hi: float = 0.80) -> list[float]:
    """Average luminance per column, sampled coarsely over the middle rows.

    The middle band avoids the sky and the ground, which barely move when the
    camera pans and would dilute the correlation.
    """
    if frame.rgb is None or frame.width <= 0 or frame.height <= 0:
        return []
    width, height = frame.width, frame.height
    y0 = max(0, int(height * row_lo))
    y1 = min(height, int(height * row_hi))
    if y1 - y0 < 2:
        return []
    y_step = max(1, (y1 - y0) // 24)
    x_step = max(1, width // (cols * 3))
    profile: list[float] = []
    for c in range(cols):
        x0 = int(width * c / cols)
        x1 = max(x0 + 1, int(width * (c + 1) / cols))
        total = 0.0
        count = 0
        for y in range(y0, y1, y_step):
            row = y * width
            for x in range(x0, x1, x_step):
                i = (row + x) * 3
                total += (frame.rgb[i] * 0.299 + frame.rgb[i + 1] * 0.587
                          + frame.rgb[i + 2] * 0.114)
                count += 1
        profile.append(total / count if count else 0.0)
    return profile


def _normalise(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    return [v - mean for v in values]


def estimate_shift(before: Frame, after: Frame, *, cols: int = 96,
                   max_shift: float = 0.45) -> tuple[float, float]:
    """Horizontal pan between two frames.

    Returns ``(shift, confidence)`` where ``shift`` is a fraction of the frame
    width, positive when the scene content moved right (camera turned left),
    and ``confidence`` is the peak normalised cross-correlation (-1..1).
    Below ~0.3 the match is not trustworthy and callers should reject it.
    """
    a = _normalise(_profile(before, cols))
    b = _normalise(_profile(after, cols))
    n = len(a)
    if n < 8 or len(b) != n:
        return 0.0, 0.0
    limit = max(1, int(n * max_shift))
    best_shift, best_corr = 0, -2.0
    min_overlap = int(n * 0.45)
    for shift in range(-limit, limit + 1):
        lo = max(0, shift)
        hi = min(n, n + shift)
        if hi - lo < min_overlap:
            continue
        num = den_a = den_b = 0.0
        for i in range(lo, hi):
            av = a[i - shift]
            bv = b[i]
            num += av * bv
            den_a += av * av
            den_b += bv * bv
        if den_a <= 1e-9 or den_b <= 1e-9:
            continue
        corr = num / math.sqrt(den_a * den_b)
        if corr > best_corr:
            best_shift, best_corr = shift, corr
    return best_shift / n, best_corr


def measure_sensitivity(before: Frame, after: Frame, delta_px: int, *,
                        min_shift: float = 0.03,
                        min_confidence: float = 0.30) -> dict:
    """Turn one probe move into ``px_per_screen`` for ``motion.TurnConfig``.

    ``delta_px`` is the signed mouse delta that was injected between the two
    frames. Returns ``{"ok", "shift", "confidence", "px_per_screen", "reason"}``.
    """
    shift, confidence = estimate_shift(before, after)
    result = {"ok": False, "shift": round(shift, 4),
              "confidence": round(confidence, 3), "px_per_screen": 0.0,
              "reason": ""}
    if abs(delta_px) < 8:
        result["reason"] = "probe delta too small"
        return result
    if confidence < min_confidence:
        result["reason"] = f"frame match too weak ({confidence:.2f})"
        return result
    if abs(shift) < min_shift:
        result["reason"] = f"scene barely moved ({shift:+.3f} of width)"
        return result
    result["ok"] = True
    result["px_per_screen"] = round(abs(delta_px) / abs(shift), 3)
    result["reason"] = "ok"
    return result


def estimate_closing_rate(height_before: float, height_after: float,
                          dt_s: float) -> float | None:
    """How fast the player closes on a target, from its apparent size.

    Apparent height scales with 1/distance, so ``1/h`` is proportional to
    distance. The returned value is "inverse-distance units per second": the
    distance in units of the current distance shrinks by this much each second.
    Multiply by the current time-to-contact to predict arrival.
    """
    if dt_s <= 0 or height_before <= 0 or height_after <= 0:
        return None
    # Positive when the target is getting closer (height growing).
    rate = (1.0 / height_before - 1.0 / height_after) / dt_s
    return rate
