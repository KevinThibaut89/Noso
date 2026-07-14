"""Service Control Protocol Definition (SCPD) serving.

Fidelity path: drop a real speaker's SCPD XML into ``assets/scpd/`` (see
``tools/capture_real_speaker.sh``) and it is served verbatim.

Fallback: generate a valid SCPD from the service's ``ACTIONS`` spec — a compact
``name -> (in_args, out_args)`` mapping. The generated document includes a full
``argumentList`` per action and a ``serviceStateTable`` declaring every
referenced variable, because real controllers (SoCo, and the app) parse the
SCPD to learn an action's arguments and *refuse to call actions they can't find
there*. A name-only SCPD is not enough.
"""

from __future__ import annotations

from pathlib import Path

from .services.base import Service

ASSETS_SCPD = Path(__file__).parent / "assets" / "scpd"


def static_scpd(scpd_asset: str) -> bytes | None:
    if not scpd_asset:
        return None
    try:
        return (ASSETS_SCPD / scpd_asset).read_bytes()
    except OSError:
        return None


def _argument(name: str, direction: str) -> str:
    return (
        "<argument>"
        f"<name>{name}</name>"
        f"<direction>{direction}</direction>"
        f"<relatedStateVariable>A_ARG_TYPE_{name}</relatedStateVariable>"
        "</argument>"
    )


def generate_scpd(service: Service) -> bytes:
    actions_spec = getattr(service, "ACTIONS", None) or {
        name: ([], []) for name in service.handlers
    }

    arg_vars: dict[str, str] = {}
    action_blocks: list[str] = []
    for name, (in_args, out_args) in actions_spec.items():
        arg_xml = []
        for arg in in_args:
            arg_vars.setdefault(f"A_ARG_TYPE_{arg}", "string")
            arg_xml.append(_argument(arg, "in"))
        for arg in out_args:
            arg_vars.setdefault(f"A_ARG_TYPE_{arg}", "string")
            arg_xml.append(_argument(arg, "out"))
        action_blocks.append(
            f"<action><name>{name}</name><argumentList>{''.join(arg_xml)}</argumentList></action>"
        )

    state_vars = [
        f'<stateVariable sendEvents="yes"><name>{ev}</name>'
        "<dataType>string</dataType></stateVariable>"
        for ev in service.event_state()
    ]
    state_vars += [
        f'<stateVariable sendEvents="no"><name>{var}</name>'
        f"<dataType>{dtype}</dataType></stateVariable>"
        for var, dtype in arg_vars.items()
    ]
    if not state_vars:
        state_vars.append(
            '<stateVariable sendEvents="no"><name>A_ARG_TYPE_Result</name>'
            "<dataType>string</dataType></stateVariable>"
        )

    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<scpd xmlns="urn:schemas-upnp-org:service-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        f"<actionList>{''.join(action_blocks)}</actionList>"
        f"<serviceStateTable>{''.join(state_vars)}</serviceStateTable>"
        "</scpd>"
    ).encode("utf-8")


def scpd_for(service: Service) -> bytes:
    """SCPD bytes: a real/static asset if present, else generated from ACTIONS."""
    return static_scpd(service.scpd_asset) or generate_scpd(service)
