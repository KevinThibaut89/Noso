"""Small XML helpers shared across the UPnP/SOAP/GENA layers.

Everything here is standard-library only. Sonos leans heavily on
*doubly-encoded* XML (a whole XML document escaped and carried as the text of
another XML element — e.g. ``ZoneGroupState`` and GENA ``LastChange``), so the
escape/unescape helpers below are load-bearing, not incidental.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _escape
from xml.sax.saxutils import unescape as _unescape

# Attribute values additionally need quotes escaped; element text does not.
_ATTR_ENTITIES = {'"': "&quot;"}
_UNESCAPE_ENTITIES = {"&quot;": '"', "&apos;": "'"}


def xml_escape(text: str) -> str:
    """Escape ``&``, ``<``, ``>`` for use as element text."""
    return _escape(text or "")


def attr_escape(text: str) -> str:
    """Escape a string for use inside a double-quoted XML attribute."""
    return _escape(text or "", _ATTR_ENTITIES)


def xml_unescape(text: str) -> str:
    """Reverse :func:`xml_escape` / attribute escaping."""
    return _unescape(text or "", _UNESCAPE_ENTITIES)


def attrs(pairs: dict[str, object]) -> str:
    """Render an attribute dict as ``key="escaped-value"`` pairs.

    ``None`` values are skipped; everything else is stringified. Order is
    preserved so output diffs stably against a captured real-speaker document.
    """
    out = []
    for key, value in pairs.items():
        if value is None:
            continue
        out.append(f'{key}="{attr_escape(str(value))}"')
    return " ".join(out)
