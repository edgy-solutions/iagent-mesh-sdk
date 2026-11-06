"""`ExportProfileHeader` generalizes a header shape three independently-evolved producers each
return under their own `header()` method with a slightly different field set (see the module
docstring for the field-set history). This suite covers the shape itself: a valid construction,
the two optional-with-defaults fields, and the open-vocabulary design of `format`/`granularity`
— the architect's 2026-10-30 directive is that neither is a closed set the SDK validates
against, same "ruled optional/open, not required/closed" precedent `iagent_mesh.ingest`'s own
fields already drew.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from iagent_mesh.export_profile import (
    ExportProfileHeader,
    ExportProfileSource,
    compose_export_profiles,
)


def test_a_valid_header_builds_with_all_fields():
    header = ExportProfileHeader(
        name="pcn-export",
        format="csv",
        granularity="notice",
        label="PCN Export",
        kinds=("pcn", "pdn"),
    )
    assert header.name == "pcn-export"
    assert header.format == "csv"
    assert header.granularity == "notice"
    assert header.label == "PCN Export"
    assert header.kinds == ("pcn", "pdn")


def test_label_and_kinds_default():
    header = ExportProfileHeader(name="pcn-export", format="csv", granularity="notice")
    assert header.label is None
    assert header.kinds == ()


def test_format_and_granularity_are_an_open_vocabulary_not_a_closed_enum():
    """Neither `format` nor `granularity` is restricted to any particular set — a new export
    format or a new granularity level is a fact this module has no business refusing to hold,
    same reasoning `iagent_mesh.ingest.ContentKindRegistration.arrives_as` already draws."""
    header = ExportProfileHeader(name="x", format="a-brand-new-format", granularity="notice_part")
    assert header.format == "a-brand-new-format"
    assert header.granularity == "notice_part"


# ── v0.9.13: compose_export_profiles — the converged seed/overlay/tombstone loader ─────────
#
# `_write` mirrors `tests/test_declarations.py`'s own helper (one YAML document per file, the
# file layout `declarations.compose_rows` hard-codes) rather than inventing a second fixture
# shape for the same composer.


def _write(d: Path, name: str, row: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(row), encoding="utf-8")


def _source(tmp_path: Path, **overrides) -> ExportProfileSource:
    defaults = dict(
        kind="review-export",
        seed_env="UNUSED_SEED_ENV_FOR_THIS_TEST",
        seed_default=str(tmp_path / "seed"),
        overlay_env="UNUSED_OVERLAY_ENV_FOR_THIS_TEST",
    )
    defaults.update(overrides)
    return ExportProfileSource(**defaults)


def test_seed_only_composition(tmp_path):
    seed = tmp_path / "seed"
    _write(seed, "a.yaml", {"name": "pcn-export", "format": "csv"})
    _write(seed, "b.yaml", {"name": "pdn-export", "format": "xlsx"})

    source = _source(tmp_path)
    profiles = compose_export_profiles(source, overlay_dirs=[])

    assert set(profiles) == {"pcn-export", "pdn-export"}
    assert profiles["pcn-export"]["format"] == "csv"


def test_overlay_replaces_a_same_named_profile(tmp_path):
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", {"name": "pcn-export", "format": "csv"})
    _write(overlay, "a.yaml", {"name": "pcn-export", "format": "xlsx"})

    source = _source(tmp_path)
    profiles = compose_export_profiles(source, overlay_dirs=[str(overlay)])

    assert profiles["pcn-export"]["format"] == "xlsx", (
        "the overlay row must fully replace the seed row, not merge into it"
    )


def test_overlay_tombstones_a_seed_profile(tmp_path):
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", {"name": "pcn-export", "format": "csv"})
    _write(seed, "b.yaml", {"name": "pdn-export", "format": "xlsx"})
    _write(overlay, "a.yaml", {"name": "pcn-export", "deleted": True})

    source = _source(tmp_path)
    profiles = compose_export_profiles(source, overlay_dirs=[str(overlay)])

    assert "pcn-export" not in profiles, "a tombstone must remove the name from the final set"
    assert "pdn-export" in profiles, "a tombstone must not affect a name it does not name"


def test_missing_seed_directory_falls_back_to_seed_default(tmp_path):
    """`seed_env` is unset in the environment, so the composer falls back to
    `source.seed_default` — and that default directory need not even exist on disk yet
    (`declarations.read_rows` globs a directory that may be missing; it is not an error)."""
    missing_seed = tmp_path / "seed-not-created"
    assert not missing_seed.exists()

    source = ExportProfileSource(
        kind="review-export",
        seed_env="UNUSED_SEED_ENV_FOR_THIS_TEST",
        seed_default=str(missing_seed),
        overlay_env="UNUSED_OVERLAY_ENV_FOR_THIS_TEST",
    )
    profiles = compose_export_profiles(source, overlay_dirs=[])

    assert profiles == {}


def test_overlay_env_is_os_pathsep_delimited(tmp_path, monkeypatch):
    """The `overlay_env` value is parsed as `os.pathsep`-delimited when `overlay_dirs` is not
    passed explicitly — this repo's own flagged guess (see the module docstring in
    `iagent_mesh/export_profile.py`), exercised here so the behavior it documents is real."""
    seed = tmp_path / "seed"
    overlay_1 = tmp_path / "overlay1"
    overlay_2 = tmp_path / "overlay2"
    _write(seed, "a.yaml", {"name": "pcn-export", "format": "csv"})
    _write(overlay_1, "a.yaml", {"name": "pcn-export", "format": "xlsx"})
    _write(overlay_2, "b.yaml", {"name": "pdn-export", "format": "pdf"})

    monkeypatch.setenv(
        "TEST_EXPORT_PROFILE_OVERLAY_DIRS",
        os.pathsep.join([str(overlay_1), str(overlay_2)]),
    )
    source = ExportProfileSource(
        kind="review-export",
        seed_env="UNUSED_SEED_ENV_FOR_THIS_TEST",
        seed_default=str(seed),
        overlay_env="TEST_EXPORT_PROFILE_OVERLAY_DIRS",
    )
    profiles = compose_export_profiles(source)

    assert profiles["pcn-export"]["format"] == "xlsx"
    assert profiles["pdn-export"]["format"] == "pdf"
