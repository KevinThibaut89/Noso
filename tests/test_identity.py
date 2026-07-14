from pathlib import Path

from noso.identity import Identity, load_or_create


def test_udn_and_derivations():
    ident = Identity(node="A1B2C3", household="Sonos_x", boot_seq=1)
    assert ident.uuid == "uuid:RINCON_000E58A1B2C301400"
    assert ident.rincon == "RINCON_000E58A1B2C301400"
    assert ident.uuid_ms == "uuid:RINCON_000E58A1B2C301400_MS"
    assert ident.uuid_mr == "uuid:RINCON_000E58A1B2C301400_MR"
    assert ident.mac == "00:0E:58:A1:B2:C3"
    assert ident.serial == "00-0E-58-A1-B2-C3:E"


def test_persist_and_bump_boot_seq(tmp_path: Path):
    path = tmp_path / "identity.json"
    first = load_or_create(path)
    second = load_or_create(path)
    assert first.node == second.node  # stable identity
    assert first.household == second.household
    assert second.boot_seq == first.boot_seq + 1  # bumped each start


def test_generated_uuid_shape(tmp_path: Path):
    ident = load_or_create(tmp_path / "id.json")
    assert ident.uuid.startswith("uuid:RINCON_000E58")
    assert ident.uuid.endswith("01400")
    assert len(ident.rincon) == len("RINCON_000E58A1B2C301400")
