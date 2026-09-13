"""ONE composer for every family of ratified YAML rows: seed, overlay, ADR-0036 algebra.

The ADR-0039 amendment refuses a fourth composer BY NAME. This module is why that refusal is
structural rather than a rule people follow — there is one walk, one replacement-by-key, one
duplicate-declaration error and one tombstone rule, and a new declaration family gets them by
passing its key field and its builder rather than by copying forty lines.

── WHY IT IS ITS OWN MODULE AND NOT A PARAMETER ON THE TASK-KIND ONE ───────────────────────
The composer began inside ``task_kinds`` because task kinds were the first family to need it.
Parameterising it there would have worked and would have been wrong: the next family would
``from iagent_mesh.task_kinds import compose``, which reads as though decisions are a kind of
task. **A shared mechanism named after its first caller is the same defect as a domain name in
a platform seed** — the boundary would be lexical (a comment saying "generic, despite the
module") rather than structural (nothing domain-shaped to import).

``task_kinds.compose`` keeps its exact signature and delegates here, so v0.8.0 callers are
untouched. That is what makes this a PATCH-COMPATIBLE addition rather than another break.

── WHAT IS DELIBERATELY NOT PARAMETERISED ──────────────────────────────────────────────────
The FILE LAYOUT: one document per file, ``*.yaml``, keyed by a top-level field. A family that
wanted several documents per file would get the composer's refusal instead
(``expected a single document in the stream``), and that refusal is the good outcome — silently
taking the first document would give a family four missing rows and a green seal. Measured: a
lane wrote five kinds into one file separated by ``---`` and the error surfaced in seconds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

__all__ = [
    "DeclarationError",
    "read_rows",
    "load_rows",
    "compose_rows",
]

T = TypeVar("T")


class DeclarationError(ValueError):
    """A ratified row is invalid. Always names the FILE, because "a declaration is invalid" is
    not actionable at merge time and naming the file is what makes it fixable without a bisect.

    Families subclass this so a caller can catch their own family's failures specifically while
    a rail that composes several can catch the base.
    """


def read_rows(
    directory: Path | str,
    *,
    key_field: str,
    error: type[DeclarationError] = DeclarationError,
) -> dict[str, tuple[Path, dict]]:
    """Raw YAML by key, BEFORE validation — so a tombstone can be seen for what it is.

    Unvalidated on purpose: a tombstone carries only its key and ``deleted: true``, so building
    it as a full row would refuse the very thing composition needs to read.
    """
    import yaml

    rows: dict[str, tuple[Path, dict]] = {}
    for f in sorted(Path(directory).glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        if raw is None:
            raise error(f"{f.name} is empty — an empty ratified row is not a row")
        key = raw.get(key_field)
        if not key:
            raise error(f"{f.name} has no {key_field}")
        if key in rows:
            raise error(
                f"{f.name} and {rows[key][0].name} both declare {key_field} {key!r}"
            )
        rows[key] = (f, raw)
    return rows


def _build(fname: str, raw: dict, builder: Callable[[dict], T], label: str,
           error: type[DeclarationError]) -> T:
    try:
        return builder(raw)
    except error:
        raise
    except Exception as exc:  # noqa: BLE001 — re-raised with the file named
        raise error(f"{fname} is not a valid {label}: {exc}") from exc


def load_rows(
    directory: Path | str,
    *,
    key_field: str,
    builder: Callable[[dict], T],
    label: str = "declaration",
    error: type[DeclarationError] = DeclarationError,
) -> list[T]:
    """Every ratified row in ONE directory, validated, sorted by key.

    RAISES on an invalid row rather than skipping it. A consumer that skipped one would come up
    healthy and be missing exactly one row — the failure mode with no symptom.

    A TOMBSTONE HERE IS AN ERROR, not a no-op: ``deleted: true`` only means something composed
    against a seed, and a tombstone sitting in a seed directory is a row someone believes they
    removed and did not.
    """
    rows = read_rows(directory, key_field=key_field, error=error)
    out: list[T] = []
    for key in sorted(rows):
        f, raw = rows[key]
        if raw.get("deleted"):
            raise error(
                f"{f.name} is a tombstone (deleted: true) but this is not an overlay — "
                f"a tombstone only means something composed against a seed. Delete the file."
            )
        out.append(_build(f.name, raw, builder, label, error))
    return out


def compose_rows(
    seed_dir: Path | str,
    overlay_dirs: Iterable[Path | str] = (),
    *,
    key_field: str,
    builder: Callable[[dict], T],
    label: str = "declaration",
    error: type[DeclarationError] = DeclarationError,
) -> list[T]:
    """ADR-0036 composition: overlay entries REPLACE or DELETE by key; seed applies where the
    overlay is silent. Per-entry granularity, which is what makes deletion natural.

    An overlay row is a FULL REPLACEMENT, not a field-level merge. ADR-0036 leaves field-level
    merge for "a real overlay [that] shows whether it is ever wanted", and adding it early would
    mean a customer's row silently inheriting a seed field they never read.

    A TOMBSTONE FOR A KEY THE SEED DOES NOT SHIP IS AN ERROR, not a no-op. A stale tombstone is
    how an overlay rots: it keeps deleting a key nobody ships while the row it meant to remove
    returns under a new name with nothing to say so.
    """
    rows = read_rows(seed_dir, key_field=key_field, error=error)
    for od in overlay_dirs:
        for key, (f, raw) in read_rows(od, key_field=key_field, error=error).items():
            if raw.get("deleted"):
                if key not in rows:
                    raise error(
                        f"{f.name} deletes {key_field} {key!r}, which the seed does not ship. "
                        f"A tombstone for a row that is not there silently stops deleting "
                        f"anything the day the seed renames it."
                    )
                rows.pop(key)
            else:
                rows[key] = (f, raw)
    return [_build(rows[k][0].name, rows[k][1], builder, label, error) for k in sorted(rows)]
