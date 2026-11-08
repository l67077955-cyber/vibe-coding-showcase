"""In-match exploration: turn Jev's first-person judgement into key presses.

The model answers one `move` Choice per frame plus chest/obstacle Nouls. Code
keeps the rules: hazards override forward motion, a low obstacle turns a walk
into a jump, and a near chest turns into an interact hold. A coarse frame
signature detects "walked into a wall and nothing changed" so the loop backs
out instead of grinding against geometry.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .config import Config
from .jev import Observation

MOVE_KEYS: dict[str, list[str]] = {
    "forward": ["w"],
    "forward_left": ["w", "a"],
    "forward_right": ["w", "d"],
    "left": ["a"],
    "right": ["d"],
    "backward": ["s"],
    "jump_forward": ["w"],
    "stop": [],
}

# Jev v2: the model picks the operation, the hold length and the repeat count.
HOLD_SECONDS = {"tap": 0.12, "short": 0.35, "medium": 0.8, "long": 1.6}
REPEAT_COUNTS = {"once": 1, "twice": 2, "three_times": 3}
ACTION_KEYS: dict[str, list[str]] = {
    "move_forward": ["w"],
    "move_forward_left": ["w", "a"],
    "move_forward_right": ["w", "d"],
    "strafe_left": ["a"],
    "strafe_right": ["d"],
    "back_up": ["s"],
    "jump_forward": ["w"],
    "jump_in_place": [],
    "interact": ["e"],
    "attack": [],
    "aim": [],
    "reload": ["r"],
    "look_left": [],
    "look_right": [],
    "stop": [],
}
FORWARD_ACTIONS = {"move_forward", "move_forward_left", "move_forward_right", "jump_forward"}
MOVEMENT_ACTIONS = {"move_forward", "move_forward_left", "move_forward_right",
                    "strafe_left", "strafe_right", "back_up"}


@dataclass
class ExplorePlan:
    keys: list[str]
    hold_s: float
    jump: bool = False
    interact: bool = False
    look_dx: int = 0
    reason: str = ""
    move: str = ""
    move_confidence: float = 0.0
    chest_presence: float = 0.0
    chest_distance: str = "unclear"
    action: str = ""
    hold_label: str = ""
    repeat: int = 1
    mouse: str = ""
    target_kind: str = ""
    continuous: bool = False
    # Normalised horizontal offset from screen centre to the object Jev found
    # (-0.5 .. +0.5). The controller converts it to pixels and turns with the
    # eased profile, so the camera aims at the chest instead of snapping.
    aim_norm: float = 0.0
    # Same idea on the vertical axis: positive means the target is below the
    # crosshair, so the camera should tilt down. Without this the bot only ever
    # turned left/right.
    aim_norm_y: float = 0.0


def frame_signature(frame) -> tuple[int, ...]:
    """8x8 average-luma thumbnail; cheap enough to run on every decision."""
    rgb = frame.rgb
    if not rgb:
        return ()
    width, height = frame.width, frame.height
    cells: list[int] = []
    for gy in range(8):
        y0 = gy * height // 8
        y1 = max(y0 + 1, (gy + 1) * height // 8)
        for gx in range(8):
            x0 = gx * width // 8
            x1 = max(x0 + 1, (gx + 1) * width // 8)
            total = 0
            count = 0
            step_y = max(1, (y1 - y0) // 8)
            step_x = max(1, (x1 - x0) // 8)
            for y in range(y0, y1, step_y):
                row = y * width * 3
                for x in range(x0, x1, step_x):
                    i = row + x * 3
                    total += (rgb[i] * 299 + rgb[i + 1] * 587 + rgb[i + 2] * 114) // 1000
                    count += 1
            cells.append(total // max(1, count))
    return tuple(cells)


def signature_similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return 1.0 - (sum(abs(x - y) for x, y in zip(a, b)) / len(a)) / 255.0


def plan_explore(obs: Observation, cfg: Config, rng: random.Random,
                 *, chest_ready: bool) -> ExplorePlan:
    action, action_conf = obs.choice("action")
    # The v2 question set is identified by the presence of the `action` key, not
    # by its confidence. Falling through to the legacy `move` schema when the
    # model is unsure would silently drop the action/hold/repeat contract (and
    # `move` does not even exist in the fast profile).
    if "action" in obs.answers:
        return _plan_action(obs, cfg, rng, chest_ready=chest_ready,
                            action=action or "move_forward", action_conf=action_conf)

    move, move_conf = obs.choice("move")
    chest_presence = obs.noul("chest_visible") or 0.0
    distance, distance_conf = obs.choice("chest_distance")
    obstacle = obs.noul("obstacle_ahead") or 0.0
    hazard = obs.noul("hazard_ahead") or 0.0
    look_around = (obs.noul("look_around") or 0.0) >= 0.5
    hold = rng.uniform(*cfg.explore.move_hold_s)

    chest_box = obs.usable_box(
        "chest",
        min_confidence=cfg.confidence.box,
        min_presence=cfg.explore.chest_min_presence,
        allow_null=cfg.confidence.allow_null,
        null_value=cfg.confidence.null_value,
        max_side=cfg.confidence.max_box_side,
    )
    chest_big = chest_box is not None and chest_box.height >= cfg.explore.chest_near_box_height
    chest_near = distance == "near" and (distance_conf >= 0.40 or chest_big)
    if (chest_presence >= cfg.explore.chest_min_presence
            and (chest_near or chest_big)
            and chest_ready):
        return ExplorePlan(
            keys=[cfg.explore.interact_key], hold_s=cfg.explore.interact_hold_s,
            interact=True, reason="near loot chest", move=move or "",
            move_confidence=move_conf, chest_presence=chest_presence,
            chest_distance=distance or "unclear",
        )

    if move not in MOVE_KEYS or move_conf < 0.35:
        # Low-confidence model answer: keep moving but respect obvious danger.
        move = "backward" if hazard >= 0.6 else "forward"
        move_conf = 0.0

    if hazard >= 0.65 and move in ("forward", "forward_left", "forward_right", "jump_forward"):
        move = "backward"
        reason = "hazard ahead"
    elif obstacle >= 0.65 and move == "forward":
        move = "jump_forward"
        reason = "low obstacle -> jump while moving"
    else:
        reason = f"model chose {move}"

    look_dx = 0
    if look_around or move == "stop":
        look_dx = rng.choice([-1, 1]) * rng.randint(160, 320)
    if move == "stop":
        # Standing still forever is how an AFK loop dies; back out and scan.
        keys = ["s"]
        hold = min(hold, 0.5)
        reason = "stop -> back up and scan"
    else:
        keys = list(MOVE_KEYS[move])

    return ExplorePlan(
        keys=keys, hold_s=hold, jump=(move == "jump_forward"),
        interact=False, look_dx=look_dx, reason=reason, move=move,
        move_confidence=move_conf, chest_presence=chest_presence,
        chest_distance=distance or "unclear",
    )


def _plan_action(obs: Observation, cfg: Config, rng: random.Random, *,
                 chest_ready: bool, action: str, action_conf: float) -> ExplorePlan:
    """Jev v2: operation + hold length + repeat count, with code-side safety rules."""
    hold_label, _ = obs.choice("hold")
    repeat_label, _ = obs.choice("repeat")
    hold = HOLD_SECONDS.get(hold_label or "", 0.7)
    repeat = REPEAT_COUNTS.get(repeat_label or "", 1)
    repeat = max(1, min(3, repeat))

    target_visible = obs.noul("target_visible") or 0.0
    target_kind, _ = obs.choice("target_kind")
    target_distance, distance_conf = obs.choice("target_distance")
    interact_ready = obs.noul("interact_ready") or 0.0
    chest_visible = obs.noul("chest_visible") or 0.0
    path, _ = obs.choice("path")
    obstacle = obs.noul("obstacle_ahead") or 0.0
    hazard = obs.noul("hazard_ahead") or 0.0
    look_around = (obs.noul("look_around") or 0.0) >= 0.5

    def box(name: str):
        return obs.usable_box(
            name,
            min_confidence=cfg.confidence.box,
            min_presence=cfg.explore.chest_min_presence,
            allow_null=cfg.confidence.allow_null,
            null_value=cfg.confidence.null_value,
            max_side=cfg.confidence.max_box_side,
        )

    target_box = box("target")
    chest_box = box("chest")
    if target_visible < cfg.explore.chest_min_presence and chest_visible >= cfg.explore.chest_min_presence:
        target_visible = chest_visible
        target_kind = "chest"
        target_box = chest_box
        target_distance, distance_conf = obs.choice("chest_distance")

    target_kind = target_kind or "none"
    target_is_object = target_kind in ("chest", "door", "button", "vehicle", "loot", "other")
    target_big = target_box is not None and target_box.height >= cfg.explore.chest_near_box_height
    target_near = (target_distance == "near" and (distance_conf >= 0.40 or target_big)) or target_big

    aim_norm = 0.0
    aim_norm_y = 0.0
    if target_box is not None and target_visible >= cfg.explore.chest_min_presence:
        # Aim at the object's centre. Full 0.5 offset would mean "turn half a
        # screen"; aim_px() turns it into a bounded, eased mouse movement.
        aim_norm = max(-0.5, min(0.5, target_box.center[0] - 0.5))
        aim_norm_y = max(-0.5, min(0.5, target_box.center[1] - 0.5))

    reason = f"model action {action}"
    if (chest_ready and target_is_object
            and target_visible >= cfg.explore.chest_min_presence
            and target_near and interact_ready >= 0.40):
        action = "interact"
        hold = max(hold, cfg.explore.interact_hold_s)
        repeat = 1
        reason = f"near {target_kind} ready -> interact"
    elif path == "hazard" or hazard >= 0.65:
        action = "back_up"
        reason = "hazard/drop ahead -> back up"
    # A visible landmark outranks "something low ahead": walking toward the
    # chest and letting the stuck-escape handle a real obstruction beats
    # hopping in place against a fence while the chest sits off to the side.
    landmark = target_box is not None and target_visible >= cfg.explore.chest_min_presence
    if (path == "low" or obstacle >= 0.65) and action in FORWARD_ACTIONS and not landmark:
        action = "jump_forward"
        reason = "low obstacle -> jump while moving"
    elif path == "high_wall" and action in FORWARD_ACTIONS and not landmark:
        if target_box is not None and target_box.center[0] < 0.5:
            action = "strafe_left"
        else:
            action = "strafe_right"
        reason = "high wall -> strafe around it"

    if action not in ACTION_KEYS:
        action = "move_forward"
        action_conf = 0.0
    if action == "interact" and not (target_is_object and target_near and interact_ready >= 0.40):
        action = "move_forward"
        reason = "interact without a near target -> walk forward"
    if action_conf < 0.25:
        action = "move_forward"
        action_conf = 0.0
        reason = "low confidence -> forward"

    look_dx = 0
    if action == "look_left":
        look_dx = -rng.randint(160, 320)
    elif action == "look_right":
        look_dx = rng.randint(160, 320)
    elif action == "stop" or look_around:
        look_dx = rng.choice([-1, 1]) * rng.randint(160, 320)

    if action == "stop":
        action = "back_up"
        reason = "stop -> back up and scan"
    if action == "interact":
        keys = [cfg.explore.interact_key]
    else:
        keys = list(ACTION_KEYS[action])
    mouse = "left" if action == "attack" else ("right" if action == "aim" else "")
    jump = action in ("jump_forward", "jump_in_place")
    interact = action == "interact"

    return ExplorePlan(
        keys=keys, hold_s=hold, jump=jump, interact=interact, look_dx=look_dx,
        reason=reason, move=action, move_confidence=action_conf,
        chest_presence=target_visible, chest_distance=target_distance or "unclear",
        action=action, hold_label=hold_label or "", repeat=repeat, mouse=mouse,
        target_kind=target_kind,
        continuous=cfg.explore.continuous and action in MOVEMENT_ACTIONS,
        aim_norm=aim_norm,
        aim_norm_y=aim_norm_y,
    )


def describe(plan: ExplorePlan) -> str:
    bits = []
    if plan.action:
        bits.append(f"action={plan.action}({plan.move_confidence:.2f})")
    else:
        bits.append(f"move={plan.move}({plan.move_confidence:.2f})")
    if plan.continuous:
        bits.append("hold=continuous")
    elif plan.hold_label:
        bits.append(f"hold={plan.hold_label}:{plan.hold_s:.2f}s")
    if plan.repeat > 1 and not plan.continuous:
        bits.append(f"x{plan.repeat}")
    if plan.mouse:
        bits.append(f"mouse={plan.mouse}")
    if plan.target_kind:
        bits.append(f"target={plan.target_kind}/{plan.chest_distance}")
    if plan.jump:
        bits.append("jump")
    if plan.interact:
        bits.append("interact")
    if plan.aim_norm:
        bits.append(f"aim={plan.aim_norm:+.2f}")
    if plan.look_dx:
        bits.append(f"look={plan.look_dx}")
    return ", ".join(bits)
