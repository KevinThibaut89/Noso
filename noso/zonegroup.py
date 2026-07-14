"""Build the ``ZoneGroupState`` document.

This is the single most important payload in the whole project: the controller
(and the app) call ``ZoneGroupTopology.GetZoneGroupState`` and render the
returned document as the list of rooms. The ``ZoneName`` attribute becomes the
room label; ``Location`` points back at our device description.

We advertise a single group containing a single member (ourself, as the
coordinator). The wide attribute set mirrors modern firmware and is cheap
insurance against a strict parser dropping the zone.
"""

from __future__ import annotations

from .context import ServerContext
from .xmlutil import attrs


def member_attributes(ctx: ServerContext) -> dict[str, object]:
    ident = ctx.identity
    cfg = ctx.config
    location = f"{ctx.base_url}/xml/device_description.xml"
    return {
        "UUID": ident.rincon,
        "Location": location,
        "ZoneName": ctx.state.room_name,
        "Icon": ctx.state.icon,
        "Configuration": "1",
        "SoftwareVersion": cfg.software_version,
        "SWGen": "2",
        "MinCompatibleVersion": cfg.min_compatible_version,
        "LegacyCompatibleVersion": cfg.legacy_compatible_version,
        "BootSeq": ident.boot_seq,
        "TVConfigurationError": "0",
        "HdmiCecAvailable": "0",
        "WirelessMode": "0",
        "WirelessLeafOnly": "0",
        "ChannelFreq": "2412",
        "BehindWifiExtender": "0",
        "WifiEnabled": "1",
        "EthLink": "1",
        "Orientation": "0",
        "RoomCalibrationState": "4",
        "SecureRegState": "3",
        "VoiceConfigState": "0",
        "MicEnabled": "0",
        "AirPlayEnabled": "0",
        "IdleState": "1",
        "MoreInfo": "",
        "SSLPort": "1443",
        "HHSSLPort": "1443",
        "Invisible": "0",
    }


def build_zone_group_state(ctx: ServerContext) -> str:
    """Return the raw (unescaped) ``ZoneGroupState`` XML document."""
    ident = ctx.identity
    member = f"<ZoneGroupMember {attrs(member_attributes(ctx))}/>"
    group = (
        f'<ZoneGroup Coordinator="{ident.rincon}" ID="{ident.rincon}:0">'
        f"{member}</ZoneGroup>"
    )
    return f"<ZoneGroupState><ZoneGroups>{group}</ZoneGroups><VanishedDevices/></ZoneGroupState>"
