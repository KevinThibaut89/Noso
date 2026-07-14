"""mpv audio backend (via libmpv / python-mpv).

A good pure-python option when GStreamer isn't installed: libmpv handles the
same broad format set and gives live volume, mute, seek, and end-of-file
notification.
"""

from __future__ import annotations

import logging

from .base import AudioPlayer, TransportState

log = logging.getLogger("noso.audio.mpv")


class MpvPlayer(AudioPlayer):
    def __init__(self) -> None:
        super().__init__()
        import mpv  # lazy import so the factory can fall back if absent

        self._mpv = mpv.MPV(video=False, ytdl=False, audio_display=False)
        self._state = TransportState.NO_MEDIA
        self._volume = 25
        self._mute = False
        self._mpv.volume = self._volume

        @self._mpv.property_observer("eof-reached")
        def _on_eof(_name, value):  # pragma: no cover - callback
            if value:
                self._set_state(TransportState.STOPPED)
                self._emit_eos()

    def close(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:  # noqa: BLE001
            pass

    def set_uri(self, uri: str, metadata: str = "") -> None:
        self._uri = uri
        if uri:
            self._mpv.play(uri)
            self._mpv.pause = True
            self._set_state(TransportState.STOPPED)
        else:
            self._set_state(TransportState.NO_MEDIA)

    def play(self) -> None:
        self._mpv.pause = False
        self._set_state(TransportState.PLAYING)

    def pause(self) -> None:
        self._mpv.pause = True
        self._set_state(TransportState.PAUSED)

    def stop(self) -> None:
        try:
            self._mpv.command("stop")
        except Exception:  # noqa: BLE001
            pass
        self._set_state(TransportState.STOPPED)

    def seek(self, seconds: float) -> None:
        try:
            self._mpv.seek(seconds, reference="absolute")
        except Exception:  # noqa: BLE001
            pass

    def get_state(self) -> TransportState:
        return self._state

    def get_position(self) -> tuple[float, float]:
        return (float(self._mpv.duration or 0.0), float(self._mpv.time_pos or 0.0))

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._mpv.volume = self._volume

    def get_volume(self) -> int:
        return self._volume

    def set_mute(self, mute: bool) -> None:
        self._mute = bool(mute)
        self._mpv.mute = self._mute

    def get_mute(self) -> bool:
        return self._mute

    def _set_state(self, state: TransportState) -> None:
        if state != self._state:
            self._state = state
            self._emit_state(state)
