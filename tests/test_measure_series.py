"""`MeasureSeries`/`MeasureSeriesReference` — Fork A1, ruled 2026-11-05 (see the module docstring
for the packet). This suite covers the declared-series shape, the reference's exactly-one-of
`value`/`series` rule, and that `cumulative` is a plain bool fact with no computed behavior.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.measure_series import MeasureSeries, MeasureSeriesReference


def test_a_declared_series_builds_with_all_fields():
    series = MeasureSeries(key="bcws", label="BCWS", unit="USD", cumulative=True)
    assert series.key == "bcws"
    assert series.label == "BCWS"
    assert series.unit == "USD"
    assert series.cumulative is True


def test_unit_and_cumulative_default():
    series = MeasureSeries(key="bcws", label="BCWS")
    assert series.unit is None
    assert series.cumulative is False


def test_a_reference_by_constant_value():
    ref = MeasureSeriesReference(label="BAC", value=100_000.0)
    assert ref.label == "BAC"
    assert ref.value == 100_000.0
    assert ref.series is None


def test_a_reference_by_declared_series_key():
    """The census's own worked example: BAC served from data rather than declared as a
    constant in the row."""
    ref = MeasureSeriesReference(series="bac", label="BAC")
    assert ref.series == "bac"
    assert ref.value is None


def test_a_reference_with_neither_value_nor_series_is_refused():
    with pytest.raises(ValidationError):
        MeasureSeriesReference(label="BAC")


def test_a_reference_with_both_value_and_series_is_refused():
    with pytest.raises(ValidationError):
        MeasureSeriesReference(label="BAC", value=1.0, series="bac")


def test_an_unknown_field_is_refused_on_both_models():
    with pytest.raises(ValidationError):
        MeasureSeries(key="bcws", label="BCWS", extra_field="nope")
    with pytest.raises(ValidationError):
        MeasureSeriesReference(label="BAC", value=1.0, extra_field="nope")
