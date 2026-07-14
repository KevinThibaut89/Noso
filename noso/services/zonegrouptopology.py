"""ZoneGroupTopology — the service that makes Noso appear as a room."""

from __future__ import annotations

from ..zonegroup import build_zone_group_state
from .base import Service


class ZoneGroupTopologyService(Service):
    service_type = "urn:schemas-upnp-org:service:ZoneGroupTopology:1"
    service_id = "urn:upnp-org:serviceId:ZoneGroupTopology"
    scpd_asset = "ZoneGroupTopology1.xml"
    scpd_path = "/xml/ZoneGroupTopology1.xml"
    control_path = "/ZoneGroupTopology/Control"
    event_path = "/ZoneGroupTopology/Event"
    device = "root"

    ACTIONS = {
        "GetZoneGroupAttributes": (
            [],
            [
                "CurrentZoneGroupName",
                "CurrentZoneGroupID",
                "CurrentZonePlayerUUIDsInGroup",
                "CurrentMuseHouseholdId",
            ],
        ),
        "GetZoneGroupState": ([], ["ZoneGroupState"]),
        "RegisterMobileDevice": (["MobileDeviceName", "MobileDeviceUDN", "MobileIPAndPort"], []),
        "ReportUnresponsiveDevice": (["DeviceUUID", "DesiredAction"], []),
        "CheckForUpdate": (["UpdateType", "CachedOnly", "Version"], ["UpdateItem"]),
    }

    def register(self) -> None:
        self.handlers = {
            "GetZoneGroupState": self._get_state,
            "GetZoneGroupAttributes": self._get_attributes,
            # Accepted no-ops so a controller's housekeeping calls don't fault.
            "RegisterMobileDevice": lambda a: {},
            "ReportUnresponsiveDevice": lambda a: {},
            "CheckForUpdate": lambda a: {"UpdateItem": ""},
        }

    def _get_state(self, args: dict) -> dict:
        return {"ZoneGroupState": build_zone_group_state(self.ctx)}

    def _get_attributes(self, args: dict) -> dict:
        ident = self.ctx.identity
        return {
            "CurrentZoneGroupName": self.ctx.state.room_name,
            "CurrentZoneGroupID": f"{ident.rincon}:0",
            "CurrentZonePlayerUUIDsInGroup": ident.rincon,
            "CurrentMuseHouseholdId": ident.household,
        }

    def event_state(self) -> dict[str, str]:
        # ZoneGroupTopology events the whole ZoneGroupState document.
        return {"ZoneGroupState": build_zone_group_state(self.ctx)}
