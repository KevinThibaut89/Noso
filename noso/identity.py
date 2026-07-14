"""Stable, Sonos-shaped device identity.

A real Sonos player is identified everywhere by a ``RINCON_<mac>01400`` token
derived from its MAC address. Controllers key on this UID, so it must stay
stable across restarts — we persist the random part to a small JSON file and
only ever bump ``boot_seq``.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

# Sonos' registered MAC OUI (Organizationally Unique Identifier). Using it
# makes the generated MAC/serial look like genuine Sonos hardware.
SONOS_OUI = "00:0E:58"
_OUI_HEX = SONOS_OUI.replace(":", "")  # "000E58"


@dataclass(frozen=True)
class Identity:
    """Immutable identity derived from a random 3-byte node id."""

    node: str  # 6 uppercase hex chars — the random tail after the Sonos OUI
    household: str  # stable household token (Sonos_XXXX...)
    boot_seq: int  # bumped every process start; feeds SSDP BOOTID + ZoneGroup

    # --- MAC / serial -----------------------------------------------------
    @property
    def mac_hex(self) -> str:
        """12 hex chars, no separators, e.g. ``000E58A1B2C3``."""
        return _OUI_HEX + self.node

    @property
    def mac(self) -> str:
        """Colon MAC, e.g. ``00:0E:58:A1:B2:C3``."""
        h = self.mac_hex
        return ":".join(h[i : i + 2] for i in range(0, 12, 2))

    @property
    def serial(self) -> str:
        """Sonos serial format, e.g. ``00-0E-58-A1-B2-C3:E``."""
        h = self.mac_hex
        return "-".join(h[i : i + 2] for i in range(0, 12, 2)) + ":E"

    # --- UDNs -------------------------------------------------------------
    @property
    def rincon(self) -> str:
        """Bare RINCON id (no ``uuid:`` prefix); used inside ZoneGroupState."""
        return f"RINCON_{self.mac_hex}01400"

    @property
    def uuid(self) -> str:
        """Root ZonePlayer UDN, e.g. ``uuid:RINCON_000E58A1B2C301400``."""
        return f"uuid:{self.rincon}"

    @property
    def uuid_ms(self) -> str:
        """Embedded MediaServer UDN (root UDN + ``_MS``)."""
        return f"{self.uuid}_MS"

    @property
    def uuid_mr(self) -> str:
        """Embedded MediaRenderer UDN (root UDN + ``_MR``)."""
        return f"{self.uuid}_MR"


def _new_node() -> str:
    return secrets.token_hex(3).upper()  # 3 bytes -> 6 uppercase hex chars


def _new_household() -> str:
    return "Sonos_" + secrets.token_hex(16)


def load_or_create(path: Path) -> Identity:
    """Load persisted identity from ``path`` (JSON), creating it if absent.

    Always bumps and re-persists ``boot_seq`` so each start advertises a
    higher BootSeq — real speakers do this and some controllers use it to
    detect a reboot.
    """
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            data = {}

    node = str(data.get("node") or _new_node()).upper()
    household = str(data.get("household") or _new_household())
    boot_seq = int(data.get("boot_seq", 0)) + 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"node": node, "household": household, "boot_seq": boot_seq}, indent=2)
    )
    return Identity(node=node, household=household, boot_seq=boot_seq)
