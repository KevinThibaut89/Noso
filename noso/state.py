"""Mutable per-zone state that isn't owned by the audio backend.

Volume/mute/transport live in the :class:`~noso.audio.base.AudioPlayer` (the
mixer is the source of truth there). This holds the rest: the room name (which
a controller can change via ``DeviceProperties.SetZoneAttributes``), the play
mode, and the currently-loaded URI + its DIDL-Lite metadata.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ZoneState:
    room_name: str
    icon: str = "x-rincon-roomicon:living"
    play_mode: str = "NORMAL"  # NORMAL | REPEAT_ALL | SHUFFLE | SHUFFLE_NOREPEAT ...
    current_uri: str = ""
    current_uri_metadata: str = ""
