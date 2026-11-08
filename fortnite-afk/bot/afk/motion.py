"""Human-like camera turning and timing primitives.

The old bot snapped the camera with one random 160-320 px mouse jump and then
held a movement key for a fixed 0.8 s. Both read as robotic: the view
teleports in a single frame and the character starts/stops on a hard edge.
This module replaces those two moves with primitives that can be driven at
50 Hz:

* :func:`plan_turn` splits one correction into a burst of small mouse deltas
  with an ease-in/ease-out (smoothstep) speed curve, so the camera
  accelerates and settles instead of snapping.
* :func:`aim_px` turns a normalised target position into a damped,
  deadzoned, bounded pixel correction, so a partially centred target is not
  overshot on every frame and micro-noise does not cause twitching.
* :func:`jitter` and :func:`scan_delta` add the small timing and gaze
  irregularities that keep a session from looking periodic.

Everything here is pure: no module state, and every random draw takes an
explicit ``random.Random``. That keeps runs reproducible and lets two
controllers share the module without interfering.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class TurnConfig:
    """Tuning for an AI-ish camera turn.

    ``max_px_per_s`` is a velocity budget, not a per-tick step: a real hand
    sweeps the mouse over several frames instead of jumping the full distance
    at once. ``gain`` stays below 1 so a visible target is approached
    monotonically (no overshoot-and-correct oscillation), and ``deadzone_px``
    swallows the last few pixels of error that a human would also ignore.
    """

    max_px_per_s: float = 900.0   # cap on camera speed
    tick_s: float = 0.02          # one mouse-move tick (50 Hz)
    deadzone_px: float = 10.0     # ignore tiny corrections
    gain: float = 0.65            # proportional gain, <1 avoids overshoot
    max_step_px: float = 420.0    # never plan more than this in one decision
    min_ticks: int = 2
    max_ticks: int = 24
    # Mouse pixels needed to pan the view by one full screen width. This is the
    # one number that changes between games: 1.0 means "1 mouse px = 1 screen
    # px", a game with half the sensitivity needs 2.0. Measured by
    # tools/tune_game.py and written back here; the controller never assumes it.
    px_per_screen: float = 1.0
    # Hand tremor: a human never holds the camera perfectly still. Two slow
    # sinusoids (drift) plus per-tick jitter and an occasional tiny flick.
    noise: bool = True
    noise_drift_px: float = 5.0        # peak slow drift, in mouse px
    noise_tremor_px: float = 0.8       # per-tick jitter
    noise_saccade_px: float = 7.0      # occasional flick size
    noise_saccade_every_s: tuple[float, float] = (2.5, 7.0)


def smoothstep(t: float) -> float:
    """3t^2 - 2t^3, clamped to [0, 1].

    Zero slope at both ends is what gives a turn its ease-in/ease-out: the
    first and last ticks move very little, so the camera does not lurch on
    the first frame and does not slam to a stop on the last.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


class CameraNoise:
    """Bounded hand tremor for the camera.

    Three layers, because a real hand is not white noise:

    * **drift** - two slow sinusoids with random frequency/phase. This is the
      slow wander you see when someone holds a mouse still for a few seconds.
    * **tremor** - a small per-tick jitter, the physiological shake.
    * **saccade** - occasional tiny flicks, and their sign alternates so a long
      session does not slowly rotate the view away from the target.

    All amplitudes are in mouse pixels and are applied through the same
    ``move_relative`` path as deliberate turns, so the game's own sensitivity
    scales the effect exactly like a human hand would be scaled.
    """

    def __init__(self, rng: random.Random, cfg: TurnConfig = TurnConfig()) -> None:
        self.rng = rng
        self.cfg = cfg
        self.t = 0.0
        if cfg.noise_drift_px > 0:
            self.freqs = (rng.uniform(0.05, 0.13), rng.uniform(0.16, 0.30))
            self.phases = (rng.uniform(0.0, math.tau), rng.uniform(0.0, math.tau))
            self.amps = (cfg.noise_drift_px * rng.uniform(0.55, 1.0),
                         cfg.noise_drift_px * rng.uniform(0.25, 0.55))
        else:
            self.freqs = (0.0, 0.0)
            self.phases = (0.0, 0.0)
            self.amps = (0.0, 0.0)
        self._last = self._wave(0.0)
        self._next_saccade = rng.uniform(*cfg.noise_saccade_every_s)
        self._saccade_sign = rng.choice((-1, 1))
        self.saccades = 0

    def _wave(self, t: float) -> float:
        return sum(amp * math.sin(math.tau * freq * t + phase)
                   for amp, freq, phase in zip(self.amps, self.freqs, self.phases))

    def step(self, dt: float) -> tuple[int, int]:
        """Advance ``dt`` seconds and return the (dx, dy) tremor in mouse px."""
        if not self.cfg.noise or dt <= 0:
            return 0, 0
        self.t += dt
        current = self._wave(self.t)
        dx = current - self._last
        self._last = current

        # The tremor is defined per 50 Hz tick; a longer step gets proportionally
        # more shake so a slow loop does not feel unnaturally still.
        scale = min(3.0, dt / 0.02)
        dx += self.rng.uniform(-1.0, 1.0) * self.cfg.noise_tremor_px * scale
        dy = self.rng.uniform(-1.0, 1.0) * self.cfg.noise_tremor_px * scale * 0.7

        if self.t >= self._next_saccade:
            self._saccade_sign *= -1
            dx += (self._saccade_sign * self.rng.uniform(0.4, 1.0)
                   * self.cfg.noise_saccade_px)
            self.saccades += 1
            self._next_saccade = self.t + self.rng.uniform(*self.cfg.noise_saccade_every_s)
        return int(round(dx)), int(round(dy))


def aim_px(center_norm: float, frame_width: int, cfg: TurnConfig = TurnConfig()) -> int:
    """Pixels to move the mouse so a target at normalized x lands on screen centre.

    ``center_norm`` is 0..1 with 0 at the left edge; positive means "turn
    right", matching the sign convention of raw mouse-dx. The correction is
    scaled by ``gain`` (<1) and then compared with ``deadzone_px``: after the
    gain even a modest offset produces only a few pixels of movement, and
    chasing those is what makes a bot jitter at a target it already faces.
    The final clamp to ``max_step_px`` bounds a single decision so a bad box
    from the detector cannot throw the view across the map.
    """
    if frame_width <= 0:
        return 0
    offset = (float(center_norm) - 0.5) * float(frame_width)
    # Convert screen pixels to mouse pixels for this game's sensitivity. With
    # px_per_screen < 1 the same mouse movement turns further, so the demand
    # shrinks; with > 1 the game is sluggish and the demand grows.
    px = offset * float(cfg.gain) * float(cfg.px_per_screen)
    if abs(px) <= float(cfg.deadzone_px):
        return 0
    limit = int(round(cfg.max_step_px))
    if limit < 0:
        limit = 0
    return max(-limit, min(limit, int(round(px))))


def plan_turn(dx_px: int, cfg: TurnConfig = TurnConfig()) -> list[int]:
    """Split one turn into per-tick mouse deltas with a smooth speed profile.

    The sum of the list is exactly the requested delta (possibly clamped to
    ``max_step_px``), which is the key invariant: the controller can trust
    that the camera ends up where it asked, without drift accumulating across
    hundreds of small turns. Rounding error is therefore not dropped, it is
    folded into the largest tick.

    The magnitude is distributed over ``n`` ticks by sampling ``smoothstep``
    at cumulative fractions ``i/n``: slow start, fast middle, slow stop.
    ``n`` is chosen from the velocity budget (peak slope of smoothstep is 1.5,
    so the peak tick is about ``1.5 * |dx| / n``) and clamped to
    ``[min_ticks, max_ticks]``. Negative deltas are produced by planning the
    magnitude once and negating, so left turns mirror right turns exactly.
    """
    dx = int(dx_px)
    if dx == 0:
        return []

    cap = float(cfg.max_px_per_s) * float(cfg.tick_s) * 1.6
    if cap <= 0.0 or cfg.max_ticks <= 0:
        return []

    limit = int(round(cfg.max_step_px))
    if limit <= 0:
        return []
    mag = min(abs(dx), limit)
    if mag == 0:
        return []

    # 1.8 instead of the theoretical 1.5 leaves headroom for the integer
    # leftover that is folded into the largest tick.
    ticks = int(math.ceil((1.8 * mag) / cap))
    ticks = max(int(cfg.min_ticks), min(int(cfg.max_ticks), ticks))

    steps: list[int] = []
    prev = 0.0
    for i in range(1, ticks + 1):
        cur = smoothstep(i / ticks)
        steps.append(int(round((cur - prev) * mag)))
        prev = cur

    leftover = mag - sum(steps)
    if leftover:
        biggest = max(range(len(steps)), key=lambda idx: steps[idx])
        steps[biggest] += leftover

    sign = 1 if dx > 0 else -1
    return [sign * step for step in steps]


def turn_duration(steps: list[int], cfg: TurnConfig = TurnConfig()) -> float:
    """len(steps) * tick_s.

    Wall-clock time to sleep across a planned turn. Kept next to
    :func:`plan_turn` so the caller never has to know the tick rate.
    """
    return len(steps) * float(cfg.tick_s)


def jitter(seconds: float, rng: random.Random, amount: float = 0.12) -> float:
    """seconds * uniform(1-amount, 1+amount), floored at 0.01.

    A fixed hold time is the single most obvious bot tell in a replay: every
    key press has the same duration to the millisecond. The floor keeps a
    jittered value usable as a sleep argument even for tiny or negative
    inputs.
    """
    value = float(seconds) * rng.uniform(1.0 - float(amount), 1.0 + float(amount))
    return max(0.01, value)


def scan_delta(rng: random.Random, direction: int, frame_width: int,
               magnitude: float = 0.16) -> int:
    """A small human head-scan: direction -1/0/+1, magnitude as a fraction of the
    frame width, with +/-25% randomness. direction 0 -> 0.

    Humans do not hold a perfectly still camera; they make small corrective
    glances. A bounded, slightly random nudge reads as looking around, while
    an exact repetition of the same offset reads as a loop. ``direction`` 0
    is the "keep looking" case and must not move the mouse at all.
    """
    if direction == 0 or frame_width <= 0:
        return 0
    base = float(frame_width) * float(magnitude)
    px = base * rng.uniform(0.75, 1.25)
    moved = int(round(px))
    return moved if direction > 0 else -moved
