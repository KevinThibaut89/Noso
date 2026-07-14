"""Subprocess audio backend using ``ffplay`` or the ``mpv`` CLI.

Last-resort backend for boxes that have an ffmpeg/mpv binary but no Python
bindings. Playback is real; pause/resume use SIGSTOP/SIGCONT. Volume is applied
at launch — live volume changes are stored and take effect on the next track
(documented limitation of this fallback).
"""

from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import threading

from .base import AudioPlayer, TransportState

log = logging.getLogger("noso.audio.subprocess")


def _find_binary() -> tuple[str, str] | None:
    if shutil.which("ffplay"):
        return ("ffplay", "ffplay")
    if shutil.which("mpv"):
        return ("mpv", "mpv")
    return None


class SubprocessPlayer(AudioPlayer):
    def __init__(self) -> None:
        super().__init__()
        found = _find_binary()
        if found is None:
            raise RuntimeError("no ffplay or mpv binary found")
        self._kind, self._bin = found
        self._proc: subprocess.Popen | None = None
        self._monitor: threading.Thread | None = None
        self._state = TransportState.NO_MEDIA
        self._uri = ""
        self._volume = 25
        self._mute = False

    def close(self) -> None:
        self._kill()

    def _command(self) -> list[str]:
        vol = 0 if self._mute else self._volume
        if self._kind == "ffplay":
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                    "-volume", str(vol), self._uri]
        return ["mpv", "--no-video", "--really-quiet", f"--volume={vol}", self._uri]

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                self._proc.kill()
        self._proc = None

    def _launch(self) -> None:
        self._kill()
        self._proc = subprocess.Popen(
            self._command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        proc = self._proc
        self._monitor = threading.Thread(target=self._wait, args=(proc,), daemon=True)
        self._monitor.start()

    def _wait(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        # Only a natural exit (autoexit at EOF) counts as end-of-stream.
        if proc is self._proc and code == 0:
            self._set_state(TransportState.STOPPED)
            self._emit_eos()

    def set_uri(self, uri: str, metadata: str = "") -> None:
        self._kill()
        self._uri = uri
        self._set_state(TransportState.STOPPED if uri else TransportState.NO_MEDIA)

    def play(self) -> None:
        if self._proc and self._proc.poll() is None and self._state == TransportState.PAUSED:
            self._proc.send_signal(signal.SIGCONT)
        elif self._uri:
            self._launch()
        self._set_state(TransportState.PLAYING)

    def pause(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.send_signal(signal.SIGSTOP)
            self._set_state(TransportState.PAUSED)

    def stop(self) -> None:
        self._kill()
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

    def _set_state(self, state: TransportState) -> None:
        if state != self._state:
            self._state = state
            self._emit_state(state)
