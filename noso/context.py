"""Server context — the single object wired through every layer.

Holds config, identity, the resolved advertised IP, the zone state, the audio
player, and (once started) the GENA manager. Passing one context object avoids
global state and makes the whole stack trivial to construct in a test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # avoid import cycles at runtime
    from .audio.base import AudioPlayer
    from .config import Config
    from .identity import Identity
    from .state import ZoneState


class ServerContext:
    def __init__(
        self,
        config: "Config",
        identity: "Identity",
        ip: str,
        state: "ZoneState",
        player: "AudioPlayer",
    ) -> None:
        self.config = config
        self.identity = identity
        self.ip = ip
        self.state = state
        self.player = player
        # Filled in as the server starts up.
        self.gena: Optional[Any] = None
        self.loop: Optional[Any] = None
        self.services: dict[str, Any] = {}  # service_type -> Service

    # -- URLs --------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return f"http://{self.ip}:{self.config.http_port}"

    @property
    def description_url(self) -> str:
        return f"{self.base_url}/xml/device_description.xml"
