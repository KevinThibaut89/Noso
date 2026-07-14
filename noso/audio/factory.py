"""Pick the best available audio backend at runtime."""

from __future__ import annotations

import logging

from .base import AudioPlayer
from .null import NullPlayer

log = logging.getLogger("noso.audio")

_AUTO_ORDER = ["gstreamer", "mpv", "ffmpeg", "null"]


def _construct(name: str, sink: str | None) -> AudioPlayer:
    if name == "gstreamer":
        from .gstreamer import GstPlayer

        return GstPlayer(sink=sink)
    if name == "mpv":
        from .mpv import MpvPlayer

        return MpvPlayer()
    if name == "ffmpeg":
        from .subprocess_player import SubprocessPlayer

        return SubprocessPlayer()
    return NullPlayer()


def make_player(backend: str = "auto", sink: str | None = None) -> AudioPlayer:
    """Return a started :class:`AudioPlayer` for ``backend`` (or best available).

    A specific backend that fails to construct falls back to null with a
    warning; ``auto`` tries gstreamer -> mpv -> ffmpeg -> null in order.
    """
    order = _AUTO_ORDER if backend == "auto" else [backend]
    for name in order:
        try:
            player = _construct(name, sink)
            player.start()
            if not isinstance(player, NullPlayer):
                log.info("audio backend: %s", player.name)
            return player
        except Exception as exc:  # noqa: BLE001 - any import/init failure -> next
            log.info("audio backend %r unavailable: %s", name, exc)
    log.warning("no real audio backend available; using NullPlayer (no sound)")
    player = NullPlayer()
    player.start()
    return player
