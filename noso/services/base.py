"""Base class for UPnP services.

A service declares its identity + URL scheme as class attributes (which must
match what ``device_description.xml`` advertises), registers action handlers in
:meth:`register`, and optionally exposes evented state for GENA.
"""

from __future__ import annotations

from typing import Callable

from ..context import ServerContext
from ..soap import UPnPError

Handler = Callable[[dict], dict]


class Service:
    # Overridden per subclass.
    service_type: str = ""
    service_id: str = ""
    scpd_asset: str = ""  # filename under assets/scpd/
    scpd_path: str = ""  # SCPDURL
    control_path: str = ""  # controlURL
    event_path: str = ""  # eventSubURL
    device: str = "root"  # root | MS | MR (which device node hosts it)
    # action name -> (in_arg_names, out_arg_names); drives generated SCPD so
    # controllers can discover each action's arguments.
    ACTIONS: dict[str, tuple[list[str], list[str]]] = {}

    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self.handlers: dict[str, Handler] = {}
        self.register()

    def register(self) -> None:
        """Subclasses populate ``self.handlers`` (action name -> callable)."""

    def handle(self, action: str, args: dict) -> dict:
        fn = self.handlers.get(action)
        if fn is None:
            raise UPnPError(401, f"Invalid Action: {action}")
        return fn(args) or {}

    def event_state(self) -> dict[str, str]:
        """Evented variables -> current value for the initial GENA NOTIFY.

        Services using the Sonos ``LastChange`` pattern return
        ``{"LastChange": "<escaped event doc>"}``; ZoneGroupTopology returns
        ``{"ZoneGroupState": "<doc>"}``. Empty means "no eventing".
        """
        return {}
