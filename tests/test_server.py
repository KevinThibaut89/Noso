"""Integration tests: drive the running HTTP/SOAP/GENA server over loopback."""

import http.client
import xml.etree.ElementTree as ET

AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"
ZGT = "urn:schemas-upnp-org:service:ZoneGroupTopology:1"


def _request(base, method, path, headers=None, body=b""):
    host = base.split("//", 1)[1]
    conn = http.client.HTTPConnection(host, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


def _soap(service_type, action, args=""):
    return (
        '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<s:Body><u:{action} xmlns:u="{service_type}">{args}</u:{action}></s:Body></s:Envelope>'
    ).encode()


def test_device_description(server):
    base, _ = server
    status, _, body = _request(base, "GET", "/xml/device_description.xml")
    assert status == 200
    root = ET.fromstring(body)
    ns = "{urn:schemas-upnp-org:device-1-0}"
    dev = root.find(f"{ns}device")
    assert dev.findtext(f"{ns}deviceType") == "urn:schemas-upnp-org:device:ZonePlayer:1"
    assert dev.findtext(f"{ns}manufacturer") == "Sonos, Inc."
    assert len(dev.find(f"{ns}deviceList").findall(f"{ns}device")) == 2


def test_device_description_version_fields(server):
    """S2 version fields must flow through (else the app flags the device S1),
    and the old cosmetic double-"Sonos" must be gone.
    """
    base, ctx = server
    _, _, body = _request(base, "GET", "/xml/device_description.xml")
    ns = "{urn:schemas-upnp-org:device-1-0}"
    dev = ET.fromstring(body).find(f"{ns}device")
    assert dev.findtext(f"{ns}softwareVersion") == ctx.config.software_version
    assert dev.findtext(f"{ns}displayVersion") == ctx.config.display_version
    assert dev.findtext(f"{ns}minCompatibleVersion") == ctx.config.min_compatible_version
    assert dev.findtext(f"{ns}hardwareVersion") == ctx.config.hardware_version
    assert dev.findtext(f"{ns}swGen") == "2"
    assert b"Sonos Sonos" not in body  # no double-brand in modelDescription


def test_scpd_served(server):
    base, _ = server
    status, _, body = _request(base, "GET", "/xml/AVTransport1.xml")
    assert status == 200
    ET.fromstring(body)  # valid XML


def test_get_zone_group_state(server):
    base, _ = server
    status, _, body = _request(
        base, "POST", "/ZoneGroupTopology/Control",
        {"SOAPACTION": f'"{ZGT}#GetZoneGroupState"'},
        _soap(ZGT, "GetZoneGroupState"),
    )
    assert status == 200
    env = ET.fromstring(body)
    zgs_text = list(list(env)[0])[0][0].text
    member = ET.fromstring(zgs_text).find(".//ZoneGroupMember")
    assert member.get("ZoneName") == "Test Room"


def test_volume_roundtrip(server):
    base, _ = server
    _request(
        base, "POST", "/MediaRenderer/RenderingControl/Control",
        {"SOAPACTION": f'"{RC}#SetVolume"'},
        _soap(RC, "SetVolume",
              "<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>42</DesiredVolume>"),
    )
    status, _, body = _request(
        base, "POST", "/MediaRenderer/RenderingControl/Control",
        {"SOAPACTION": f'"{RC}#GetVolume"'},
        _soap(RC, "GetVolume", "<InstanceID>0</InstanceID><Channel>Master</Channel>"),
    )
    assert status == 200
    assert ET.fromstring(body).find(".//CurrentVolume").text == "42"


def test_invalid_action_returns_fault(server):
    base, _ = server
    status, _, body = _request(
        base, "POST", "/MediaRenderer/AVTransport/Control",
        {"SOAPACTION": f'"{AVT}#DoesNotExist"'},
        _soap(AVT, "DoesNotExist"),
    )
    assert status == 500
    code = ET.fromstring(body).find(".//{urn:schemas-upnp-org:control-1-0}errorCode").text
    assert code == "401"


def test_player_info_endpoint(server):
    """The mDNS TXT `info` path the modern app fetches after discovery."""
    base, ctx = server
    rincon = ctx.identity.rincon
    status, _, body = _request(base, "GET", f"/api/v1/players/{rincon}/info")
    assert status == 200
    import json

    data = json.loads(body)
    assert data["playerId"] == rincon
    assert data["householdId"]
    assert data["websocketUrl"].startswith("wss://")
    assert data["device"]["name"] == "Test Room"


def test_subscribe_returns_sid(server):
    base, _ = server
    status, headers, _ = _request(
        base, "SUBSCRIBE", "/MediaRenderer/RenderingControl/Event",
        {"CALLBACK": "<http://127.0.0.1:9/none>", "NT": "upnp:event", "TIMEOUT": "Second-1800"},
    )
    assert status == 200
    assert headers.get("SID", "").startswith("uuid:")
    assert headers.get("TIMEOUT") == "Second-1800"
