import xml.etree.ElementTree as ET

from noso.scpd import scpd_for
from tests.conftest import build_context

NS = "{urn:schemas-upnp-org:service-1-0}"


def test_all_scpds_valid_and_self_consistent():
    """Every generated SCPD must be well-formed and — critically — declare a
    state variable for every argument's relatedStateVariable, or SoCo's parser
    KeyErrors and the action becomes uncallable.
    """
    ctx, services = build_context(1400)
    for svc in services:
        tree = ET.fromstring(scpd_for(svc))
        state_vars = {v.findtext(f"{NS}name") for v in tree.iter(f"{NS}stateVariable")}
        actions = list(tree.iter(f"{NS}action"))
        assert actions, f"{svc.service_type} has no actions"
        for action in actions:
            for arg in action.iter(f"{NS}argument"):
                related = arg.findtext(f"{NS}relatedStateVariable")
                assert related in state_vars, f"{svc.service_type}: {related} undeclared"


def test_scpd_lists_expected_actions():
    ctx, services = build_context(1400)
    by_type = {s.service_type: s for s in services}
    rc = by_type["urn:schemas-upnp-org:service:RenderingControl:1"]
    tree = ET.fromstring(scpd_for(rc))
    names = {a.findtext(f"{NS}name") for a in tree.iter(f"{NS}action")}
    assert {"GetVolume", "SetVolume", "GetMute", "SetMute"} <= names
