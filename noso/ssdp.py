"""SSDP discovery: answer M-SEARCH and announce presence via NOTIFY.

Advertises the full ZonePlayer set — root device (as rootdevice, by UUID, and
as ``ZonePlayer:1``), the two embedded devices, and every service — matching
what a real Sonos multicasts. Announcements also go to the broadcast address
so discovery survives multicast-hostile LANs (AP client isolation, IGMP
snooping).
"""

from __future__ import annotations

import asyncio
import logging
import random

from .config import server_string
from .context import ServerContext
from .netutil import BROADCAST_ADDR, SSDP_ADDR, SSDP_PORT, make_ssdp_socket

log = logging.getLogger("noso.ssdp")


def build_entries(ctx: ServerContext, services: list) -> list[tuple[str, str]]:
    """Return the ``(NT, USN)`` advertisement set for this device."""
    ident = ctx.identity
    root = ident.uuid
    entries: list[tuple[str, str]] = [
        ("upnp:rootdevice", f"{root}::upnp:rootdevice"),
        (root, root),
        (
            "urn:schemas-upnp-org:device:ZonePlayer:1",
            f"{root}::urn:schemas-upnp-org:device:ZonePlayer:1",
        ),
        (ident.uuid_ms, ident.uuid_ms),
        (
            "urn:schemas-upnp-org:device:MediaServer:1",
            f"{ident.uuid_ms}::urn:schemas-upnp-org:device:MediaServer:1",
        ),
        (ident.uuid_mr, ident.uuid_mr),
        (
            "urn:schemas-upnp-org:device:MediaRenderer:1",
            f"{ident.uuid_mr}::urn:schemas-upnp-org:device:MediaRenderer:1",
        ),
    ]
    device_udn = {"root": root, "MS": ident.uuid_ms, "MR": ident.uuid_mr}
    for svc in services:
        udn = device_udn[svc.device]
        entries.append((svc.service_type, f"{udn}::{svc.service_type}"))
    return entries


def _parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in text.split("\r\n")[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers


class SsdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, manager: "SsdpServer") -> None:
        self.manager = manager

    def connection_made(self, transport) -> None:  # type: ignore[override]
        self.manager.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
        try:
            text = data.decode("iso-8859-1")
        except UnicodeDecodeError:
            return
        if not text.startswith("M-SEARCH"):
            return
        headers = _parse_headers(text)
        if headers.get("man", "").strip('"') != "ssdp:discover":
            return
        st = headers.get("st", "").strip()
        try:
            mx = max(0, min(int(headers.get("mx", "1")), 5))
        except ValueError:
            mx = 1
        self.manager.respond(st, addr, mx)


class SsdpServer:
    def __init__(self, ctx: ServerContext, services: list) -> None:
        self.ctx = ctx
        self.entries = build_entries(ctx, services)
        self.transport = None
        self._announce_task: asyncio.Task | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        sock = make_ssdp_socket(self.ctx.config.bind_ip, self.ctx.config.ssdp_ttl)
        await loop.create_datagram_endpoint(lambda: SsdpProtocol(self), sock=sock)
        # Announce a few times at startup (datagrams get lost), then periodically.
        self._announce_task = asyncio.ensure_future(self._announce_loop())
        log.info("SSDP responder active (%d advertisements)", len(self.entries))

    async def stop(self) -> None:
        if self._announce_task:
            self._announce_task.cancel()
        self._send_notify("ssdp:byebye")
        if self.transport:
            self.transport.close()

    # -- outbound ----------------------------------------------------------
    def respond(self, st: str, addr, mx: int) -> None:
        matches = self.entries if st == "ssdp:all" else [e for e in self.entries if e[0] == st]
        if not matches:
            return
        delay = random.uniform(0, min(mx, 2)) if mx else 0.0
        for nt, usn in matches:
            message = self._search_response(nt, usn)
            self.ctx.loop.call_later(delay, self._sendto, message, addr)

    def _sendto(self, message: bytes, addr) -> None:
        if self.transport is not None:
            try:
                self.transport.sendto(message, addr)
            except OSError as exc:
                log.debug("sendto %s failed: %s", addr, exc)

    async def _announce_loop(self) -> None:
        try:
            for _ in range(3):  # startup burst
                self._send_notify("ssdp:alive")
                await asyncio.sleep(0.3)
            while True:
                await asyncio.sleep(self.ctx.config.announce_interval)
                self._send_notify("ssdp:alive")
        except asyncio.CancelledError:
            pass

    def _send_notify(self, nts: str) -> None:
        for nt, usn in self.entries:
            message = self._notify(nt, usn, nts)
            for dest in ((SSDP_ADDR, SSDP_PORT), (BROADCAST_ADDR, SSDP_PORT)):
                self._sendto(message, dest)

    # -- message templates -------------------------------------------------
    def _common_headers(self) -> str:
        ident = self.ctx.identity
        return (
            f"LOCATION: {self.ctx.description_url}\r\n"
            f"SERVER: {server_string(self.ctx.config)}\r\n"
            f"BOOTID.UPNP.ORG: {ident.boot_seq}\r\n"
            "CONFIGID.UPNP.ORG: 1\r\n"
            f"X-RINCON-BOOTSEQ: {ident.boot_seq}\r\n"
            f"X-RINCON-HOUSEHOLD: {ident.household}\r\n"
        )

    def _search_response(self, nt: str, usn: str) -> bytes:
        return (
            "HTTP/1.1 200 OK\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            "EXT:\r\n"
            f"{self._common_headers()}"
            f"ST: {nt}\r\n"
            f"USN: {usn}\r\n"
            "\r\n"
        ).encode("iso-8859-1")

    def _notify(self, nt: str, usn: str, nts: str) -> bytes:
        if nts == "ssdp:byebye":
            return (
                "NOTIFY * HTTP/1.1\r\n"
                f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                f"NT: {nt}\r\n"
                "NTS: ssdp:byebye\r\n"
                f"USN: {usn}\r\n"
                f"X-RINCON-HOUSEHOLD: {self.ctx.identity.household}\r\n"
                "\r\n"
            ).encode("iso-8859-1")
        return (
            "NOTIFY * HTTP/1.1\r\n"
            f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            f"{self._common_headers()}"
            f"NT: {nt}\r\n"
            "NTS: ssdp:alive\r\n"
            f"USN: {usn}\r\n"
            "\r\n"
        ).encode("iso-8859-1")
