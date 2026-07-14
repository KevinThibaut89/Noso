"""No-op audio backend.

Tracks transport/volume/mute state faithfully but produces no sound. Used when
no real backend is available (e.g. a headless CI box) so the full UPnP/GENA
stack still runs and can be exercised by a controller.
"""

from __future__ import annotations

import logging

from .base import AudioPlayer, TransportState

log = logging.getLogger("noso.audio.null")


class NullPlayer(AudioPlayer):
    def __init__(self) -> None:
        super().__init__()
        self._state = TransportState.NO_MEDIA
        self._uri = ""
        self._metadata = ""
        self._volume = 25
        self._mute = False

    def _set_state(self, state: TransportState) -> None:
        if state != self._state:
            self._state = state
            self._emit_state(state)

    def set_uri(self, uri: str, metadata: str = "") -> None:
        self._uri = uri
        self._metadata = metadata
        log.info("set_uri %s", uri)
        self._set_state(TransportState.STOPPED if uri else TransportState.NO_MEDIA)

    def play(self) -> None:
        if self._uri:
            self._set_state(TransportState.PLAYING)

    def pause(self) -> None:
        if self._state == TransportState.PLAYING:
            self._set_state(TransportState.PAUSED)

    def stop(self) -> None:
        self._set_state(TransportState.STOPPED if self._uri else TransportState.NO_MEDIA)

    def get_state(self) -> TransportState:
        return self._state

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))

    def get_volume(self) -> int:
        return self._volume

    def set_mute(self, mute: bool) -> None:
        self._mute = bool(mute)

    def get_mute(self) -> bool:
        return self._mute
