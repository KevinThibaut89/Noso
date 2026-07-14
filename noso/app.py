"""Application wiring and lifecycle.

Builds the :class:`ServerContext`, instantiates the service set, bridges the
audio backend's (threaded) state callbacks onto the asyncio loop as GENA
notifications, and starts/stops the SSDP + HTTP + eventing subsystems.
"""

from __future__ import annotations

import asyncio
import logging

from .audio.factory import make_player
from .config import Config
from .context import ServerContext
from .gena import GenaManager
from .httpd import HttpServer
from .identity import load_or_create
from .netutil import primary_ip
from .services.avtransport import AVTransportService
from .services.contentdirectory import ContentDirectoryService
from .services.deviceproperties import DevicePropertiesService
from .services.queue import QueueService
from .services.renderingcontrol import RenderingControlService
from .services.stubs import (
    AlarmClockService,
    ConnectionManagerMR,
    ConnectionManagerMS,
    GroupManagementService,
    GroupRenderingControlService,
    MusicServicesService,
    SystemPropertiesService,
)
from .services.zonegrouptopology import ZoneGroupTopologyService
from .ssdp import SsdpServer
from .state import ZoneState

log = logging.getLogger("noso.app")

AVT_TYPE = "urn:schemas-upnp-org:service:AVTransport:1"

# Order mirrors a real ZonePlayer's device_description.xml (root, then MS, MR).
_SERVICE_CLASSES = [
    AlarmClockService,
    MusicServicesService,
    DevicePropertiesService,
    SystemPropertiesService,
    ZoneGroupTopologyService,
    GroupManagementService,
    ContentDirectoryService,
    ConnectionManagerMS,
    RenderingControlService,
    ConnectionManagerMR,
    AVTransportService,
    QueueService,
    GroupRenderingControlService,
]


class NosoApp:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.ctx: ServerContext | None = None
        self.services: list = []
        self.http: HttpServer | None = None
        self.ssdp: SsdpServer | None = None

    def build(self) -> ServerContext:
        cfg = self.config
        identity = load_or_create(cfg.identity_path)
        ip = primary_ip(cfg.interface_ip)
        state = ZoneState(room_name=cfg.room_name, icon=cfg.icon)
        player = make_player(cfg.audio_backend, cfg.audio_sink)

        ctx = ServerContext(config=cfg, identity=identity, ip=ip, state=state, player=player)
        self.services = [cls(ctx) for cls in _SERVICE_CLASSES]
        # Keyed by type for notify-by-type lookups (ConnectionManager appears
        # twice with one type; only its representative is stored, which is fine
        # because it is never the target of a notify).
        ctx.services = {s.service_type: s for s in self.services}
        self.ctx = ctx
        return ctx

    async def start(self) -> None:
        ctx = self.build()
        loop = asyncio.get_running_loop()
        ctx.loop = loop

        ctx.gena = GenaManager(ctx)
        ctx.gena.start()
        self._wire_player_events(ctx, loop)

        self.http = HttpServer(ctx, self.services)
        await self.http.start()
        # SSDP needs multicast; if the environment can't provide it (some
        # containers, restrictive VLANs) keep serving so control-by-IP and
        # already-known controllers still work.
        self.ssdp = SsdpServer(ctx, self.services)
        try:
            await self.ssdp.start()
        except OSError as exc:
            log.warning("SSDP discovery unavailable (%s); continuing without it", exc)
            self.ssdp = None

        log.info(
            "Noso up: room=%r uid=%s at %s (audio=%s)",
            ctx.state.room_name,
            ctx.identity.rincon,
            ctx.description_url,
            ctx.player.name,
        )

    def _wire_player_events(self, ctx: ServerContext, loop: asyncio.AbstractEventLoop) -> None:
        avt = ctx.services.get(AVT_TYPE)

        def notify_transport(*_a) -> None:
            # Called from a backend thread; hop onto the loop before touching GENA.
            if ctx.gena and avt:
                loop.call_soon_threadsafe(ctx.gena.notify, avt)

        ctx.player.set_callbacks(on_state=notify_transport, on_eos=notify_transport)

    async def stop(self) -> None:
        if self.ssdp:
            await self.ssdp.stop()  # multicasts ssdp:byebye
        if self.http:
            await self.http.stop()
        if self.ctx and self.ctx.gena:
            await self.ctx.gena.stop()
        if self.ctx:
            self.ctx.player.close()
        log.info("Noso stopped")
