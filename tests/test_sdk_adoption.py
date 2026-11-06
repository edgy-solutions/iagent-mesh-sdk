"""Tests for ``iagent_mesh.sdk_adoption`` — the reusable SDK-adoption drift check.

Covers:
- A fixture package that hand-copies an ``iagent_mesh``-exported type (local ``class``
  definition with a colliding name) is flagged, with the right file/line/name.
- A fixture package that only imports the name from ``iagent_mesh`` (never redefines it
  locally) is not flagged.
- Running the check against THIS repo's own ``iagent_mesh/`` tree finds zero hand-copies —
  the live self-test / "does it work on a real package" smoke test.
"""

from pathlib import Path

import pytest

import iagent_mesh
from iagent_mesh.sdk_adoption import (
    HandCopyFinding,
    assert_no_hand_copied_types,
    find_hand_copied_types,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_hand_copied_class_is_flagged(tmp_path: Path) -> None:
    fixture = tmp_path / "engine_with_hand_copy"
    fixture.mkdir()
    (fixture / "models.py").write_text(
        "class ResolveInstanceRequest:\n"
        "    identifier: str\n",
        encoding="utf-8",
    )

    findings = find_hand_copied_types(fixture)

    assert findings == [
        HandCopyFinding(
            path=fixture / "models.py",
            line=1,
            class_name="ResolveInstanceRequest",
        )
    ]
    with pytest.raises(AssertionError, match="ResolveInstanceRequest"):
        assert_no_hand_copied_types(fixture)


def test_imported_type_is_not_flagged(tmp_path: Path) -> None:
    fixture = tmp_path / "engine_without_hand_copy"
    fixture.mkdir()
    (fixture / "models.py").write_text(
        "from iagent_mesh import ResolveInstanceRequest\n"
        "\n"
        "def build(identifier):\n"
        "    return ResolveInstanceRequest(identifier=identifier)\n",
        encoding="utf-8",
    )

    assert find_hand_copied_types(fixture) == []
    assert assert_no_hand_copied_types(fixture) is None


def test_sdk_itself_has_zero_hand_copies() -> None:
    """Live self-test against this repo's own ``iagent_mesh/`` source tree: the SDK does not
    hand-copy its own types, so this must find zero findings against a real package."""
    package_root = REPO_ROOT / "iagent_mesh"
    assert package_root.is_dir()

    findings = find_hand_copied_types(package_root)

    assert findings == []
    assert assert_no_hand_copied_types(package_root) is None


def test_exports_are_reachable_from_the_package_root() -> None:
    assert iagent_mesh.find_hand_copied_types is find_hand_copied_types
    assert iagent_mesh.assert_no_hand_copied_types is assert_no_hand_copied_types
    assert iagent_mesh.HandCopyFinding is HandCopyFinding
