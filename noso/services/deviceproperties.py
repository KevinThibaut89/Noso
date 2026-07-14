"""DeviceProperties — identity + room naming."""

from __future__ import annotations

from .base import Service

ZGT_TYPE = "urn:schemas-upnp-org:service:ZoneGroupTopology:1"


class DevicePropertiesService(Service):
    service_type = "urn:schemas-upnp-org:service:DeviceProperties:1"
    service_id = "urn:upnp-org:serviceId:DeviceProperties"
    scpd_asset = "DeviceProperties1.xml"
    scpd_path = "/xml/DeviceProperties1.xml"
    control_path = "/DeviceProperties/Control"
    event_path = "/DeviceProperties/Event"
    device = "root"

    ACTIONS = {
        "GetZoneInfo": (
            [],
            ["SerialNumber", "SoftwareVersion", "DisplaySoftwareVersion", "HardwareVersion",
             "IPAddress", "MACAddress", "CopyrightInfo", "ExtraInfo", "HTAudioIn", "Flags"],
        ),
        "GetZoneAttributes": ([], ["CurrentZoneName", "CurrentIcon", "CurrentConfiguration"]),
        "SetZoneAttributes": (["DesiredZoneName", "DesiredIcon", "DesiredConfiguration"], []),
        "GetHouseholdID": ([], ["CurrentHouseholdID"]),
        "GetLEDState": ([], ["CurrentLEDState"]),
        "SetLEDState": (["DesiredLEDState"], []),
        "GetButtonLockState": ([], ["CurrentButtonLockState"]),
        "SetButtonLockState": (["DesiredButtonLockState"], []),
    }

    def register(self) -> None:
        self.handlers = {
            "GetZoneInfo": self._get_zone_info,
            "GetZoneAttributes": self._get_zone_attributes,
            "SetZoneAttributes": self._set_zone_attributes,
            "GetHouseholdID": self._get_household,
            "GetLEDState": lambda a: {"CurrentLEDState": "On"},
            "SetLEDState": lambda a: {},
            "GetButtonLockState": lambda a: {"CurrentButtonLockState": "Off"},
            "SetButtonLockState": lambda a: {},
        }

    def _get_zone_info(self, args: dict) -> dict:
        ident = self.ctx.identity
        cfg = self.ctx.config
        return {
            "SerialNumber": ident.serial,
            "SoftwareVersion": cfg.software_version,
            "DisplaySoftwareVersion": cfg.software_version.split("-")[0],
            "HardwareVersion": "1.20.1.6-1.1",
            "IPAddress": self.ctx.ip,
            "MACAddress": ident.mac,
            "CopyrightInfo": "© 2004-2024 Sonos, Inc. All Rights Reserved.",
            "ExtraInfo": "",
            "HTAudioIn": "0",
            "Flags": "0",
        }

    def _get_zone_attributes(self, args: dict) -> dict:
        st = self.ctx.state
        return {
            "CurrentZoneName": st.room_name,
            "CurrentIcon": st.icon,
            "CurrentConfiguration": "1",
        }

    def _set_zone_attributes(self, args: dict) -> dict:
        if "DesiredZoneName" in args and args["DesiredZoneName"]:
            self.ctx.state.room_name = args["DesiredZoneName"]
        if args.get("DesiredIcon"):
            self.ctx.state.icon = args["DesiredIcon"]
        # A room rename must be reflected in the topology the app renders.
        zgt = self.ctx.services.get(ZGT_TYPE)
        if zgt and self.ctx.gena:
            self.ctx.gena.notify(zgt)
        return {}

    def _get_household(self, args: dict) -> dict:
        return {"CurrentHouseholdID": self.ctx.identity.household}
