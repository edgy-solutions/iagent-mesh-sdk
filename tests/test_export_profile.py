"""`ExportProfileHeader` generalizes a header shape three independently-evolved producers each
return under their own `header()` method with a slightly different field set (see the module
docstring for the field-set history). This suite covers the shape itself: a valid construction,
the two optional-with-defaults fields, and the open-vocabulary design of `format`/`granularity`
— the architect's 2026-10-30 directive is that neither is a closed set the SDK validates
against, same "ruled optional/open, not required/closed" precedent `iagent_mesh.ingest`'s own
fields already drew.
"""
from __future__ import annotations

from iagent_mesh.export_profile import ExportProfileHeader


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
