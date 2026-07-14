"""Render ``device_description.xml`` — the ZonePlayer device tree.

A Sonos device presents a non-standard root ``ZonePlayer`` device with two
embedded devices: a ``MediaServer`` (UDN ``..._MS``) and a ``MediaRenderer``
(UDN ``..._MR``). Each hosts a subset of the services. The manufacturer must be
``Sonos, Inc.`` and the root ``deviceType`` must be ``ZonePlayer:1`` or no
controller will treat it as Sonos.
"""

from __future__ import annotations

from typing import Iterable

from .context import ServerContext
from .services.base import Service
from .xmlutil import xml_escape as esc


def _service_block(svc: Service) -> str:
    return (
        "<service>"
        f"<serviceType>{svc.service_type}</serviceType>"
        f"<serviceId>{svc.service_id}</serviceId>"
        f"<controlURL>{svc.control_path}</controlURL>"
        f"<eventSubURL>{svc.event_path}</eventSubURL>"
        f"<SCPDURL>{svc.scpd_path}</SCPDURL>"
        "</service>"
    )


def _service_list(services: Iterable[Service]) -> str:
    inner = "".join(_service_block(s) for s in services)
    return f"<serviceList>{inner}</serviceList>"


def _icon_list(model_number: str) -> str:
    return (
        "<iconList><icon>"
        "<id>0</id>"
        "<mimetype>image/png</mimetype>"
        "<width>48</width><height>48</height><depth>24</depth>"
        f"<url>/img/icon-{esc(model_number)}.png</url>"
        "</icon></iconList>"
    )


def render_device_description(ctx: ServerContext, services: list[Service]) -> str:
    cfg = ctx.config
    ident = ctx.identity
    ip = ctx.ip
    model = cfg.model_name
    friendly = f"{ip} - {model}"

    root_services = [s for s in services if s.device == "root"]
    ms_services = [s for s in services if s.device == "MS"]
    mr_services = [s for s in services if s.device == "MR"]

    media_server = (
        "<device>"
        "<deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>"
        f"<friendlyName>{esc(ip)} - {esc(model)} Media Server</friendlyName>"
        "<manufacturer>Sonos, Inc.</manufacturer>"
        "<manufacturerURL>http://www.sonos.com</manufacturerURL>"
        f"<modelNumber>{esc(cfg.model_number)}</modelNumber>"
        f"<modelDescription>Sonos {esc(model)} Media Server</modelDescription>"
        f"<modelName>{esc(model)}</modelName>"
        "<modelURL>http://www.sonos.com</modelURL>"
        f"<UDN>{ident.uuid_ms}</UDN>"
        f"{_service_list(ms_services)}"
        "</device>"
    )
    media_renderer = (
        "<device>"
        "<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>"
        f"<friendlyName>{esc(ip)} - {esc(model)} Media Renderer</friendlyName>"
        "<manufacturer>Sonos, Inc.</manufacturer>"
        "<manufacturerURL>http://www.sonos.com</manufacturerURL>"
        f"<modelNumber>{esc(cfg.model_number)}</modelNumber>"
        f"<modelDescription>Sonos {esc(model)} Media Renderer</modelDescription>"
        f"<modelName>{esc(model)}</modelName>"
        "<modelURL>http://www.sonos.com</modelURL>"
        f"<UDN>{ident.uuid_mr}</UDN>"
        f"{_service_list(mr_services)}"
        "</device>"
    )

    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<root xmlns="urn:schemas-upnp-org:device-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        "<device>"
        "<deviceType>urn:schemas-upnp-org:device:ZonePlayer:1</deviceType>"
        f"<friendlyName>{esc(friendly)}</friendlyName>"
        "<manufacturer>Sonos, Inc.</manufacturer>"
        "<manufacturerURL>http://www.sonos.com</manufacturerURL>"
        f"<modelNumber>{esc(cfg.model_number)}</modelNumber>"
        f"<modelDescription>Sonos {esc(model)}</modelDescription>"
        f"<modelName>{esc(model)}</modelName>"
        "<modelURL>http://www.sonos.com/products/zoneplayers</modelURL>"
        f"<softwareVersion>{esc(cfg.software_version)}</softwareVersion>"
        "<swGen>2</swGen>"
        "<hardwareVersion>1.20.1.6-1.1</hardwareVersion>"
        f"<serialNum>{esc(ident.serial)}</serialNum>"
        f"<MACAddress>{esc(ident.mac)}</MACAddress>"
        f"<UDN>{ident.uuid}</UDN>"
        f"{_icon_list(cfg.model_number)}"
        f"<minCompatibleVersion>{esc(cfg.min_compatible_version)}</minCompatibleVersion>"
        f"<legacyCompatibleVersion>{esc(cfg.legacy_compatible_version)}</legacyCompatibleVersion>"
        f"<displayVersion>{esc(cfg.software_version.split('-')[0])}</displayVersion>"
        f"<roomName>{esc(ctx.state.room_name)}</roomName>"
        f"<displayName>{esc(model)}</displayName>"
        "<zoneType>9</zoneType>"
        f"{_service_list(root_services)}"
        f"<deviceList>{media_server}{media_renderer}</deviceList>"
        "</device>"
        f"<URLBase>{ctx.base_url}/</URLBase>"
        "</root>"
    )
