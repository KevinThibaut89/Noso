"""ContentDirectory — minimal Browse returning valid (empty) DIDL-Lite.

Enough to keep a controller's "now playing" / library views from erroring; we
don't expose a real music library.
"""

from __future__ import annotations

from .base import Service

EMPTY_DIDL = (
    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
    'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
    'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>'
)


class ContentDirectoryService(Service):
    service_type = "urn:schemas-upnp-org:service:ContentDirectory:1"
    service_id = "urn:upnp-org:serviceId:ContentDirectory"
    scpd_asset = "ContentDirectory1.xml"
    scpd_path = "/xml/ContentDirectory1.xml"
    control_path = "/MediaServer/ContentDirectory/Control"
    event_path = "/MediaServer/ContentDirectory/Event"
    device = "MS"

    ACTIONS = {
        "Browse": (
            ["ObjectID", "BrowseFlag", "Filter", "StartingIndex", "RequestedCount", "SortCriteria"],
            ["Result", "NumberReturned", "TotalMatches", "UpdateID"],
        ),
        "GetSystemUpdateID": ([], ["Id"]),
        "GetSearchCapabilities": ([], ["SearchCaps"]),
        "GetSortCapabilities": ([], ["SortCaps"]),
    }

    def register(self) -> None:
        self.handlers = {
            "Browse": self._browse,
            "GetSystemUpdateID": lambda a: {"Id": "1"},
            "GetSearchCapabilities": lambda a: {"SearchCaps": ""},
            "GetSortCapabilities": lambda a: {"SortCaps": ""},
        }

    def _browse(self, args: dict) -> dict:
        return {
            "Result": EMPTY_DIDL,
            "NumberReturned": "0",
            "TotalMatches": "0",
            "UpdateID": "1",
        }
