"""Configuration: defaults, JSON overlay, validation, and API-key resolution."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from .motion import TurnConfig

# When frozen by PyInstaller, config/logs/key.txt live next to the .exe, not
# inside the temporary extraction directory.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = APP_DIR / "config.json"


class ConfigError(RuntimeError):
    pass


@dataclass
class CaptureConfig:
    # Frames are downscaled before they go to Jev. Box answers are normalised,
    # so this only trades accuracy on tiny UI elements against latency/cost.
    # Measured on this machine (375 B/s-ish uplink through Clash):
    #   1280px -> 3.1 s/decision, 960px -> 3.0 s, 768px -> 2.0 s.
    # 768 keeps chest-sized objects crisp while cutting the upload in half.
    max_width: int = 768
    # Extra pixels cropped from the captured client area, in screen pixels.
    inset_left: int = 0
    inset_top: int = 0
    inset_right: int = 0
    inset_bottom: int = 0


@dataclass
class ConfidenceConfig:
    box: float = 0.35
    screen: float = 0.55
    presence: float = 0.50
    # Jev may answer a Box with confidence: null. Treat it as this neutral value.
    allow_null: bool = True
    null_value: float = 0.50
    # Reject boxes that cover almost the whole frame (usually a miss).
    max_box_side: float = 0.92


@dataclass
class TimingConfig:
    lobby_poll_s: float = 3.0
    queue_poll_s: float = 6.0
    match_check_s: float = 45.0
    # Random match length before the script leaves and requeues.
    match_minutes: tuple[float, float] = (16.0, 22.0)
    queue_timeout_s: float = 240.0
    leave_timeout_s: float = 45.0
    action_settle_s: float = 1.2
    lobby_cooldown_s: float = 6.0
    max_actions_per_state: int = 8


@dataclass
class AfkConfig:
    move_every_s: tuple[float, float] = (18.0, 45.0)
    move_hold_s: tuple[float, float] = (0.25, 1.0)
    jump_every_s: tuple[float, float] = (110.0, 280.0)
    look_every_s: tuple[float, float] = (25.0, 70.0)
    crouch_every_s: tuple[float, float] = (240.0, 600.0)
    # Chance that a movement step also jumps.
    jump_with_move: float = 0.15


@dataclass
class ModeConfig:
    # off    - never check the selected mode
    # verify - check it, but refuse to start a match if it is wrong
    # auto   - click the mode controls until the check passes
    setup: str = "verify"
    zero_build: bool = True
    squads: bool = True
    fill: bool = True


@dataclass
class SafetyConfig:
    panic_key: str = "f12"
    require_foreground: bool = True
    focus_on_start: bool = True
    max_consecutive_failures: int = 5
    dry_run: bool = False
    # Hard stop after this many completed lobby -> match cycles (0 = unlimited).
    max_cycles: int = 0


@dataclass
class ExploreConfig:
    enabled: bool = True
    interval_s: tuple[float, float] = (2.5, 4.0)
    move_hold_s: tuple[float, float] = (0.45, 0.9)
    interact_key: str = "e"
    interact_hold_s: float = 1.0
    chest_min_presence: float = 0.55
    # A box this tall counts as "already close". 0.22 was low enough that a
    # stylised chest 4 m away qualified, so the bot pressed E from out of range;
    # 0.34 only trips when the object really fills the lower view.
    chest_near_box_height: float = 0.34
    chest_cooldown_s: float = 7.0
    stuck_similarity: float = 0.985
    stuck_limit: int = 2
    look_every_s: tuple[float, float] = (8.0, 16.0)
    # Jev question set for the in-match loop. `explore_fast` asks 11 questions
    # instead of 18; fewer answers = fewer output tokens = lower latency.
    question_profile: str = "explore_fast"
    # Keep movement keys held between Jev decisions for smooth, continuous motion.
    continuous: bool = True
    # Safety cap: release movement if no fresh decision arrives within this time.
    max_continuous_s: float = 4.5
    # Turn toward the target in small eased mouse steps instead of one snap.
    smooth_turn: bool = True


@dataclass
class CloudConfig:
    # Keep the cloud display awake while the script runs.
    keep_awake: bool = True
    # Strict mode: pause when WTS reports the console disconnected. Off by
    # default so a cloud plan that keeps rendering in the background can farm;
    # the foreground/black-frame guards still stop blind clicking.
    pause_when_disconnected: bool = False
    # A frame darker than this mean luma is treated as a black/blank capture.
    black_frame_min_luma: float = 3.0
    max_consecutive_black_frames: int = 10


@dataclass
class LoggingConfig:
    dir: str = "logs"
    save_frames: str = "failures"  # off | failures | all
    level: str = "INFO"


@dataclass
class Config:
    backend: str = "openrouter"  # openrouter | typesafe
    api_url: str = "https://openrouter.ai/api/v1/systemone"
    model: str = "typesafe/jev-1.14"
    api_key_env: str = "OPENROUTER_API_KEY"
    api_key_file: str = ""
    api_key: str = ""  # prefer the environment variable; kept for local overrides
    proxy: str = "auto"  # auto | none | http://127.0.0.1:7890
    input_backend: str = "sendinput"  # sendinput | postmessage | hybrid
    key_mode: str = "both"  # both | scancode | virtualkey (sendinput only)
    request_timeout_s: float = 45.0
    max_retries: int = 3
    window_class: str = "UnrealWindow"
    window_title: str = "Fortnite"
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    turn: TurnConfig = field(default_factory=TurnConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    afk: AfkConfig = field(default_factory=AfkConfig)
    mode: ModeConfig = field(default_factory=ModeConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    explore: ExploreConfig = field(default_factory=ExploreConfig)
    cloud: CloudConfig = field(default_factory=CloudConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _coerce(value: Any, annotation: Any, path: str) -> Any:
    """Coerce JSON lists to tuples and validate simple scalar types."""
    origin = get_origin(annotation)
    if origin is tuple:
        args = get_args(annotation)
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f"{path}: expected a list, got {type(value).__name__}")
        if len(value) != len(args):
            raise ConfigError(f"{path}: expected {len(args)} items, got {len(value)}")
        return tuple(_coerce(v, args[0], f"{path}[{i}]") for i, v in enumerate(value))
    if origin is not None:  # other generics: leave as-is
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{path}: expected true/false")
        return value
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: expected an integer")
        return value
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{path}: expected a number")
        return float(value)
    if annotation is str:
        if not isinstance(value, str):
            raise ConfigError(f"{path}: expected a string")
        return value
    return value


def _build(cls: type, data: dict[str, Any], path: str) -> Any:
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected an object")
    known = {f.name: f for f in fields(cls)}
    hints = get_type_hints(cls)
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ConfigError(f"{path}: unknown option(s): {', '.join(unknown)}")
    kwargs = {}
    for name, f in known.items():
        if name not in data:
            continue
        value = data[name]
        annotation = hints[name]
        if is_dataclass(annotation):
            kwargs[name] = _build(annotation, value, f"{path}.{name}" if path else name)
        else:
            kwargs[name] = _coerce(value, annotation, f"{path}.{name}" if path else name)
    return cls(**kwargs)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    cfg = Config()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path}: invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: top level must be an object")
        cfg = _build(Config, data, "")
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    if cfg.backend not in ("openrouter", "typesafe"):
        raise ConfigError("backend must be 'openrouter' or 'typesafe'")
    if cfg.input_backend not in ("sendinput", "postmessage", "hybrid"):
        raise ConfigError("input_backend must be 'sendinput', 'postmessage' or 'hybrid'")
    if cfg.key_mode not in ("both", "scancode", "virtualkey"):
        raise ConfigError("key_mode must be 'both', 'scancode' or 'virtualkey'")
    if not cfg.api_url.startswith("https://"):
        raise ConfigError("api_url must start with https://")
    if not cfg.model:
        raise ConfigError("model must not be empty")
    if not (320 <= cfg.capture.max_width <= 3840):
        raise ConfigError("capture.max_width must be between 320 and 3840")
    for name in ("box", "screen", "presence", "null_value"):
        value = getattr(cfg.confidence, name)
        if not (0.0 <= value <= 1.0):
            raise ConfigError(f"confidence.{name} must be between 0 and 1")
    if not (0.1 <= cfg.confidence.max_box_side <= 1.0):
        raise ConfigError("confidence.max_box_side must be between 0.1 and 1.0")
    if cfg.mode.setup not in ("off", "verify", "auto"):
        raise ConfigError("mode.setup must be 'off', 'verify' or 'auto'")
    if cfg.safety.panic_key.lower() not in ("f12", "f11", "f10", "f9", "f8"):
        raise ConfigError("safety.panic_key must be one of F8-F12")
    if cfg.safety.max_cycles < 0:
        raise ConfigError("safety.max_cycles must be >= 0")
    if not (0.0 <= cfg.cloud.black_frame_min_luma <= 255.0):
        raise ConfigError("cloud.black_frame_min_luma must be between 0 and 255")
    if cfg.cloud.max_consecutive_black_frames < 1:
        raise ConfigError("cloud.max_consecutive_black_frames must be >= 1")
    if cfg.logging.save_frames not in ("off", "failures", "all"):
        raise ConfigError("logging.save_frames must be 'off', 'failures' or 'all'")

    def positive_range(name: str, value: tuple[float, float]) -> None:
        low, high = value
        if low <= 0 or high < low:
            raise ConfigError(f"{name} must be a positive range with low <= high")

    positive_range("timing.match_minutes", cfg.timing.match_minutes)
    positive_range("afk.move_every_s", cfg.afk.move_every_s)
    positive_range("afk.move_hold_s", cfg.afk.move_hold_s)
    positive_range("afk.jump_every_s", cfg.afk.jump_every_s)
    positive_range("afk.look_every_s", cfg.afk.look_every_s)
    positive_range("afk.crouch_every_s", cfg.afk.crouch_every_s)
    positive_range("explore.interval_s", cfg.explore.interval_s)
    positive_range("explore.move_hold_s", cfg.explore.move_hold_s)
    positive_range("explore.look_every_s", cfg.explore.look_every_s)
    if not (0.0 <= cfg.explore.chest_min_presence <= 1.0):
        raise ConfigError("explore.chest_min_presence must be between 0 and 1")
    if not (0.0 <= cfg.explore.chest_near_box_height <= 1.0):
        raise ConfigError("explore.chest_near_box_height must be between 0 and 1")
    if not (0.0 <= cfg.explore.stuck_similarity <= 1.0):
        raise ConfigError("explore.stuck_similarity must be between 0 and 1")
    if cfg.explore.max_continuous_s <= 0:
        raise ConfigError("explore.max_continuous_s must be > 0")
    if not (0.0 <= cfg.afk.jump_with_move <= 1.0):
        raise ConfigError("afk.jump_with_move must be between 0 and 1")


def resolve_api_key(cfg: Config) -> str:
    """Environment first, then an explicit file, then the inline field.

    The key is never logged. A missing key is a hard, explanatory error.
    """
    env_value = os.environ.get(cfg.api_key_env, "").strip()
    if env_value:
        return env_value
    if cfg.api_key_file:
        path = Path(os.path.expandvars(os.path.expanduser(cfg.api_key_file)))
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        raise ConfigError(f"api_key_file not found or empty: {path}")
    for candidate in (APP_DIR / "key.txt", APP_DIR / "openrouter.key"):
        if candidate.exists():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    if cfg.api_key.strip():
        return cfg.api_key.strip()
    raise ConfigError(
        f"No API key. Set the {cfg.api_key_env} environment variable, create key.txt "
        f"next to the script/exe, or set api_key_file in config.json."
    )


def apply_overrides(cfg: Config, *, dry_run: bool | None = None, max_cycles: int | None = None,
                    max_minutes: float | None = None) -> None:
    if dry_run is not None:
        cfg.safety.dry_run = dry_run
    if max_cycles is not None:
        cfg.safety.max_cycles = max_cycles
    if max_minutes is not None:
        cfg.timing.match_minutes = (max_minutes, max_minutes)


def config_summary(cfg: Config) -> str:
    return (
        f"backend={cfg.backend} model={cfg.model} "
        f"input={cfg.input_backend}/{cfg.key_mode} "
        f"mode={cfg.mode.setup} explore={cfg.explore.enabled} "
        f"match={cfg.timing.match_minutes[0]:g}-"
        f"{cfg.timing.match_minutes[1]:g}min dry_run={cfg.safety.dry_run}"
    )
