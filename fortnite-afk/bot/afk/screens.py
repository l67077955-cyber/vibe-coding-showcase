"""Question sets for each screen. Stable IDs are shared with the controller.

Every Box gets a companion `<name>_visible` Noul because a Box answer always
returns four edges, even when the target is absent.
"""
from __future__ import annotations

from typing import Any

SCREEN_CHOICES: dict[str, dict[str, str]] = {
    "lobby": {
        "lobby": "The main lobby/menu: mode tiles, a PLAY button, no live HUD.",
        "matchmaking": "A matchmaking/queue overlay with a cancel button and a searching message.",
        "in_match": "Live gameplay with health/shield bars, weapon slots and a minimap.",
        "other": "Loading screen, store, settings, error dialog, or anything else.",
    },
    "queue": {
        "matchmaking": "A matchmaking/queue overlay with a cancel button and a searching message.",
        "in_match": "Live gameplay with health/shield bars, weapon slots and a minimap.",
        "lobby": "The main lobby/menu with mode tiles and a PLAY button.",
        "other": "Loading screen, error dialog, or anything else.",
    },
    "ingame": {
        "in_match": "Live gameplay with health/shield bars, weapon slots and a minimap.",
        "eliminated": "The player is eliminated: a spectating view or an ELIMINATED banner, teammates may still be alive.",
        "results": "End-of-match results with placement, XP and a RETURN TO LOBBY button.",
        "esc_menu": "The pause/escape menu overlay with Leave Match, Settings, etc.",
        "other": "Loading screen, lobby, error dialog, or anything else.",
    },
    "explore": {
        "in_match": "Live gameplay with health/shield bars, weapon slots and a minimap.",
        "eliminated": "The player is eliminated: a spectating view or an ELIMINATED banner, teammates may still be alive.",
        "results": "End-of-match results with placement, XP and a RETURN TO LOBBY button.",
        "esc_menu": "The pause/escape menu overlay with Leave Match, Settings, etc.",
        "other": "Loading screen, lobby, error dialog, or anything else.",
    },
    "menu": {
        "esc_menu": "The pause/escape menu overlay with Leave Match, Settings, etc.",
        "results": "End-of-match results with placement, XP and a RETURN TO LOBBY button.",
        "lobby": "The main lobby/menu with mode tiles and a PLAY button.",
        "in_match": "Live gameplay with health/shield bars and a minimap.",
        "other": "Loading screen, confirmation dialog, error dialog, or anything else.",
    },
    "results": {
        "results": "End-of-match results with placement, XP and a RETURN TO LOBBY button.",
        "lobby": "The main lobby/menu with mode tiles and a PLAY button.",
        "in_match": "Live gameplay with health/shield bars and a minimap.",
        "other": "Loading screen, error dialog, or anything else.",
    },
}

_BOX_VISIBLE = "Is this control clearly visible and clickable in the screenshot?"


def _box(name: str, instructions: str) -> dict[str, Any]:
    return {
        f"{name}": {"type": "box", "instructions": instructions},
        f"{name}_visible": {"type": "noul", "instructions": _BOX_VISIBLE},
    }


def _screen(profile: str) -> dict[str, Any]:
    return {
        "screen": {
            "type": "choice",
            "instructions": (
                "Which Fortnite screen is this? Judge the whole screenshot, not a single label. "
                "A live match always has a health bar and weapon slots; the lobby has mode tiles "
                "and a large PLAY button; the pause menu is a dark overlay over the match."
            ),
            "criteria": SCREEN_CHOICES[profile],
        }
    }


def lobby_questions() -> dict[str, Any]:
    q = _screen("lobby")
    q.update(
        {
            "play_button": {
                "type": "box",
                "instructions": (
                    "the large yellow or orange PLAY button (Chinese: 开始) in the bottom-right "
                    "corner of the lobby"
                ),
            },
            "play_button_visible": {
                "type": "noul",
                "instructions": (
                    "Is a large yellow/orange PLAY button (开始) visible in the bottom-right "
                    "corner of the lobby?"
                ),
            },
            "zero_build_tile": {
                "type": "box",
                "instructions": (
                    "the ZERO BUILD game-mode tile (Chinese: 零建造) in the lobby mode list, "
                    "not the Battle Royale tile"
                ),
            },
            "zero_build_tile_visible": {
                "type": "noul",
                "instructions": "Is a ZERO BUILD (零建造) game-mode tile visible in the lobby?",
            },
            "squad_control": {
                "type": "box",
                "instructions": (
                    "the squad-size selector/button near the PLAY button that shows the current "
                    "team size (SQUADS / 小队, DUOS / 双人, TRIOS / 三人, SOLO / 单人)"
                ),
            },
            "squad_control_visible": {
                "type": "noul",
                "instructions": (
                    "Is a squad-size selector (showing SOLO, DUOS, TRIOS or SQUADS) visible "
                    "near the PLAY button?"
                ),
            },
            "squads_option": {
                "type": "box",
                "instructions": (
                    "the SQUADS / 小队 (4 players) option inside the open team-size dropdown menu"
                ),
            },
            "squads_option_visible": {
                "type": "noul",
                "instructions": (
                    "Is an open team-size dropdown menu visible with a SQUADS / 小队 option?"
                ),
            },
            "fill_toggle": {
                "type": "box",
                "instructions": (
                    "the FILL toggle, switch or checkbox that controls filling the squad with "
                    "random players (Chinese: 填充)"
                ),
            },
            "fill_toggle_visible": {
                "type": "noul",
                "instructions": (
                    "Is a FILL toggle/checkbox (填充) for random teammates visible in the lobby?"
                ),
            },
            "selected_mode": {
                "type": "choice",
                "instructions": (
                    "Which game mode is currently selected? Look at the highlighted mode tile, "
                    "or the mode name shown next to the PLAY button."
                ),
                "criteria": {
                    "zero_build": "ZERO BUILD (零建造) is the selected mode.",
                    "battle_royale": "Battle Royale with building (建造) is the selected mode.",
                    "reload": "Reload or another limited-time mode is selected.",
                    "other": "Some other mode is selected.",
                    "unclear": "The selected mode cannot be determined from this screenshot.",
                },
            },
            "squad_size": {
                "type": "choice",
                "instructions": (
                    "What team size is currently selected? Read the label near the PLAY button "
                    "or in the mode panel."
                ),
                "criteria": {
                    "squads": "SQUADS / 小队 (4 players).",
                    "trios": "TRIOS / 三人 (3 players).",
                    "duos": "DUOS / 双人 (2 players).",
                    "solo": "SOLO / 单人 (1 player).",
                    "unclear": "The team size cannot be determined from this screenshot.",
                },
            },
            "fill_state": {
                "type": "choice",
                "instructions": (
                    "Is the FILL option (random teammates / 填充) currently ON or OFF? "
                    "Look at the fill toggle's state."
                ),
                "criteria": {
                    "on": "FILL is enabled; random teammates will be matched.",
                    "off": "FILL is disabled; the player queues alone or with their party.",
                    "unclear": "The FILL state cannot be determined from this screenshot.",
                },
            },
        }
    )
    return q


def queue_questions() -> dict[str, Any]:
    q = _screen("queue")
    q.update(_box(
        "cancel_button",
        "the CANCEL matchmaking button (Chinese: 取消) shown while searching for a match",
    ))
    return q


def ingame_questions() -> dict[str, Any]:
    q = _screen("ingame")
    q.update(
        {
            "eliminated": {
                "type": "noul",
                "instructions": (
                    "Has the player been eliminated? There is an ELIMINATED / 已被淘汰 message, "
                    "a spectating camera, or a death screen instead of normal gameplay."
                ),
            },
            "return_lobby_button": {
                "type": "box",
                "instructions": (
                    "the RETURN TO LOBBY button (Chinese: 返回大厅) on the end-of-match results screen"
                ),
            },
            "return_lobby_button_visible": {
                "type": "noul",
                "instructions": "Is a RETURN TO LOBBY button (返回大厅) visible on screen?",
            },
        }
    )
    return q


def menu_questions() -> dict[str, Any]:
    q = _screen("menu")
    q.update(
        {
            "leave_button": {
                "type": "box",
                "instructions": (
                    "the LEAVE MATCH button (Chinese: 离开对局) inside the pause/escape menu, "
                    "not the Settings or Resume button"
                ),
            },
            "leave_button_visible": {
                "type": "noul",
                "instructions": "Is a LEAVE MATCH button (离开对局) visible in the pause menu?",
            },
            "confirm_button": {
                "type": "box",
                "instructions": (
                    "the confirm/yes button (YES / 确定 / 离开) in the 'leave this match?' "
                    "confirmation dialog"
                ),
            },
            "confirm_button_visible": {
                "type": "noul",
                "instructions": (
                    "Is a confirmation dialog asking whether to leave the match visible, with a "
                    "YES/确定/离开 button?"
                ),
            },
            "return_lobby_button": {
                "type": "box",
                "instructions": (
                    "the RETURN TO LOBBY button (Chinese: 返回大厅) on the end-of-match results screen"
                ),
            },
            "return_lobby_button_visible": {
                "type": "noul",
                "instructions": "Is a RETURN TO LOBBY button (返回大厅) visible on screen?",
            },
        }
    )
    return q


def results_questions() -> dict[str, Any]:
    q = _screen("results")
    q.update(_box(
        "return_lobby_button",
        "the RETURN TO LOBBY button (Chinese: 返回大厅) on the end-of-match results screen",
    ))
    q.update(_box(
        "play_again_button",
        "the PLAY AGAIN button (Chinese: 再来一局) on the end-of-match results screen",
    ))
    return q


def explore_questions() -> dict[str, Any]:
    """First-person gameplay: pick the next movement, spot chests, climb obstacles."""
    q = _screen("explore")
    q.update(
        {
            "move": {
                "type": "choice",
                "instructions": (
                    "You are the player in a first-person view. Decide the single best next "
                    "movement to explore the map, reach loot, and avoid getting stuck. "
                    "The player is at the bottom centre of the image. Prefer routes that make "
                    "progress and keep the player out of water, lava, cliffs and the storm."
                ),
                "criteria": {
                    "forward": "The path straight ahead is clear enough to walk forward.",
                    "forward_left": "Move diagonally forward-left to go around an obstacle or "
                                    "toward a target on the left.",
                    "forward_right": "Move diagonally forward-right to go around an obstacle or "
                                     "toward a target on the right.",
                    "left": "Strafe left because the way forward is blocked or the target is "
                            "directly to the left.",
                    "right": "Strafe right because the way forward is blocked or the target is "
                             "directly to the right.",
                    "backward": "Back up because the way ahead is a dead end, a cliff, water, "
                                "lava, or a wall too high to climb.",
                    "jump_forward": "A low wall, rock, fence, ledge or step directly ahead can "
                                    "be climbed by jumping while moving forward.",
                    "stop": "No safe movement is available; stand still and look around.",
                },
            },
            "action": {
                "type": "choice",
                "instructions": (
                    "You are the player in a first-person view. Choose the single operation the "
                    "player should perform now: move, jump, interact, attack, aim, reload, look, "
                    "or stop. Pick the operation that best reaches loot, explores the map and "
                    "avoids getting stuck. The player controls: W/A/S/D move, Space jumps, "
                    "E interacts, the LEFT mouse button fires the equipped weapon, the RIGHT "
                    "mouse button aims down sights, R reloads. If an enemy is visible and a "
                    "weapon is ready, shooting is usually the right answer."
                ),
                "criteria": {
                    "move_forward": "Walk straight ahead.",
                    "move_forward_left": "Walk diagonally forward-left.",
                    "move_forward_right": "Walk diagonally forward-right.",
                    "strafe_left": "Move sideways to the left without turning.",
                    "strafe_right": "Move sideways to the right without turning.",
                    "back_up": "Walk backwards to escape a wall, cliff or dead end.",
                    "jump_forward": "Jump while moving forward to climb a low wall, rock or step.",
                    "jump_in_place": "Jump straight up without moving forward.",
                    "interact": "Press the interact key (E) to open a chest, door, button or vehicle.",
                    "attack": "Press the left mouse button to attack or shoot.",
                    "aim": "Hold the right mouse button to aim.",
                    "reload": "Press R to reload.",
                    "look_left": "Turn the camera to the left to scan for loot or a route.",
                    "look_right": "Turn the camera to the right to scan for loot or a route.",
                    "stop": "No safe operation; stand still and scan.",
                },
            },
            "hold": {
                "type": "choice",
                "instructions": (
                    "How long should the chosen operation be held? Use tap for a single click, "
                    "short for a quick step, medium for a normal walk, and long for a committed "
                    "walk or a chest that needs a longer interact hold."
                ),
                "criteria": {
                    "tap": "A single tap/click, about 0.12 seconds.",
                    "short": "A short hold, about 0.35 seconds.",
                    "medium": "A medium hold, about 0.8 seconds.",
                    "long": "A long hold, about 1.6 seconds.",
                },
            },
            "repeat": {
                "type": "choice",
                "instructions": "How many times should the chosen operation be repeated?",
                "criteria": {
                    "once": "Perform it once.",
                    "twice": "Perform it twice.",
                    "three_times": "Perform it three times.",
                },
            },
            "target_visible": {
                "type": "noul",
                "instructions": (
                    "Is an interactive object visible: a loot chest, door, button, vehicle, "
                    "or a pickup worth walking to?"
                ),
            },
            "target": {
                "type": "box",
                "instructions": "the nearest interactive object (chest, door, button, vehicle or loot)",
            },
            "target_kind": {
                "type": "choice",
                "instructions": "What kind of interactive object is the nearest target?",
                "criteria": {
                    "chest": "A loot chest.",
                    "door": "A door or gate.",
                    "button": "A switch, button or lever.",
                    "vehicle": "A car, boat, plane or other vehicle.",
                    "loot": "A floor pickup, weapon or item.",
                    "other": "Another interactive object.",
                    "none": "No interactive object is visible.",
                    "unclear": "An object is visible but its kind cannot be determined.",
                },
            },
            "target_distance": {
                "type": "choice",
                "instructions": (
                    "How close is the nearest interactive object? Judge its size in the "
                    "first-person view."
                ),
                "criteria": {
                    "near": "Within a few steps; the player can interact now.",
                    "far": "Visible but still some distance away; walk toward it first.",
                    "unclear": "No object is visible or the distance cannot be judged.",
                },
            },
            "interact_ready": {
                "type": "noul",
                "instructions": (
                    "Is the player close enough and facing the interactive object so that "
                    "pressing interact now would use it?"
                ),
            },
            "path": {
                "type": "choice",
                "instructions": (
                    "What is directly ahead of the player within a few steps? Judge the terrain "
                    "and solid objects, not the distant background."
                ),
                "criteria": {
                    "clear": "The path ahead is walkable and clear.",
                    "low": "A low wall, rock, fence, step or ledge can be climbed by jumping.",
                    "high_wall": "A wall, tree, rock or barrier too high to jump; detour around it.",
                    "hazard": "A cliff, deep water, lava, storm wall or other dangerous drop.",
                    "unclear": "The path ahead cannot be determined.",
                },
            },
            "chest_visible": {
                "type": "noul",
                "instructions": (
                    "Is a loot chest visible? In Fortnite a chest is a golden or wooden box "
                    "with a glowing outline, usually on the floor or on a platform. Do not count "
                    "ammo boxes, backpacks or ordinary crates."
                ),
                "criteria": {
                    "true": "At least one loot chest is clearly visible.",
                    "false": "No loot chest is visible.",
                },
            },
            "chest": {
                "type": "box",
                "instructions": "the nearest loot chest in the image",
            },
            "chest_distance": {
                "type": "choice",
                "instructions": (
                    "How close is the nearest visible loot chest to the player? Judge its size "
                    "and position in the first-person view."
                ),
                "criteria": {
                    "near": "The chest is within a few steps and large in the frame; the player "
                            "can open it now by holding the interact key.",
                    "far": "The chest is visible but still some distance away; walk toward it first.",
                    "unclear": "No chest is visible or the distance cannot be judged.",
                },
            },
            "obstacle_ahead": {
                "type": "noul",
                "instructions": (
                    "Is a wall, rock, tree trunk, fence, ledge or other solid obstacle directly "
                    "in front of the player, blocking a straight walk forward?"
                ),
            },
            "hazard_ahead": {
                "type": "noul",
                "instructions": (
                    "Is there a dangerous drop, cliff edge, deep water, lava, or the storm wall "
                    "directly ahead within a few steps?"
                ),
            },
            "eliminated": {
                "type": "noul",
                "instructions": (
                    "Has the player been eliminated? There is an ELIMINATED / 已被淘汰 message, "
                    "a spectating camera, or a death screen instead of normal gameplay."
                ),
            },
            "look_around": {
                "type": "noul",
                "instructions": (
                    "Would turning the camera left or right help find loot or a way forward, "
                    "because the current view is a wall, empty sky, or a dead end?"
                ),
            },
            "enemy": {
                "type": "box",
                "instructions": (
                    "The nearest visible enemy player. Tight box around their body."
                ),
            },
            "enemy_visible": {
                "type": "noul",
                "instructions": (
                    "Is an enemy player visible in the image? Teammates do not count. "
                    "Look for a hostile character, name plate, or muzzle flash."
                ),
            },
            "weapon_ready": {
                "type": "noul",
                "instructions": (
                    "Is a weapon equipped and ready to fire? The weapon slot and ammo "
                    "counter are visible at the bottom right of the screen."
                ),
            },
        }
    )
    return q


PROFILES = {
    "lobby": lobby_questions,
    "queue": queue_questions,
    "ingame": ingame_questions,
    "menu": menu_questions,
    "results": results_questions,
    "explore": explore_questions,
    "explore_fast": None,  # filled in below
}

# The latencies that matter are output tokens: every question the model must
# answer is generated one token at a time. `explore` carries legacy chest/scan
# questions that the v2 planner no longer reads, so the in-match loop can drop
# them and pay roughly half the generation cost.
FAST_EXPLORE_KEYS = (
    # `screen` stays: the controller uses it to notice a return to the lobby or
    # the results screen. Everything below is what plan_explore() reads.
    "screen", "action", "hold", "repeat",
    "target_visible", "target", "target_kind", "target_distance",
    "interact_ready", "path", "obstacle_ahead", "hazard_ahead",
    "enemy", "enemy_visible", "weapon_ready",
)


def explore_fast_questions() -> dict[str, Any]:
    """The subset of `explore` that `plan_explore` actually consumes."""
    q = explore_questions()
    return {key: q[key] for key in FAST_EXPLORE_KEYS if key in q}


PROFILES["explore_fast"] = explore_fast_questions


def questions_for(profile: str) -> dict[str, Any]:
    try:
        return PROFILES[profile]()
    except KeyError as exc:
        raise ValueError(f"unknown screen profile: {profile}") from exc
