"""Stub services.

These are advertised by a real ZonePlayer and referenced by controllers, but
Noso only needs them to answer housekeeping calls plausibly. Each implements
the handful of actions a controller actually invokes and returns benign values.
"""

from __future__ import annotations

from .base import Service

# Formats we claim to accept as a rendering sink (advertised via ConnectionManager).
_SINK_PROTOCOLS = ",".join(
    f"http-get:*:audio/{fmt}:*"
    for fmt in ("mpeg", "mp4", "aac", "x-flac", "flac", "wav", "x-wav", "ogg", "x-ms-wma")
)


class ConnectionManagerService(Service):
    service_type = "urn:schemas-upnp-org:service:ConnectionManager:1"
    service_id = "urn:upnp-org:serviceId:ConnectionManager"
    scpd_asset = "ConnectionManager1.xml"

    ACTIONS = {
        "GetProtocolInfo": ([], ["Source", "Sink"]),
        "GetCurrentConnectionIDs": ([], ["ConnectionIDs"]),
        "GetCurrentConnectionInfo": (
            ["ConnectionID"],
            ["RcsID", "AVTransportID", "ProtocolInfo", "PeerConnectionManager",
             "PeerConnectionID", "Direction", "Status"],
        ),
    }

    def register(self) -> None:
        self.handlers = {
            "GetProtocolInfo": lambda a: {"Source": "", "Sink": _SINK_PROTOCOLS},
            "GetCurrentConnectionIDs": lambda a: {"ConnectionIDs": "0"},
            "GetCurrentConnectionInfo": lambda a: {
                "RcsID": "0",
                "AVTransportID": "0",
                "ProtocolInfo": "",
                "PeerConnectionManager": "",
                "PeerConnectionID": "-1",
                "Direction": "Input",
                "Status": "OK",
            },
        }


class ConnectionManagerMR(ConnectionManagerService):
    scpd_path = "/xml/ConnectionManager1.xml"
    control_path = "/MediaRenderer/ConnectionManager/Control"
    event_path = "/MediaRenderer/ConnectionManager/Event"
    device = "MR"


class ConnectionManagerMS(ConnectionManagerService):
    scpd_path = "/xml/MSConnectionManager1.xml"
    control_path = "/MediaServer/ConnectionManager/Control"
    event_path = "/MediaServer/ConnectionManager/Event"
    device = "MS"


class GroupRenderingControlService(Service):
    service_type = "urn:schemas-upnp-org:service:GroupRenderingControl:1"
    service_id = "urn:upnp-org:serviceId:GroupRenderingControl"
    scpd_asset = "GroupRenderingControl1.xml"
    scpd_path = "/xml/GroupRenderingControl1.xml"
    control_path = "/MediaRenderer/GroupRenderingControl/Control"
    event_path = "/MediaRenderer/GroupRenderingControl/Event"
    device = "MR"

    ACTIONS = {
        "GetGroupVolume": (["InstanceID"], ["CurrentVolume"]),
        "SetGroupVolume": (["InstanceID", "DesiredVolume"], []),
        "GetGroupMute": (["InstanceID"], ["CurrentMute"]),
        "SetGroupMute": (["InstanceID", "DesiredMute"], []),
        "SnapshotGroupVolume": (["InstanceID"], []),
    }

    def register(self) -> None:
        self.handlers = {
            "GetGroupVolume": lambda a: {"CurrentVolume": str(self.ctx.player.get_volume())},
            "SetGroupVolume": self._set_group_volume,
            "GetGroupMute": lambda a: {"CurrentMute": "1" if self.ctx.player.get_mute() else "0"},
            "SetGroupMute": self._set_group_mute,
            "SnapshotGroupVolume": lambda a: {},
        }

    def _set_group_volume(self, args: dict) -> dict:
        try:
            self.ctx.player.set_volume(int(args.get("DesiredVolume", "0")))
        except ValueError:
            pass
        return {}

    def _set_group_mute(self, args: dict) -> dict:
        self.ctx.player.set_mute(args.get("DesiredMute", "0") in ("1", "true", "True"))
        return {}


class AlarmClockService(Service):
    service_type = "urn:schemas-upnp-org:service:AlarmClock:1"
    service_id = "urn:upnp-org:serviceId:AlarmClock"
    scpd_asset = "AlarmClock1.xml"
    scpd_path = "/xml/AlarmClock1.xml"
    control_path = "/AlarmClock/Control"
    event_path = "/AlarmClock/Event"
    device = "root"

    ACTIONS = {
        "ListAlarms": ([], ["CurrentAlarmList", "CurrentAlarmListVersion"]),
        "GetTimeZone": ([], ["Index", "AutoAdjustDst"]),
        "GetTimeZoneRule": (["Index"], ["TimeZone", "AutoAdjustDst"]),
        "GetTimeZoneAndRule": ([], ["Index", "AutoAdjustDst", "CurrentTimeZone"]),
        "GetFormat": ([], ["CurrentTimeFormat", "CurrentDateFormat"]),
        "GetHouseholdTimeAtStamp": (["TimeStamp"], ["HouseholdUTCTime"]),
    }

    def register(self) -> None:
        self.handlers = {
            "ListAlarms": lambda a: {
                "CurrentAlarmList": "",
                "CurrentAlarmListVersion": f"{self.ctx.identity.rincon}:0",
            },
            "GetTimeZone": lambda a: {"Index": "0", "AutoAdjustDst": "1"},
            "GetTimeZoneRule": lambda a: {"TimeZone": "", "AutoAdjustDst": "1"},
            "GetTimeZoneAndRule": lambda a: {"Index": "0", "AutoAdjustDst": "1", "CurrentTimeZone": ""},
            "GetFormat": lambda a: {"CurrentTimeFormat": "INV", "CurrentDateFormat": "INV"},
            "GetHouseholdTimeAtStamp": lambda a: {"HouseholdUTCTime": ""},
        }


class MusicServicesService(Service):
    service_type = "urn:schemas-upnp-org:service:MusicServices:1"
    service_id = "urn:upnp-org:serviceId:MusicServices"
    scpd_asset = "MusicServices1.xml"
    scpd_path = "/xml/MusicServices1.xml"
    control_path = "/MusicServices/Control"
    event_path = "/MusicServices/Event"
    device = "root"

    ACTIONS = {
        "ListAvailableServices": (
            [],
            ["AvailableServiceDescriptorList", "AvailableServiceTypeList",
             "AvailableServiceListVersion"],
        ),
        "GetSessionId": (["ServiceId", "Username"], ["SessionId"]),
        "UpdateAvailableServices": ([], []),
    }

    def register(self) -> None:
        self.handlers = {
            "ListAvailableServices": lambda a: {
                "AvailableServiceDescriptorList": "",
                "AvailableServiceTypeList": "",
                "AvailableServiceListVersion": f"{self.ctx.identity.rincon}:0",
            },
            "GetSessionId": lambda a: {"SessionId": ""},
            "UpdateAvailableServices": lambda a: {},
        }


class SystemPropertiesService(Service):
    service_type = "urn:schemas-upnp-org:service:SystemProperties:1"
    service_id = "urn:upnp-org:serviceId:SystemProperties"
    scpd_asset = "SystemProperties1.xml"
    scpd_path = "/xml/SystemProperties1.xml"
    control_path = "/SystemProperties/Control"
    event_path = "/SystemProperties/Event"
    device = "root"

    ACTIONS = {
        "GetString": (["VariableName"], ["StringValue"]),
        "SetString": (["VariableName", "StringValue"], []),
        "GetWebCode": (["AccountType"], ["WebCode"]),
        "ProvisionCredentialedTrialAccountX": (
            ["AccountType", "AccountID", "AccountPassword"],
            ["IsExpired", "AccountUDN"],
        ),
        "GetHouseholdID": ([], ["CurrentHouseholdID"]),
    }

    def register(self) -> None:
        self.handlers = {
            "GetString": lambda a: {"StringValue": ""},
            "SetString": lambda a: {},
            "GetWebCode": lambda a: {"WebCode": ""},
            "ProvisionCredentialedTrialAccountX": lambda a: {"IsExpired": "0", "AccountUDN": ""},
            "GetHouseholdID": lambda a: {"CurrentHouseholdID": self.ctx.identity.household},
        }


class GroupManagementService(Service):
    service_type = "urn:schemas-upnp-org:service:GroupManagement:1"
    service_id = "urn:upnp-org:serviceId:GroupManagement"
    scpd_asset = "GroupManagement1.xml"
    scpd_path = "/xml/GroupManagement1.xml"
    control_path = "/GroupManagement/Control"
    event_path = "/GroupManagement/Event"
    device = "root"

    ACTIONS = {
        "AddMember": (["MemberID", "BootSeq"], ["CurrentTransportSettings", "CurrentURI", "GroupUUIDJoined"]),
        "RemoveMember": (["MemberID"], []),
        "ReportTrackBufferingResult": (["MemberID", "ResultCode"], []),
    }

    def register(self) -> None:
        self.handlers = {
            "AddMember": lambda a: {"CurrentTransportSettings": "", "CurrentURI": "", "GroupUUIDJoined": ""},
            "RemoveMember": lambda a: {},
            "ReportTrackBufferingResult": lambda a: {},
        }


# --- services advertised by a real ZonePlayer that Noso only needs to present
# plausibly (rarely called by the app during discovery). SCPDs are served
# verbatim from the captured assets; handlers are permissive no-ops.


class AudioInService(Service):
    service_type = "urn:schemas-upnp-org:service:AudioIn:1"
    service_id = "urn:upnp-org:serviceId:AudioIn"
    scpd_asset = "AudioIn1.xml"
    scpd_path = "/xml/AudioIn1.xml"
    control_path = "/AudioIn/Control"
    event_path = "/AudioIn/Event"
    device = "root"
    permissive = True

    def register(self) -> None:
        self.handlers = {
            "GetAudioInputAttributes": lambda a: {"CurrentName": "", "CurrentIcon": ""},
            "GetLineInLevel": lambda a: {"CurrentLeftLineInLevel": "0", "CurrentRightLineInLevel": "0"},
        }


class QPlayService(Service):
    service_type = "urn:schemas-tencent-com:service:QPlay:1"
    service_id = "urn:tencent-com:serviceId:QPlay"
    scpd_asset = "QPlay1.xml"
    scpd_path = "/xml/QPlay1.xml"
    control_path = "/QPlay/Control"
    event_path = "/QPlay/Event"
    device = "MR"
    permissive = True

    def register(self) -> None:
        self.handlers = {"QPlayAuth": lambda a: {"Code": "", "MID": "", "DID": ""}}


class VirtualLineInService(Service):
    service_type = "urn:schemas-upnp-org:service:VirtualLineIn:1"
    service_id = "urn:upnp-org:serviceId:VirtualLineIn"
    scpd_asset = "VirtualLineIn1.xml"
    scpd_path = "/xml/VirtualLineIn1.xml"
    control_path = "/MediaRenderer/VirtualLineIn/Control"
    event_path = "/MediaRenderer/VirtualLineIn/Event"
    device = "MR"
    permissive = True

    def register(self) -> None:
        self.handlers = {}
