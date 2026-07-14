"""GENA eventing (UPnP's SUBSCRIBE / NOTIFY).

Controllers SUBSCRIBE to a service's ``eventSubURL`` and expect (a) an
immediate NOTIFY carrying full initial state, and (b) a NOTIFY whenever an
evented variable changes. Apps commonly drop a device that never sends the
initial event, so that path is implemented up front.

Sonos uses the ``LastChange`` pattern for AVTransport / RenderingControl (one
evented variable whose value is an escaped ``<Event>`` document) and events the
whole ``ZoneGroupState`` for ZoneGroupTopology. Both are just "evented variable
-> string value" here; the service decides the payload via ``event_state()``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from .config import server_string
from .context import ServerContext
from .services.base import Service
from .xmlutil import xml_escape

log = logging.getLogger("noso.gena")

DEFAULT_TIMEOUT = 1800
_CALLBACK_RE = re.compile(r"<([^>]+)>")


@dataclass
class Subscription:
    sid: str
    service: Service
    callbacks: list[str]
    expiry: float  # monotonic deadline
    seq: int = 0
    # Coalesced pending values (var -> latest value) awaiting delivery.
    pending: dict[str, str] = field(default_factory=dict)


def _parse_timeout(header: str | None) -> int:
    if header:
        header = header.strip().lower()
        if header.startswith("second-"):
            try:
                return int(header.split("-", 1)[1])
            except ValueError:
                pass
    return DEFAULT_TIMEOUT


def _parse_callbacks(header: str | None) -> list[str]:
    return _CALLBACK_RE.findall(header or "")


class GenaManager:
    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self.subs: dict[str, Subscription] = {}
        self._sweeper: asyncio.Task | None = None
        self._coalesce_delay = 0.2  # seconds; batch bursty LastChange updates

    def start(self) -> None:
        self._sweeper = asyncio.ensure_future(self._sweep_loop())

    async def stop(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
        self.subs.clear()

    # -- subscription lifecycle -------------------------------------------
    def subscribe(self, service: Service, callback: str | None, timeout: str | None):
        """Create a subscription. Returns ``(sid, timeout_seconds)``."""
        seconds = _parse_timeout(timeout)
        sid = f"uuid:{uuid.uuid4()}"
        sub = Subscription(
            sid=sid,
            service=service,
            callbacks=_parse_callbacks(callback),
            expiry=time.monotonic() + seconds,
        )
        self.subs[sid] = sub
        # Deliver the mandatory initial event (SEQ 0) right after we return the
        # SUBSCRIBE response.
        if self.ctx.loop:
            self.ctx.loop.call_soon(lambda: asyncio.ensure_future(self._send_initial(sub)))
        log.info("SUBSCRIBE %s -> %s (%ss)", service.service_type, sid, seconds)
        return sid, seconds

    def renew(self, sid: str, timeout: str | None) -> int | None:
        sub = self.subs.get(sid)
        if sub is None:
            return None
        seconds = _parse_timeout(timeout)
        sub.expiry = time.monotonic() + seconds
        return seconds

    def unsubscribe(self, sid: str) -> bool:
        return self.subs.pop(sid, None) is not None

    # -- change notification ----------------------------------------------
    def notify(self, service: Service) -> None:
        """Queue a change NOTIFY for every subscriber of ``service``."""
        state = service.event_state()
        if not state:
            return
        for sub in list(self.subs.values()):
            if sub.service is service:
                sub.pending.update(state)
                if self.ctx.loop:
                    self.ctx.loop.call_later(
                        self._coalesce_delay,
                        lambda s=sub: asyncio.ensure_future(self._flush(s)),
                    )

    async def _send_initial(self, sub: Subscription) -> None:
        state = sub.service.event_state()
        if state:
            await self._deliver(sub, state)

    async def _flush(self, sub: Subscription) -> None:
        if sub.sid not in self.subs or not sub.pending:
            return
        payload = dict(sub.pending)
        sub.pending.clear()
        await self._deliver(sub, payload)

    async def _deliver(self, sub: Subscription, variables: dict[str, str]) -> None:
        body = _propertyset(variables)
        seq = sub.seq
        sub.seq += 1
        for url in sub.callbacks:
            try:
                await self._post_notify(url, sub.sid, seq, body)
                break  # first working callback wins, per spec
            except OSError as exc:
                log.debug("NOTIFY to %s failed: %s", url, exc)

    async def _post_notify(self, url: str, sid: str, seq: int, body: bytes) -> None:
        host, port, path = _split_url(url)
        reader, writer = await asyncio.open_connection(host, port)
        try:
            request = (
                f"NOTIFY {path} HTTP/1.1\r\n"
                f"HOST: {host}:{port}\r\n"
                'CONTENT-TYPE: text/xml; charset="utf-8"\r\n'
                f"CONTENT-LENGTH: {len(body)}\r\n"
                "NT: upnp:event\r\n"
                "NTS: upnp:propchange\r\n"
                f"SID: {sid}\r\n"
                f"SEQ: {seq}\r\n"
                f"SERVER: {server_string(self.ctx.config)}\r\n"
                "CONNECTION: close\r\n\r\n"
            ).encode("utf-8") + body
            writer.write(request)
            await writer.drain()
            try:
                await asyncio.wait_for(reader.read(1024), timeout=5)
            except asyncio.TimeoutError:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                now = time.monotonic()
                for sid, sub in list(self.subs.items()):
                    if sub.expiry <= now:
                        self.subs.pop(sid, None)
                        log.debug("subscription expired: %s", sid)
        except asyncio.CancelledError:
            pass


def _propertyset(variables: dict[str, str]) -> bytes:
    props = "".join(
        f"<e:property><{name}>{xml_escape(value)}</{name}></e:property>"
        for name, value in variables.items()
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">'
        f"{props}</e:propertyset>"
    ).encode("utf-8")


def _split_url(url: str) -> tuple[str, int, str]:
    # Minimal parse for http://host:port/path callbacks.
    rest = url.split("://", 1)[-1]
    netloc, _, path = rest.partition("/")
    host, _, port = netloc.partition(":")
    return host, int(port or 80), "/" + path
