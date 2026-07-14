"""RenderingControl — volume and mute (plus tone-control stubs)."""

from __future__ import annotations

from ..soap import UPnPError
from ..xmlutil import attr_escape
from .base import Service


class RenderingControlService(Service):
    service_type = "urn:schemas-upnp-org:service:RenderingControl:1"
    service_id = "urn:upnp-org:serviceId:RenderingControl"
    scpd_asset = "RenderingControl1.xml"
    scpd_path = "/xml/RenderingControl1.xml"
    control_path = "/MediaRenderer/RenderingControl/Control"
    event_path = "/MediaRenderer/RenderingControl/Event"
    device = "MR"

    ACTIONS = {
        "GetVolume": (["InstanceID", "Channel"], ["CurrentVolume"]),
        "SetVolume": (["InstanceID", "Channel", "DesiredVolume"], []),
        "GetMute": (["InstanceID", "Channel"], ["CurrentMute"]),
        "SetMute": (["InstanceID", "Channel", "DesiredMute"], []),
        "GetBass": (["InstanceID"], ["CurrentBass"]),
        "SetBass": (["InstanceID", "DesiredBass"], []),
        "GetTreble": (["InstanceID"], ["CurrentTreble"]),
        "SetTreble": (["InstanceID", "DesiredTreble"], []),
        "GetLoudness": (["InstanceID", "Channel"], ["CurrentLoudness"]),
        "SetLoudness": (["InstanceID", "Channel", "DesiredLoudness"], []),
    }

    def register(self) -> None:
        self.handlers = {
            "GetVolume": self._get_volume,
            "SetVolume": self._set_volume,
            "GetMute": self._get_mute,
            "SetMute": self._set_mute,
            "GetBass": lambda a: {"CurrentBass": "0"},
            "GetTreble": lambda a: {"CurrentTreble": "0"},
            "SetBass": lambda a: {},
            "SetTreble": lambda a: {},
            "GetLoudness": lambda a: {"CurrentLoudness": "1"},
            "SetLoudness": lambda a: {},
        }

    @property
    def _player(self):
        return self.ctx.player

    def _notify(self) -> None:
        if self.ctx.gena:
            self.ctx.gena.notify(self)

    def _get_volume(self, args: dict) -> dict:
        return {"CurrentVolume": str(self._player.get_volume())}

    def _set_volume(self, args: dict) -> dict:
        try:
            volume = int(args.get("DesiredVolume", "0"))
        except ValueError as exc:
            raise UPnPError(600, "Argument Value Invalid") from exc
        self._player.set_volume(volume)
        self._notify()
        return {}

    def _get_mute(self, args: dict) -> dict:
        return {"CurrentMute": "1" if self._player.get_mute() else "0"}

    def _set_mute(self, args: dict) -> dict:
        self._player.set_mute(args.get("DesiredMute", "0") in ("1", "true", "True"))
        self._notify()
        return {}

    def event_state(self) -> dict[str, str]:
        volume = self._player.get_volume()
        mute = "1" if self._player.get_mute() else "0"
        inner = (
            f'<Volume channel="Master" val="{volume}"/>'
            f'<Mute channel="Master" val="{mute}"/>'
        )
        event = (
            '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/">'
            f'<InstanceID val="0">{inner}</InstanceID></Event>'
        )
        return {"LastChange": event}
