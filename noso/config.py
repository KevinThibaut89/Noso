"""Runtime configuration.

Precedence (low to high): dataclass defaults -> optional TOML file -> ``NOSO_*``
environment variables -> explicit overrides (CLI flags, wired up in
``__main__``). TOML is read with the standard-library ``tomllib`` (Python
3.11+); no third-party config library is required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

try:  # Python 3.11+ standard library
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older interpreters
    tomllib = None  # type: ignore[assignment]

_INT_FIELDS = {"http_port", "ssdp_port", "ssdp_ttl", "announce_interval"}
_PATH_FIELDS = {"state_dir"}
_BOOL_FIELDS = {"mdns_enabled"}
_TRUE = {"1", "true", "yes", "on"}


def _default_state_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "noso"
    return Path.home() / ".local" / "share" / "noso"


@dataclass
class Config:
    """All tunables for one emulated ZonePlayer."""

    room_name: str = "Noso"
    # Identity presented in device_description.xml + ZoneGroupState + /info.
    # Defaults mimic a current-firmware Sonos Connect (ZP90) — a line-out network
    # receiver, which is what Noso is. The version fields MUST be S2-current or
    # the app classifies the device as S1 and demands a system update. Values
    # captured from a real S2 household (app 17.2.6). Override to match a model
    # you actually own for the best chance of the app accepting it.
    model_name: str = "Sonos Connect"
    model_number: str = "ZP90"
    software_version: str = "86.8-78270"
    display_version: str = "17.2.6"  # marketing version the app shows
    hardware_version: str = "1.17.5.5-2.0"
    min_compatible_version: str = "85.0-00000"
    legacy_compatible_version: str = "58.0-00000"
    # Modern-app identity fields, all captured from a real S2 Connect. The Sonos
    # app derives model/Series-ID/OS-generation from these *local* fields:
    #   series_id     -> Series ID shown in the app ("C100" = Connect family)
    #   api_version   -> flips the device S1 -> S2 (with the <versions> block in
    #                    device.py); mirrored into GetZoneInfo + /info
    #   extra_version -> the "OTP: ..." string GetZoneInfo/ExtraInfo returns
    # Recapture from a unit you own for an exact match:
    #   curl -s http://<speaker-ip>:1400/xml/device_description.xml
    series_id: str = "C100"
    api_version: str = "1.53.1"
    min_api_version: str = "1.1.0"
    extra_version: str = "OTP: 1.1.1(1-17-5-zp90-2.1)"
    variant: str = "0"
    zone_type: str = "1"  # real Connect reports 1 (a line-out ZonePlayer)
    icon: str = "x-rincon-roomicon:living"

    interface_ip: Optional[str] = None  # LAN IP to advertise (autodetect if None)
    bind_ip: str = "0.0.0.0"  # HTTP listen + SSDP multicast membership
    http_port: int = 1400
    ssdp_port: int = 1900
    ssdp_ttl: int = 4
    announce_interval: int = 600  # seconds between ssdp:alive re-announcements

    audio_backend: str = "auto"  # auto | gstreamer | mpv | ffmpeg | null
    audio_sink: Optional[str] = None  # GStreamer sink override, e.g. "alsasink"

    # mDNS/Bonjour advertisement — REQUIRED for the modern Sonos app to discover
    # the device (it dropped SSDP for local discovery). Advertises _sonos._tcp.
    mdns_enabled: bool = True
    mdns_backend: str = "auto"  # auto | zeroconf | avahi | none
    # Household id to advertise (mDNS `hhid`, ZoneGroupState, /info). Set this to
    # your real household's id to look like a member of the existing household;
    # otherwise a stable generated one is used.
    household: Optional[str] = None
    protovers: str = "1.29.2"  # advertised Sonos protocol version (mDNS `protovers`)

    state_dir: Path = field(default_factory=_default_state_dir)
    log_level: str = "INFO"

    @property
    def identity_path(self) -> Path:
        return self.state_dir / "identity.json"

    # -- construction ------------------------------------------------------
    @classmethod
    def build(cls, config_file: Optional[str | Path] = None, **overrides: Any) -> "Config":
        values: dict[str, Any] = {}
        if config_file:
            values.update(_read_toml(Path(config_file)))
        values.update(_read_env())
        # Explicit overrides win, but ignore Nones so "flag not passed" != "unset".
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**_coerce(values))


def server_string(cfg: Config) -> str:
    """The Sonos-style ``SERVER`` header, e.g.
    ``Linux UPnP/1.0 Sonos/56.0-76060 (ZPS3)``. Controllers regex-match the
    ``Sonos`` token to confirm a device is a Sonos.
    """
    return f"Linux UPnP/1.0 Sonos/{cfg.software_version} (ZP{cfg.model_number})"


def _known_fields() -> set[str]:
    return {f.name for f in fields(Config)}


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    # Accept either a flat table or a [noso] section.
    if "noso" in data and isinstance(data["noso"], dict):
        data = data["noso"]
    return {k: v for k, v in data.items() if k in _known_fields()}


def _read_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in _known_fields():
        env_key = "NOSO_" + name.upper()
        if env_key in os.environ:
            out[name] = os.environ[env_key]
    return out


def _coerce(values: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key not in _known_fields():
            continue
        if value is None:
            out[key] = None
        elif key in _INT_FIELDS:
            out[key] = int(value)
        elif key in _BOOL_FIELDS:
            out[key] = value if isinstance(value, bool) else str(value).lower() in _TRUE
        elif key in _PATH_FIELDS:
            out[key] = Path(value).expanduser()
        else:
            out[key] = value
    return out
