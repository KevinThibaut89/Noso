"""Minimal asyncio HTTP/1.1 server for the UPnP control plane on port 1400.

Deliberately hand-rolled and dependency-free. UPnP clients send well-formed
requests with a ``Content-Length`` body, and GENA needs the non-standard
``SUBSCRIBE`` / ``UNSUBSCRIBE`` methods, so a tiny purpose-built server is both
simpler and more faithful than bending a general framework. Responses use
``Connection: close`` — controllers reconnect per request.
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlsplit

from .config import server_string
from .context import ServerContext
from .device import render_device_description
from .scpd import scpd_for
from .soap import UPnPError, build_fault, build_response, parse_args, parse_soap_action

log = logging.getLogger("noso.http")

# 1x1 transparent PNG, so /img/icon-*.png resolves to a valid image.
_ICON_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class HttpServer:
    def __init__(self, ctx: ServerContext, services: list) -> None:
        self.ctx = ctx
        self.services = services
        self._server: asyncio.AbstractServer | None = None
        # Path -> service routing tables, built once.
        self._control: dict[str, object] = {s.control_path: s for s in services}
        self._events: dict[str, object] = {s.event_path: s for s in services}
        self._scpd: dict[str, object] = {s.scpd_path: s for s in services}

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, self.ctx.config.bind_ip, self.ctx.config.http_port
        )
        log.info("HTTP server on %s:%s", self.ctx.config.bind_ip, self.ctx.config.http_port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # -- request loop ------------------------------------------------------
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await self._read_request(reader)
            if request is None:
                return
            method, path, headers, body = request
            await self._route(writer, method, path, headers, body)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001 - never let one request kill the server
            log.exception("error handling request")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _read_request(self, reader: asyncio.StreamReader):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            return None
        lines = head.decode("iso-8859-1").split("\r\n")
        if not lines or " " not in lines[0]:
            return None
        parts = lines[0].split(" ")
        method, target = parts[0], parts[1]
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        body = b""
        length = int(headers.get("content-length", "0") or "0")
        if length:
            body = await reader.readexactly(length)
        path = urlsplit(target).path
        return method, path, headers, body

    # -- routing -----------------------------------------------------------
    async def _route(self, writer, method, path, headers, body) -> None:
        if method == "GET":
            await self._get(writer, path)
        elif method == "POST" and path in self._control:
            await self._control_request(writer, path, headers, body)
        elif method in ("SUBSCRIBE", "UNSUBSCRIBE") and path in self._events:
            await self._gena(writer, method, path, headers)
        elif method == "NOTIFY":
            await self._send(writer, 200)  # we don't consume inbound events
        else:
            await self._send(writer, 404, body=b"Not Found")

    async def _get(self, writer, path) -> None:
        if path in ("/xml/device_description.xml", "/xml/zone_player.xml"):
            body = render_device_description(self.ctx, self.services).encode("utf-8")
            await self._send(writer, 200, body=body)
        elif path in self._scpd:
            await self._send(writer, 200, body=scpd_for(self._scpd[path]))
        elif path.startswith("/img/"):
            await self._send(writer, 200, body=_ICON_PNG, content_type="image/png")
        elif path.startswith("/api/"):
            await self._api(writer, path)
        else:
            await self._send(writer, 404, body=b"Not Found")

    async def _api(self, writer, path) -> None:
        """Local Sonos control API (partial).

        After mDNS discovery the app GETs the TXT `info` path
        (`/api/v1/players/<RINCON>/info`) to bootstrap. We answer it with the
        player-info JSON a real speaker returns. (The app then tries the
        cert-pinned wss://:1443 channel, which a software emulator can't
        satisfy — see README.)
        """
        if path.endswith("/info"):
            body = json.dumps(self._player_info()).encode("utf-8")
            await self._send(writer, 200, body=body, content_type="application/json")
        else:
            await self._send(writer, 200, body=b"{}", content_type="application/json")

    def _player_info(self) -> dict:
        ctx = self.ctx
        cfg = ctx.config
        ident = ctx.identity
        household = cfg.household or ident.household
        wss = f"wss://{ctx.ip}:1443/websocket/api"
        return {
            "device": {
                "id": ident.rincon,
                "primaryDeviceId": ident.rincon,
                "serialNumber": ident.serial,
                "model": cfg.model_number,
                "modelDisplayName": cfg.model_name,
                "name": ctx.state.room_name,
                "softwareVersion": cfg.software_version,
                "hwVersion": cfg.hardware_version,
                "swGen": 2,
                "apiVersion": cfg.api_version,
                "minApiVersion": cfg.min_api_version,
                "capabilities": ["PLAYBACK", "CLOUD", "LINE_IN", "AUDIO_CLIP"],
                "websocketUrl": wss,
            },
            "householdId": household,
            "playerId": ident.rincon,
            "groupId": f"{ident.rincon}:0",
            "websocketUrl": wss,
            "restUrl": f"https://{ctx.ip}:1443/api/v1",
        }

    async def _control_request(self, writer, path, headers, body) -> None:
        service = self._control[path]
        try:
            service_type, action = parse_soap_action(headers.get("soapaction", ""))
            if service_type != service.service_type:
                raise UPnPError(401, "Invalid Action")
            out = service.handle(action, parse_args(body))
            response = build_response(service.service_type, action, out)
            await self._send(writer, 200, body=response)
        except UPnPError as err:
            await self._send(writer, 500, body=build_fault(err), reason="Internal Server Error")
        except Exception:  # noqa: BLE001
            log.exception("control error on %s", path)
            await self._send(
                writer, 500, body=build_fault(UPnPError(501)), reason="Internal Server Error"
            )

    async def _gena(self, writer, method, path, headers) -> None:
        gena = self.ctx.gena
        service = self._events[path]
        if gena is None:
            await self._send(writer, 500)
            return
        if method == "UNSUBSCRIBE":
            gena.unsubscribe(headers.get("sid", ""))
            await self._send(writer, 200)
            return
        # SUBSCRIBE: a new subscription has CALLBACK+NT; a renewal has only SID.
        sid = headers.get("sid")
        if sid:
            seconds = gena.renew(sid, headers.get("timeout"))
            if seconds is None:
                await self._send(writer, 412, reason="Precondition Failed")
                return
            await self._send(
                writer, 200, extra={"SID": sid, "TIMEOUT": f"Second-{seconds}"}
            )
            return
        sid, seconds = gena.subscribe(
            service, headers.get("callback"), headers.get("timeout")
        )
        await self._send(writer, 200, extra={"SID": sid, "TIMEOUT": f"Second-{seconds}"})

    # -- response helper ---------------------------------------------------
    async def _send(
        self,
        writer,
        status: int,
        body: bytes = b"",
        reason: str = "OK",
        content_type: str = 'text/xml; charset="utf-8"',
        extra: dict[str, str] | None = None,
    ) -> None:
        headers = {
            "CONTENT-LENGTH": str(len(body)),
            "CONTENT-TYPE": content_type,
            "SERVER": server_string(self.ctx.config),
            "CONNECTION": "close",
            "EXT": "",
        }
        if extra:
            headers.update(extra)
        head = f"HTTP/1.1 {status} {reason}\r\n"
        head += "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        head += "\r\n"
        try:
            writer.write(head.encode("iso-8859-1") + body)
            await writer.drain()
        except (ConnectionResetError, OSError):
            pass
