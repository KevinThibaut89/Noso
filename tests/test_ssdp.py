import asyncio

from noso.ssdp import SsdpProtocol, SsdpServer, build_entries
from tests.conftest import build_context

MSEARCH_ZP = (
    b"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
    b'MAN: "ssdp:discover"\r\nMX: 0\r\n'
    b"ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n"
)


class _FakeTransport:
    def __init__(self) -> None:
        self.sent: list = []

    def sendto(self, message, addr) -> None:
        self.sent.append((message, addr))


def _drive(msearch: bytes):
    ctx, services = build_context(1400)

    async def run():
        ctx.loop = asyncio.get_running_loop()
        ssdp = SsdpServer(ctx, services)
        ssdp.transport = _FakeTransport()
        SsdpProtocol(ssdp).datagram_received(msearch, ("192.168.1.9", 5000))
        await asyncio.sleep(0.05)
        return ssdp.transport.sent

    return asyncio.run(run())


def test_build_entries_covers_device_and_services():
    ctx, services = build_context(1400)
    nts = {nt for nt, _ in build_entries(ctx, services)}
    assert "upnp:rootdevice" in nts
    assert "urn:schemas-upnp-org:device:ZonePlayer:1" in nts
    assert ctx.identity.uuid in nts
    assert "urn:schemas-upnp-org:service:AVTransport:1" in nts


def test_msearch_reply_headers():
    sent = _drive(MSEARCH_ZP)
    assert sent, "no SSDP reply"
    reply = sent[0][0].decode()
    assert "HTTP/1.1 200 OK" in reply
    assert "ST: urn:schemas-upnp-org:device:ZonePlayer:1" in reply
    assert "USN: uuid:RINCON_000E58A1B2C301400::urn:schemas-upnp-org:device:ZonePlayer:1" in reply
    assert "LOCATION: http://127.0.0.1:1400/xml/device_description.xml" in reply
    assert "SERVER: Linux UPnP/1.0 Sonos/" in reply


def test_msearch_unrelated_st_ignored():
    sent = _drive(
        b"M-SEARCH * HTTP/1.1\r\n"
        b'MAN: "ssdp:discover"\r\nMX: 0\r\n'
        b"ST: urn:some-other:device:Thing:1\r\n\r\n"
    )
    assert sent == []
