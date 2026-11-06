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

import os
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from .declarations import DeclarationError, compose_rows

__all__ = [
    "ExportProfileHeader",
    "ExportProfileSource",
    "ExportProfileError",
    "compose_export_profiles",
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


# ── v0.9.13: the converged export-profile loader (gov's 2026-10-30 packet) ─────────────────
#
# Three engines (review export, answer export, fin CDRL) each hand-rolled the same seed-then-
# overlay, replace-by-name, tombstone-by-name mechanism, differing only in their env var names,
# default seed path and a kind label. The architect's ruling (2026-10-30, via Chris): "yes, one
# function; source rows live in a policy file both the validator and engines share."
#
# This does NOT invent a fourth composer. ``iagent_mesh.declarations`` already IS that one
# composer — its own docstring records "the ADR-0039 amendment refuses a fourth composer BY
# NAME" — so this is a thin, kind-agnostic wrapper over ``declarations.compose_rows``, not a
# new seed/overlay/tombstone mechanism. That also fixes the file format and the tombstone
# convention without guessing: ``compose_rows`` hard-codes one YAML document per file (not
# parameterized — see its module docstring) and a tombstone is a row carrying only its key
# field plus ``deleted: true``. Both are pre-existing repo-wide conventions, reused here
# exactly, not new choices made for this function.
#
# What IS a guess, pending gov's confirmation: the ``overlay_env`` value is documented by gov's
# packet only as "a list of paths" with no delimiter named, and there is no existing SDK
# precedent for parsing an overlay-dirs *environment variable* (``declarations.compose_rows``
# takes ``overlay_dirs`` as a Python argument, already split). Treated here as ``os.pathsep``-
# delimited, the conventional choice for a path-list env var on POSIX/Windows alike (``:`` vs
# ``;``) — flag this with gov before any engine switches its own loader to call this function.


class ExportProfileError(DeclarationError):
    """An export-profile row is invalid; see ``DeclarationError``. A family subclass (same
    pattern as ``task_kinds.TaskKindError``) so a caller can catch export-profile composition
    failures specifically, without catching every declaration family's."""


class ExportProfileSource(BaseModel):
    """A declared *source* for one export kind's profile set — ``{kind, seed_env, seed_default,
    overlay_env}``, exactly gov's packet's field list. One row per export kind (review export,
    answer export, fin CDRL, or any future kind); rows live in a policy file both the validator
    and each engine's loader read, per the architect's ruling, not as per-engine declarations.

    ``kind`` is an open ``str``, deliberately not a ``Literal``/``Enum`` of the three named
    kinds — per this repo's generic-at-birth standing rule, a fourth export kind must be
    reachable by adding a row, not by an SDK release that enumerates it."""

    model_config = ConfigDict(frozen=True)

    kind: str
    """Which export kind this source composes for, e.g. ``"review-export"`` — carried as DATA
    for the caller's own registry to key on; this module does not branch on it."""

    seed_env: str
    """The environment variable naming the seed directory, e.g. ``"INGEST_EXPORT_PROFILE_DIR"``."""

    seed_default: str
    """The seed directory used when ``seed_env`` is unset in the environment."""

    overlay_env: str
    """The environment variable naming the overlay directories (see the module-level note
    above on the delimiter convention), e.g. ``"EXPORT_PROFILE_OVERLAY_DIRS"``."""


def _export_profile_row(raw: dict) -> dict[str, Any]:
    """The identity builder: a composed export profile is returned as its raw declared fields,
    not forced into ``ExportProfileHeader`` or any other fixed shape. The three engines' own
    profile rows carry different field sets beyond ``name`` (``format``/``scope``/``label`` for
    some, others besides) — this module's job is composition (seed, overlay, replace,
    tombstone), not validating what a profile row itself must contain. A caller that wants a
    typed row still can: pass its own ``builder`` by calling ``declarations.compose_rows``
    directly with this function's resolved seed/overlay directories."""
    return dict(raw)


def compose_export_profiles(
    source: ExportProfileSource,
    *,
    overlay_dirs: Optional[list[str]] = None,
) -> dict[str, dict[str, Any]]:
    """Compose one export kind's profile set from a declared ``ExportProfileSource``.

    Reads the seed directory from ``os.environ.get(source.seed_env, source.seed_default)``,
    then each overlay directory in order from ``os.environ.get(source.overlay_env)`` (see the
    module-level note above: treated as ``os.pathsep``-delimited, a flagged guess) unless the
    caller passes ``overlay_dirs`` explicitly — e.g. ``validate_policy.py`` running offline in
    CI, which gov's packet names as the reason the source rows live in a file both sides read
    rather than being served.

    A later directory's same-named profile fully REPLACES the earlier one (never a field-level
    merge — same ADR-0036 reasoning ``declarations.compose_rows`` already draws); a tombstone
    (a row with only its ``name`` and ``deleted: true``) REMOVES that name from the set. The
    profile's identity is its ``name`` field, per gov's packet.

    A missing seed directory is not an error — it composes to no seed rows, same as an empty
    one (``declarations.read_rows`` globs ``*.yaml`` in a directory that may not exist).

    Returns a ``dict`` keyed by profile ``name`` rather than ``ExportProfileHeader`` rows: the
    three engines' profiles do not share one field set beyond ``name``, so forcing them into
    this module's existing header shape would either drop fields or require ``extra="allow"``
    on a type that elsewhere forbids it. See ``_export_profile_row`` for a caller that wants a
    typed row.
    """
    seed_dir = os.environ.get(source.seed_env, source.seed_default)

    if overlay_dirs is None:
        raw_overlay = os.environ.get(source.overlay_env)
        # GUESS pending gov's confirmation (see the module-level note above): os.pathsep-
        # delimited, e.g. "dir1:dir2" on POSIX or "dir1;dir2" on Windows.
        overlay_dirs = raw_overlay.split(os.pathsep) if raw_overlay else []

    rows = compose_rows(
        seed_dir,
        overlay_dirs,
        key_field="name",
        builder=_export_profile_row,
        label="export profile",
        error=ExportProfileError,
    )
    return {row["name"]: row for row in rows}
