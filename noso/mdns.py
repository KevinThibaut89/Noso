"""mDNS / DNS-SD advertisement of ``_sonos._tcp.local``.

The modern Sonos app dropped SSDP for local discovery and finds speakers over
mDNS, so without this a current app never learns Noso exists. We mirror what a
real speaker broadcasts (verified against Home Assistant captures):

* instance name ``Sonos-<MAC>`` (12 hex, uppercase, no separators)
* SRV host ``Sonos-<MAC>.local.``, **port 1400** (the HTTP port; the TLS API
  port 1443 is carried in the ``sslport`` TXT key, not the SRV)
* the full TXT set: ``info`` (the ``/api/v1/players/<RINCON>/info`` bootstrap
  path the app fetches next), ``hhid``/``mhhid`` (household), ``location``,
  ``sslport``/``hhsslport``, ``bootseq``, ``protovers``, ``vers``, ``variant``,
  ``mdnssequence``.

Two backends, chosen at runtime: python-zeroconf (pure-Python, preferred) or an
``avahi-publish-service`` subprocess (for hosts already running avahi-daemon,
avoiding a second responder on :5353). Failure is non-fatal — SSDP still runs.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import socket
import subprocess

from .context import ServerContext

log = logging.getLogger("noso.mdns")

SERVICE_TYPE = "_sonos._tcp.local."


def instance_name(ctx: ServerContext) -> str:
    """The DNS-SD service instance label.

    Verified from a live capture of real speakers, the label is
    ``RINCON_<mac>01400@<RoomName>`` (e.g. ``RINCON_B8E93799FA0201400@Living
    Room``) — not ``Sonos-<MAC>``. The app parses the RINCON and room out of it.
    """
    return f"{ctx.identity.rincon}@{ctx.state.room_name}"


def household_id(ctx: ServerContext) -> str:
    return ctx.config.household or ctx.identity.household


def sonos_txt(ctx: ServerContext) -> dict[str, str]:
    """The TXT record set a real speaker publishes, with our identity."""
    ident = ctx.identity
    hhid = household_id(ctx)
    return {
        "info": f"/api/v1/players/{ident.rincon}/info",
        "vers": "3",
        "protovers": ctx.config.protovers,
        "bootseq": str(ident.boot_seq),
        "hhid": hhid,
        "mhhid": f"{hhid}.0",
        "location": f"{ctx.base_url}/xml/device_description.xml",
        "sslport": "1443",
        "hhsslport": "1843",
        "variant": "2",
        "mdnssequence": "0",
    }


class _ZeroconfBackend:
    name = "zeroconf"

    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self._zc = None
        self._info = None

    def start(self) -> None:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf

        mac = self.ctx.identity.mac_hex
        self._info = ServiceInfo(
            type_=SERVICE_TYPE,
            name=f"{instance_name(self.ctx)}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(self.ctx.ip)],
            port=self.ctx.config.http_port,
            properties={k.encode(): v.encode() for k, v in sonos_txt(self.ctx).items()},
            server=f"Sonos-{mac}.local.",  # A-record host (no spaces/@ allowed)
        )
        self._zc = Zeroconf(ip_version=IPVersion.V4Only)
        # cooperating_responders: don't fight another mDNS stack for the name
        # (we may share the LAN with the real household).
        self._zc.register_service(self._info, cooperating_responders=True)

    def stop(self) -> None:
        try:
            if self._zc and self._info:
                self._zc.unregister_service(self._info)
        finally:
            if self._zc:
                self._zc.close()


class _AvahiBackend:
    name = "avahi"

    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        args = ["avahi-publish-service", instance_name(self.ctx), "_sonos._tcp",
                str(self.ctx.config.http_port)]
        for key, value in sonos_txt(self.ctx).items():
            args.append(f"{key}={value}")
        self._proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _zeroconf_available() -> bool:
    try:
        import zeroconf  # noqa: F401
        return True
    except ImportError:
        return False


def _select_backend(ctx: ServerContext):
    choice = ctx.config.mdns_backend
    if choice == "none":
        return None
    if choice == "zeroconf":
        return _ZeroconfBackend(ctx) if _zeroconf_available() else None
    if choice == "avahi":
        return _AvahiBackend(ctx) if shutil.which("avahi-publish-service") else None
    # auto: prefer zeroconf, fall back to avahi
    if _zeroconf_available():
        return _ZeroconfBackend(ctx)
    if shutil.which("avahi-publish-service"):
        return _AvahiBackend(ctx)
    return None


class MdnsAdvertiser:
    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self._backend = None

    async def start(self) -> None:
        if not self.ctx.config.mdns_enabled:
            log.info("mDNS advertisement disabled by config")
            return
        backend = _select_backend(self.ctx)
        if backend is None:
            log.warning(
                "no mDNS backend (install python-zeroconf or avahi-utils); "
                "the modern Sonos app will NOT discover Noso without mDNS"
            )
            return
        loop = asyncio.get_running_loop()
        try:
            # register_service does blocking network I/O; keep it off the loop.
            await loop.run_in_executor(None, backend.start)
        except Exception as exc:  # noqa: BLE001
            log.warning("mDNS advertisement failed via %s: %s", backend.name, exc)
            return
        self._backend = backend
        log.info(
            "mDNS advertising %s.%s port %d (backend=%s)",
            instance_name(self.ctx),
            SERVICE_TYPE,
            self.ctx.config.http_port,
            backend.name,
        )

    async def stop(self) -> None:
        if self._backend is None:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._backend.stop)
        except Exception:  # noqa: BLE001
            pass
        self._backend = None
