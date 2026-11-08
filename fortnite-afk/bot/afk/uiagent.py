"""Generic "get me into a match" UI agent.

Hardcoded coordinates break the moment the UI changes (and it changed: the
lobby now routes through island pages). Instead of teaching the bot every
screen, ask the model one question per frame:

    what kind of screen is this, which button advances us toward a match,
    and where is that button?

The code only clicks the box the model points at. The loop stops when the
model says the screen is live gameplay.
"""
from __future__ import annotations

from typing import Any

UI_START_QUESTIONS: dict[str, Any] = {    "screen": {
        "type": "choice",
        "instructions": (
            "What screen is this? Judge from the whole image, including any "
            "browser or streaming chrome around the game."
        ),
        "criteria": {
            "lobby": "The main Fortnite lobby with a big PLAY button.",
            "island": "An island/map details page with SELECT, or a mode selection page.",
            "map_ready": "A page where a START / PLAY / DEPLOY button would launch the match.",
            "queue": "A matchmaking screen with a searching message or a cancel button.",
            "match": "Live gameplay: a HUD, a weapon, a minimap, the player's character in the world.",
            "other": "Loading, settings, store, error, desktop, or anything else.",
        },
    },
    "target_action": {
        "type": "choice",
        "instructions": (
            "Which single action moves us closest to being inside a match right now? "
            "Prefer the button that starts or confirms the game, not menus that go sideways."
        ),
        "criteria": {
            "play": "Click the big PLAY button in the lobby.",
            "select": "Click SELECT to choose the highlighted island or mode.",
            "start": "Click START / PLAY / DEPLOY to launch the chosen game.",
            "back": "Click BACK / close to leave a menu that does not lead to a match.",
            "wait": "Do nothing; the screen is loading or matchmaking.",
            "none": "No useful button is visible.",
        },
    },
    "target_button": {
        "type": "box",
        "instructions": (
            "The exact button to click for the chosen action. Tight box around the "
            "button's visible face, not the whole panel."
        ),
    },
    "target_button_visible": {
        "type": "noul",
        "instructions": "Is that button actually visible and clickable right now?",
    },
}

DROP_QUESTIONS: dict[str, Any] = {
    "phase": {
        "type": "choice",
        "instructions": (
            "Which phase of the drop is the player in? Look at the whole screen: "
            "the battle bus, free-fall, a glider, or standing on the ground."
        ),
        "criteria": {
            "bus": "On the battle bus / flying vehicle with a JUMP prompt and a minimap of the island.",
            "skydive": "Free-falling: the camera is high above the ground, no glider.",
            "glide": "Gliding down: a glider or parachute is visible.",
            "ground": "Standing on the ground: terrain at eye level, weapons visible.",
            "other": "Loading, lobby, death screen, or anything else.",
        },
    },
    "drop_now": {
        "type": "noul",
        "instructions": (
            "Is this a good moment to jump? The island should be close ahead or below, "
            "not still tiny on the horizon."
        ),
    },
    "landing_area": {
        "type": "box",
        "instructions": "A clear patch of ground ahead/below to steer toward.",
    },
    "landing_area_visible": {
        "type": "noul",
        "instructions": "Is a clear landing area visible?",
    },
}
