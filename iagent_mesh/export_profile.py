"""The shared export-profile header — one shape three independently-evolved producers each
return under their own ``header()`` method with slightly different field sets.

``AnswerExportProfile.header()`` (PR #148) and ``ExportProfile.header()`` (PR #144/#143) both
return ``{name, format, scope, label}``. ``Profile.header()`` (lane/01's ingest-review export,
PR #151/#158) returns ``{name, format, granularity, label}`` DELIBERATELY — the existing ruling
is that ``scope`` and ``granularity`` are different axes that need not converge (see the
policy-exports packet, ``scope`` answering "who can see this" and ``granularity`` answering "how
finely is this export cut"). The architect's 2026-10-30 directive names this SDK type's exact
field list as ``name, format, granularity, label, kinds`` — ``granularity`` (not ``scope``) is
the axis this module canonicalizes. A producer still using ``scope`` for its own axis is
unaffected: this type does not replace that producer's own type, it is the new shared
declaration for producers that want one.

``kinds`` rides as DATA here (the set of content kinds this export's rows cover) per the
generic-at-birth standing rule — it is a header field naming WHAT the export covers, not a route
or branch per kind.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

__all__ = [
    "ExportProfileHeader",
]


class ExportProfileHeader(BaseModel):
    """The shared shape of an export's header — ``name``/``format``/``granularity``/``label``,
    plus ``kinds``, generalized from three producers' own ``header()`` methods (see the module
    docstring for the field-set history and the architect's 2026-10-30 directive naming this
    exact list)."""

    name: str
    format: str
    """The export's file/wire format, e.g. ``"csv"``, ``"xlsx"``, ``"pdf"``. Open string, not a
    closed ``Literal``, deliberately: new export formats are a config/registry row, not an SDK
    release, per the architect's 2026-10-30 generic-at-birth checklist (test 2: a new case must
    be reachable by adding a row, not a branch)."""

    granularity: str
    """How finely this export is cut, e.g. ``"notice_part"``, ``"notice"`` in cortex-ui's current
    usage — same open-string reasoning as :attr:`format`. The SDK does not enumerate or validate
    against that set; a producer's own registry does."""

    label: Optional[str] = None
    """Human-readable display name for this export profile; ``None`` means no display name
    declared, same optional-with-no-exceptions precedent :attr:`ContentKindRegistration.label`
    already set (``iagent_mesh/ingest.py``)."""

    kinds: tuple[str, ...] = ()
    """The content kinds this export's rows cover, e.g. ``("pcn", "pdn")`` — carried as DATA on
    the header, never as a route or branch per kind, per generic-at-birth."""
