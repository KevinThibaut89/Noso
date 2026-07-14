"""Networking helpers: pick the advertised IP and build the SSDP socket."""

from __future__ import annotations

import socket
import struct

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
BROADCAST_ADDR = "255.255.255.255"


def primary_ip(hint: str | None = None) -> str:
    """Best-effort LAN IPv4 address to advertise in LOCATION/ZoneGroupState.

    Uses the classic "UDP connect" trick: connecting a datagram socket to a
    public address makes the kernel pick the egress interface without sending
    a single packet, so we can read its local address.
    """
    if hint:
        return hint
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def make_ssdp_socket(bind_ip: str = "0.0.0.0", ttl: int = 4) -> socket.socket:
    """Create a UDP socket joined to the SSDP multicast group.

    Bound to port 1900 with address reuse so it coexists with other UPnP
    stacks on the host, joined to 239.255.255.250, and broadcast-enabled so we
    can also blast announcements to 255.255.255.255 on multicast-hostile LANs.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # SO_REUSEPORT lets a real Sonos + Noso (or multiple Nosos) share :1900.
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):  # not on every platform
        pass
    sock.bind(("", SSDP_PORT))

    group = socket.inet_aton(SSDP_ADDR)
    iface = socket.inet_aton(bind_ip if bind_ip not in ("", "0.0.0.0") else "0.0.0.0")
    mreq = struct.pack("=4s4s", group, iface)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    if bind_ip not in ("", "0.0.0.0"):
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, iface)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    return sock
