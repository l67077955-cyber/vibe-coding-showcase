"""Persisted camera-sensitivity estimate.

``px_per_screen`` answers one question: how many mouse pixels pan the view by
a full screen width? It depends on the game, the in-game sensitivity slider and
the stream resolution, so the only way to know it is to measure it at runtime.
Re-measuring from 1.0 on every launch wastes the opening minutes of every
session, so the newest probe result is written to ``state/sensitivity.json``
and the next run starts from there.

The file is deliberately separate from ``config.json``: config is hand-edited
intent, this is measured state. A bad probe can therefore never rewrite the
user's settings, and editing the config never silently throws away what the
bot has learned.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .capture import Frame

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "sensitivity.json"

MIN_SCALE = 0.25
MAX_SCALE = 8.0
HISTORY = 25


def clamp(value: float, lo: float = MIN_SCALE, hi: float = MAX_SCALE) -> float:
    return max(lo, min(hi, float(value)))


def read(path: Path | None = None) -> dict:
    """Best-effort read; a missing or corrupt file is simply "no state yet"."""
    path = path or STATE_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_scale(default: float, path: Path | None = None) -> float:
    """Last measured px_per_screen, or ``default`` when nothing usable exists."""
    value = read(path).get("px_per_screen")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float(default)
    if not (MIN_SCALE <= float(value) <= MAX_SCALE):
        return float(default)
    return float(value)


def save_scale(scale: float, *, view_shift: str | None = None,
               confidence: float | None = None, source: str = "session_loop",
               path: Path | None = None) -> dict:
    """Write one measurement atomically and return the updated state.

    Called right after every probe, not only on a clean exit, so Ctrl-C or a
    crash still leaves the last good number on disk.
    """
    path = path or STATE_PATH
    state = read(path)
    now = datetime.now().isoformat(timespec="seconds")
    value = round(clamp(scale), 4)

    entry: dict = {"at": now, "scale": value, "source": source}
    if view_shift is not None:
        entry["view_shift"] = view_shift
    if confidence is not None:
        entry["confidence"] = round(float(confidence), 3)

    state["px_per_screen"] = value
    state["updated_at"] = now
    state["probes"] = int(state.get("probes", 0) or 0) + 1
    state["last"] = entry

    history = state.get("history")
    if not isinstance(history, list):
        history = []
    history.append(entry)
    state["history"] = history[-HISTORY:]

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return state
