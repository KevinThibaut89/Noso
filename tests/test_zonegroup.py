import xml.etree.ElementTree as ET

from noso.zonegroup import build_zone_group_state
from tests.conftest import build_context


def test_zone_group_state_structure():
    ctx, _ = build_context(1400, room="Kitchen")
    doc = build_zone_group_state(ctx)
    root = ET.fromstring(doc)  # well-formed
    assert root.tag == "ZoneGroupState"

    member = root.find(".//ZoneGroupMember")
    assert member.get("ZoneName") == "Kitchen"
    assert member.get("UUID") == ctx.identity.rincon
    assert member.get("Location") == f"{ctx.base_url}/xml/device_description.xml"
    assert member.get("Invisible") == "0"

    group = root.find(".//ZoneGroup")
    assert group.get("Coordinator") == ctx.identity.rincon


def test_zone_name_escaped():
    ctx, _ = build_context(1400, room="Rock & Roll")
    doc = build_zone_group_state(ctx)
    # Must remain well-formed with an ampersand in the name.
    member = ET.fromstring(doc).find(".//ZoneGroupMember")
    assert member.get("ZoneName") == "Rock & Roll"
