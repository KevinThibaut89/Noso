"""SOAP request parsing and response/fault construction (UPnP control)."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from .xmlutil import xml_escape

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP_ENC = "http://schemas.xmlsoap.org/soap/encoding/"
UPNP_ERR_NS = "urn:schemas-upnp-org:control-1-0"


class UPnPError(Exception):
    """A UPnP control error, rendered as a SOAP Fault with an errorCode."""

    def __init__(self, code: int, description: str = "") -> None:
        super().__init__(f"{code} {description}")
        self.code = code
        self.description = description or _ERROR_DESCRIPTIONS.get(code, "Error")


# A useful subset of the UPnP error table.
_ERROR_DESCRIPTIONS = {
    401: "Invalid Action",
    402: "Invalid Args",
    501: "Action Failed",
    600: "Argument Value Invalid",
    701: "Transition not available",
    711: "Restricted parent object",
    714: "No such source resource",
    718: "Invalid InstanceID",
    719: "No such object",
}


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_soap_action(header: str) -> tuple[str, str]:
    """Split a ``SOAPACTION`` header into ``(service_type, action)``.

    Header form: ``"urn:schemas-upnp-org:service:AVTransport:1#Play"``.
    """
    value = (header or "").strip().strip('"')
    if "#" not in value:
        raise UPnPError(401, "Invalid Action")
    service_type, action = value.rsplit("#", 1)
    return service_type, action


def parse_args(body: bytes) -> dict[str, str]:
    """Extract the in-arguments from a SOAP control request body.

    Returns a ``{name: text}`` dict for the children of the action element.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise UPnPError(402, "Invalid Args") from exc

    body_el = root.find(f"{{{SOAP_ENV}}}Body")
    if body_el is None or len(body_el) == 0:
        return {}
    action_el = list(body_el)[0]
    args: dict[str, str] = {}
    for child in action_el:
        args[_localname(child.tag)] = child.text or ""
    return args


def build_response(service_type: str, action: str, out_args: dict[str, object]) -> bytes:
    """Build a SOAP ``<action>Response`` envelope.

    Every out-argument value is XML-escaped as element text. That single level
    of escaping is exactly what carries an XML-in-XML payload such as
    ``GetZoneGroupStateResponse`` (whose value is itself a ``ZoneGroupState``
    document) correctly to the controller.
    """
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<s:Envelope xmlns:s="{SOAP_ENV}" s:encodingStyle="{SOAP_ENC}">',
        "<s:Body>",
        f'<u:{action}Response xmlns:u="{service_type}">',
    ]
    for name, value in out_args.items():
        parts.append(f"<{name}>{xml_escape(str(value))}</{name}>")
    parts.append(f"</u:{action}Response>")
    parts.append("</s:Body></s:Envelope>")
    return "".join(parts).encode("utf-8")


def build_fault(error: UPnPError) -> bytes:
    """Build a SOAP Fault carrying a UPnP ``errorCode``/``errorDescription``."""
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<s:Envelope xmlns:s="{SOAP_ENV}" s:encodingStyle="{SOAP_ENC}">',
        "<s:Body>",
        "<s:Fault>",
        "<faultcode>s:Client</faultcode>",
        "<faultstring>UPnPError</faultstring>",
        "<detail>",
        f'<UPnPError xmlns="{UPNP_ERR_NS}">',
        f"<errorCode>{error.code}</errorCode>",
        f"<errorDescription>{xml_escape(error.description)}</errorDescription>",
        "</UPnPError>",
        "</detail>",
        "</s:Fault>",
        "</s:Body></s:Envelope>",
    ]
    return "".join(parts).encode("utf-8")
