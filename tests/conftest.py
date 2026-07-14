"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest

from noso.app import _SERVICE_CLASSES
from noso.audio.null import NullPlayer
from noso.config import Config
from noso.context import ServerContext
from noso.gena import GenaManager
from noso.httpd import HttpServer
from noso.identity import Identity
from noso.state import ZoneState

TEST_IDENTITY = Identity(node="A1B2C3", household="Sonos_testhousehold", boot_seq=1)


def build_context(port: int, room: str = "Test Room") -> tuple[ServerContext, list]:
    cfg = Config(http_port=port, bind_ip="127.0.0.1", interface_ip="127.0.0.1", room_name=room)
    ctx = ServerContext(
        config=cfg,
        identity=TEST_IDENTITY,
        ip="127.0.0.1",
        state=ZoneState(room_name=room, icon=cfg.icon),
        player=NullPlayer(),
    )
    services = [cls(ctx) for cls in _SERVICE_CLASSES]
    ctx.services = {s.service_type: s for s in services}
    return ctx, services


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def server():
    """Start the HTTP + GENA stack in a background thread; yield (base_url, ctx)."""
    port = _free_port()
    ctx, services = build_context(port)
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run() -> None:
        asyncio.set_event_loop(loop)
        ctx.loop = loop
        ctx.gena = GenaManager(ctx)
        http = HttpServer(ctx, services)
        loop.run_until_complete(http.start())
        ctx.gena.start()
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(5), "server did not start"

    yield f"http://127.0.0.1:{port}", ctx

    loop.call_soon_threadsafe(loop.stop)
    thread.join(2)
