"""GStreamer ``playbin`` audio backend (the preferred one).

Decodes essentially anything the installed GStreamer plugins support (MP3, AAC,
FLAC, ALAC, WAV, OGG, HLS, Shoutcast/Icecast) and routes to PipeWire/Pulse/ALSA
via ``autoaudiosink``. Runs a GLib main loop in a dedicated thread; bus
messages there are turned into transport-state callbacks.
"""

from __future__ import annotations

import logging
import threading

from .base import AudioPlayer, TransportState, format_hms  # noqa: F401

log = logging.getLogger("noso.audio.gst")


class GstPlayer(AudioPlayer):
    def __init__(self, sink: str | None = None) -> None:
        super().__init__()
        import gi  # imported lazily so the factory can fall back if absent

        gi.require_version("Gst", "1.0")
        from gi.repository import GLib, Gst  # type: ignore

        self._gst = Gst
        self._glib = GLib
        Gst.init(None)

        self._playbin = Gst.ElementFactory.make("playbin", "noso-playbin")
        if self._playbin is None:
            raise RuntimeError("GStreamer 'playbin' element unavailable")
        if sink:
            audio_sink = Gst.parse_bin_from_description(sink, True)
            self._playbin.set_property("audio-sink", audio_sink)

        self._state = TransportState.NO_MEDIA
        self._volume = 25
        self._mute = False
        self._playbin.set_property("volume", self._volume / 100.0)

        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_message)

        self._loop = GLib.MainLoop()
        self._thread = threading.Thread(target=self._loop.run, name="noso-gst", daemon=True)

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        try:
            self._playbin.set_state(self._gst.State.NULL)
            self._loop.quit()
        except Exception:  # noqa: BLE001
            pass

    # -- transport ---------------------------------------------------------
    def set_uri(self, uri: str, metadata: str = "") -> None:
        self._playbin.set_state(self._gst.State.NULL)
        self._playbin.set_property("uri", uri)
        self._set_state(TransportState.STOPPED if uri else TransportState.NO_MEDIA)

    def play(self) -> None:
        self._playbin.set_state(self._gst.State.PLAYING)
        self._set_state(TransportState.PLAYING)

    def pause(self) -> None:
        self._playbin.set_state(self._gst.State.PAUSED)
        self._set_state(TransportState.PAUSED)

    def stop(self) -> None:
        self._playbin.set_state(self._gst.State.NULL)
        self._set_state(TransportState.STOPPED)

    def seek(self, seconds: float) -> None:
        self._playbin.seek_simple(
            self._gst.Format.TIME,
            self._gst.SeekFlags.FLUSH | self._gst.SeekFlags.KEY_UNIT,
            int(seconds * self._gst.SECOND),
        )

    def get_state(self) -> TransportState:
        return self._state

    def get_position(self) -> tuple[float, float]:
        ok_d, duration = self._playbin.query_duration(self._gst.Format.TIME)
        ok_p, position = self._playbin.query_position(self._gst.Format.TIME)
        secs = self._gst.SECOND
        return (duration / secs if ok_d else 0.0, position / secs if ok_p else 0.0)

    # -- mixer -------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._playbin.set_property("volume", self._volume / 100.0)

    def get_volume(self) -> int:
        return self._volume

    def set_mute(self, mute: bool) -> None:
        self._mute = bool(mute)
        self._playbin.set_property("mute", self._mute)

    def get_mute(self) -> bool:
        return self._mute

    # -- internals ---------------------------------------------------------
    def _set_state(self, state: TransportState) -> None:
        if state != self._state:
            self._state = state
            self._emit_state(state)

    def _on_message(self, bus, message) -> None:
        mtype = message.type
        if mtype == self._gst.MessageType.EOS:
            self._set_state(TransportState.STOPPED)
            self._emit_eos()
        elif mtype == self._gst.MessageType.ERROR:
            err, _ = message.parse_error()
            log.warning("gstreamer error: %s", err)
            self._set_state(TransportState.STOPPED)
