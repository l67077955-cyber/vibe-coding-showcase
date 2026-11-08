"""Vision backend: bind screen profiles to the Jev client."""
from __future__ import annotations

import logging

from .capture import Frame
from .config import Config
from .jev import JevClient, Observation
from .screens import questions_for

log = logging.getLogger(__name__)


class JevVision:
    def __init__(self, cfg: Config, client: JevClient) -> None:
        self.cfg = cfg
        self.client = client

    def observe(self, profile: str, frame: Frame) -> Observation:
        questions = questions_for(profile)
        return self.client.ask(
            frame,
            questions,
            context=f"The script expects this to be the '{profile}' screen, but verify from the image.",
        )

    def close(self) -> None:
        self.client.close()

    @property
    def calls(self) -> int:
        return self.client.calls

    @property
    def total_cost(self) -> float:
        return self.client.total_cost
