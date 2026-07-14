from noso.mdns import instance_name, sonos_txt
from tests.conftest import build_context


def test_instance_name_matches_real_format():
    ctx, _ = build_context(1400, room="Test Room")
    # Real speakers advertise RINCON_<mac>01400@<RoomName> (verified via capture).
    assert instance_name(ctx) == "RINCON_000E58A1B2C301400@Test Room"


def test_sonos_txt_records():
    ctx, _ = build_context(1400)
    ctx.ip = "192.168.1.9"
    txt = sonos_txt(ctx)
    assert txt["info"] == "/api/v1/players/RINCON_000E58A1B2C301400/info"
    assert txt["hhid"] == "Sonos_testhousehold"
    assert txt["sslport"] == "1443"
    assert txt["hhsslport"] == "1843"
    assert txt["location"] == "http://192.168.1.9:1400/xml/device_description.xml"
    assert txt["bootseq"] == "1"


def test_household_override():
    ctx, _ = build_context(1400)
    ctx.config.household = "Sonos_customhh"
    assert sonos_txt(ctx)["hhid"] == "Sonos_customhh"
    assert sonos_txt(ctx)["mhhid"] == "Sonos_customhh.0"
