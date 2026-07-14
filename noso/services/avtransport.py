"""AVTransport — transport control (load URI, play/pause/stop/seek)."""

from __future__ import annotations

from ..audio.base import format_hms, parse_hms
from ..soap import UPnPError
from ..xmlutil import attr_escape
from .base import Service


def _var(name: str, val: str, **extra: str) -> str:
    attrs = "".join(f' {k}="{attr_escape(v)}"' for k, v in extra.items())
    return f'<{name}{attrs} val="{attr_escape(val)}"/>'


class AVTransportService(Service):
    service_type = "urn:schemas-upnp-org:service:AVTransport:1"
    service_id = "urn:upnp-org:serviceId:AVTransport"
    scpd_asset = "AVTransport1.xml"
    scpd_path = "/xml/AVTransport1.xml"
    control_path = "/MediaRenderer/AVTransport/Control"
    event_path = "/MediaRenderer/AVTransport/Event"
    device = "MR"

    ACTIONS = {
        "SetAVTransportURI": (["InstanceID", "CurrentURI", "CurrentURIMetaData"], []),
        "GetTransportInfo": (
            ["InstanceID"],
            ["CurrentTransportState", "CurrentTransportStatus", "CurrentSpeed"],
        ),
        "GetPositionInfo": (
            ["InstanceID"],
            ["Track", "TrackDuration", "TrackMetaData", "TrackURI", "RelTime",
             "AbsTime", "RelCount", "AbsCount"],
        ),
        "GetMediaInfo": (
            ["InstanceID"],
            ["NrTracks", "MediaDuration", "CurrentURI", "CurrentURIMetaData", "NextURI",
             "NextURIMetaData", "PlayMedium", "RecordMedium", "WriteStatus"],
        ),
        "GetTransportSettings": (["InstanceID"], ["PlayMode", "RecQualityMode"]),
        "GetDeviceCapabilities": (["InstanceID"], ["PlayMedia", "RecMedia", "RecQualityModes"]),
        "Play": (["InstanceID", "Speed"], []),
        "Pause": (["InstanceID"], []),
        "Stop": (["InstanceID"], []),
        "Seek": (["InstanceID", "Unit", "Target"], []),
        "Next": (["InstanceID"], []),
        "Previous": (["InstanceID"], []),
        "SetPlayMode": (["InstanceID", "NewPlayMode"], []),
    }

    def register(self) -> None:
        self.handlers = {
            "SetAVTransportURI": self._set_uri,
            "GetTransportInfo": self._get_transport_info,
            "GetPositionInfo": self._get_position_info,
            "GetMediaInfo": self._get_media_info,
            "GetTransportSettings": self._get_transport_settings,
            "GetDeviceCapabilities": self._get_device_caps,
            "Play": self._play,
            "Pause": self._pause,
            "Stop": self._stop,
            "Seek": self._seek,
            "Next": lambda a: self._transition(),
            "Previous": lambda a: self._transition(),
            "SetPlayMode": self._set_play_mode,
        }

    @property
    def _player(self):
        return self.ctx.player

    def _notify(self) -> None:
        if self.ctx.gena:
            self.ctx.gena.notify(self)

    # -- actions -----------------------------------------------------------
    def _set_uri(self, args: dict) -> dict:
        uri = args.get("CurrentURI", "")
        metadata = args.get("CurrentURIMetaData", "")
        self.ctx.state.current_uri = uri
        self.ctx.state.current_uri_metadata = metadata
        self._player.set_uri(uri, metadata)
        self._notify()
        return {}

    def _play(self, args: dict) -> dict:
        self._player.play()
        self._notify()
        return {}

    def _pause(self, args: dict) -> dict:
        self._player.pause()
        self._notify()
        return {}

    def _stop(self, args: dict) -> dict:
        self._player.stop()
        self._notify()
        return {}

    def _seek(self, args: dict) -> dict:
        unit = args.get("Unit", "REL_TIME")
        target = args.get("Target", "")
        if unit in ("REL_TIME", "ABS_TIME"):
            self._player.seek(parse_hms(target))
        self._notify()
        return {}

    def _transition(self) -> dict:
        # Single-track player: Next/Previous have nowhere to go.
        return {}

    def _set_play_mode(self, args: dict) -> dict:
        self.ctx.state.play_mode = args.get("NewPlayMode", "NORMAL")
        self._notify()
        return {}

    def _get_transport_info(self, args: dict) -> dict:
        return {
            "CurrentTransportState": self._player.get_state().value,
            "CurrentTransportStatus": "OK",
            "CurrentSpeed": "1",
        }

    def _get_position_info(self, args: dict) -> dict:
        duration, position = self._player.get_position()
        st = self.ctx.state
        return {
            "Track": "1",
            "TrackDuration": format_hms(duration),
            "TrackMetaData": st.current_uri_metadata,
            "TrackURI": st.current_uri,
            "RelTime": format_hms(position),
            "AbsTime": format_hms(position),
            "RelCount": "2147483647",
            "AbsCount": "2147483647",
        }

    def _get_media_info(self, args: dict) -> dict:
        st = self.ctx.state
        duration, _ = self._player.get_position()
        return {
            "NrTracks": "1" if st.current_uri else "0",
            "MediaDuration": format_hms(duration),
            "CurrentURI": st.current_uri,
            "CurrentURIMetaData": st.current_uri_metadata,
            "NextURI": "",
            "NextURIMetaData": "",
            "PlayMedium": "NETWORK",
            "RecordMedium": "NOT_IMPLEMENTED",
            "WriteStatus": "NOT_IMPLEMENTED",
        }

    def _get_transport_settings(self, args: dict) -> dict:
        return {"PlayMode": self.ctx.state.play_mode, "RecQualityMode": "NOT_IMPLEMENTED"}

    def _get_device_caps(self, args: dict) -> dict:
        return {
            "PlayMedia": "NONE, NETWORK",
            "RecMedia": "NOT_IMPLEMENTED",
            "RecQualityModes": "NOT_IMPLEMENTED",
        }

    # -- eventing (LastChange) --------------------------------------------
    def event_state(self) -> dict[str, str]:
        st = self.ctx.state
        inner = "".join(
            [
                _var("TransportState", self._player.get_state().value),
                _var("CurrentPlayMode", st.play_mode),
                _var("CurrentTrackURI", st.current_uri),
                _var("CurrentTrackMetaData", st.current_uri_metadata),
                _var("NumberOfTracks", "1" if st.current_uri else "0"),
                _var("CurrentTrack", "1"),
                _var("CurrentTransportActions", "Play,Stop,Pause,Seek,Next,Previous"),
            ]
        )
        event = (
            '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/" '
            'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/">'
            f'<InstanceID val="0">{inner}</InstanceID></Event>'
        )
        return {"LastChange": event}
