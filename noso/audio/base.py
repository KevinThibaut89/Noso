"""Audio backend abstraction.

Sonos playback is a *pull* model: a controller calls
``AVTransport.SetAVTransportURI`` with a URL and then ``Play``; the speaker
itself HTTP-GETs the URL and renders it. An :class:`AudioPlayer` therefore owns
transport state, position, and the volume/mute mixer, and reports asynchronous
changes (state transitions, end-of-stream) back through callbacks so the SOAP
and GENA layers can update and emit events.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import Callable, Optional


class TransportState(str, enum.Enum):
    """UPnP AVTransport ``TransportState`` values Sonos uses."""

    STOPPED = "STOPPED"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED_PLAYBACK"
    TRANSITIONING = "TRANSITIONING"
    NO_MEDIA = "NO_MEDIA_PRESENT"


def format_hms(seconds: float) -> str:
    """Format seconds as ``H:MM:SS`` (the AVTransport time format)."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def parse_hms(value: str) -> float:
    """Parse ``H:MM:SS`` (or ``MM:SS``) into seconds; 0 on garbage."""
    try:
        parts = [float(p) for p in value.strip().split(":")]
    except (ValueError, AttributeError):
        return 0.0
    total = 0.0
    for part in parts:
        total = total * 60 + part
    return total


StateCallback = Callable[[TransportState], None]
EosCallback = Callable[[], None]


class AudioPlayer(ABC):
    """Abstract, thread-safe-ish audio backend.

    Backends may run their own thread (a GLib loop, an mpv event thread, a
    subprocess monitor). They must call :meth:`_emit_state` / :meth:`_emit_eos`
    when things change; the application wires those to marshal onto the asyncio
    loop, so backend threads never touch loop state directly.
    """

    def __init__(self) -> None:
        self._on_state: Optional[StateCallback] = None
        self._on_eos: Optional[EosCallback] = None

    # -- wiring ------------------------------------------------------------
    def set_callbacks(
        self, on_state: Optional[StateCallback] = None, on_eos: Optional[EosCallback] = None
    ) -> None:
        self._on_state = on_state
        self._on_eos = on_eos

    def _emit_state(self, state: TransportState) -> None:
        if self._on_state is not None:
            self._on_state(state)

    def _emit_eos(self) -> None:
        if self._on_eos is not None:
            self._on_eos()

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Start any background thread/loop. Default: nothing to do."""

    def close(self) -> None:
        """Release resources. Default: nothing to do."""

    @property
    def name(self) -> str:
        return type(self).__name__

    # -- transport ---------------------------------------------------------
    @abstractmethod
    def set_uri(self, uri: str, metadata: str = "") -> None:
        """Load a URI (does not necessarily start playback)."""

    @abstractmethod
    def play(self) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def seek(self, seconds: float) -> None:
        """Seek within the current stream. Default: unsupported / ignored."""

    @abstractmethod
    def get_state(self) -> TransportState: ...

    def get_position(self) -> tuple[float, float]:
        """Return ``(duration_seconds, position_seconds)``; 0/0 if unknown."""
        return (0.0, 0.0)

    # -- rendering (mixer) -------------------------------------------------
    @abstractmethod
    def set_volume(self, volume: int) -> None:
        """Set volume, 0-100."""

    @abstractmethod
    def get_volume(self) -> int: ...

    @abstractmethod
    def set_mute(self, mute: bool) -> None: ...

    @abstractmethod
    def get_mute(self) -> bool: ...
