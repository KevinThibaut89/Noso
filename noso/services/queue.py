"""Queue — minimal implementation so queue-based playback doesn't fault."""

from __future__ import annotations

from .base import Service
from .contentdirectory import EMPTY_DIDL


class QueueService(Service):
    service_type = "urn:schemas-sonos-com:service:Queue:1"
    service_id = "urn:sonos-com:serviceId:Queue"
    scpd_asset = "Queue1.xml"
    scpd_path = "/xml/Queue1.xml"
    control_path = "/MediaRenderer/Queue/Control"
    event_path = "/MediaRenderer/Queue/Event"
    device = "MR"

    ACTIONS = {
        "AddURI": (
            ["QueueID", "UpdateID", "EnqueuedURI", "EnqueuedURIMetaData",
             "DesiredFirstTrackNumberEnqueued", "EnqueueAsNext"],
            ["FirstTrackNumberEnqueued", "NewQueueLength", "NewUpdateID"],
        ),
        "AddMultipleURIs": (
            ["QueueID", "UpdateID", "ContainerURI", "ContainerMetaData", "DesiredFirstTrackNumberEnqueued",
             "EnqueueAsNext", "NumberOfURIs", "EnqueuedURIsAndMetaData"],
            ["FirstTrackNumberEnqueued", "NumTracksAdded", "NewQueueLength", "NewUpdateID"],
        ),
        "RemoveAllTracks": (["QueueID", "UpdateID"], ["NewUpdateID"]),
        "Browse": (
            ["QueueID", "StartingIndex", "RequestedCount"],
            ["Result", "NumberReturned", "TotalMatches", "UpdateID"],
        ),
    }

    def register(self) -> None:
        self.handlers = {
            "AddURI": self._add_uri,
            "AddMultipleURIs": self._add_multiple,
            "RemoveAllTracks": lambda a: {},
            "Browse": self._browse,
        }

    def _add_uri(self, args: dict) -> dict:
        return {"FirstTrackNumberEnqueued": "1", "NewQueueLength": "1", "NewUpdateID": "1"}

    def _add_multiple(self, args: dict) -> dict:
        return {"FirstTrackNumberEnqueued": "1", "NumTracksAdded": "1", "NewQueueLength": "1", "NewUpdateID": "1"}

    def _browse(self, args: dict) -> dict:
        return {"Result": EMPTY_DIDL, "NumberReturned": "0", "TotalMatches": "0", "UpdateID": "1"}
