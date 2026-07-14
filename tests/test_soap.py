import xml.etree.ElementTree as ET

import pytest

from noso.soap import (
    UPnPError,
    build_fault,
    build_response,
    parse_args,
    parse_soap_action,
)


def test_parse_soap_action():
    st, action = parse_soap_action('"urn:schemas-upnp-org:service:AVTransport:1#Play"')
    assert st == "urn:schemas-upnp-org:service:AVTransport:1"
    assert action == "Play"


def test_parse_soap_action_invalid():
    with pytest.raises(UPnPError) as exc:
        parse_soap_action("garbage-without-hash")
    assert exc.value.code == 401


def test_parse_args():
    body = (
        b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        b'<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
        b"<InstanceID>0</InstanceID><CurrentURI>http://x/y.mp3</CurrentURI>"
        b"<CurrentURIMetaData></CurrentURIMetaData>"
        b"</u:SetAVTransportURI></s:Body></s:Envelope>"
    )
    args = parse_args(body)
    assert args == {"InstanceID": "0", "CurrentURI": "http://x/y.mp3", "CurrentURIMetaData": ""}


def test_build_response_escapes_xml_in_xml():
    inner = '<ZoneGroupState><ZoneGroupMember ZoneName="A &amp; B"/></ZoneGroupState>'
    resp = build_response(
        "urn:schemas-upnp-org:service:ZoneGroupTopology:1",
        "GetZoneGroupState",
        {"ZoneGroupState": inner},
    )
    root = ET.fromstring(resp)  # outer envelope well-formed
    text = None
    for el in root.iter():
        if el.tag.endswith("GetZoneGroupStateResponse"):
            text = list(el)[0].text
    assert text is not None
    reparsed = ET.fromstring(text)  # the (once-unescaped) inner doc is valid XML
    assert reparsed.find(".//ZoneGroupMember").get("ZoneName") == "A & B"


def test_build_fault():
    fault = build_fault(UPnPError(718))
    root = ET.fromstring(fault)
    code = root.find(".//{urn:schemas-upnp-org:control-1-0}errorCode").text
    assert code == "718"
