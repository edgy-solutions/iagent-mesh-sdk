"""The DISTRIBUTION is correct — asserted against the built artifact, not the source tree.

Every other test in this repo runs from a source checkout, which is precisely the environment
where the packaging bug this file exists to prevent is INVISIBLE: `scaffold_core` resolved
templates as `<its own dir>/../templates`, which exists in a checkout and does not exist in
site-packages. The wheel carried only `iagent_mesh/`, so a `pip install`ed SDK raised

    FileNotFoundError: .../site-packages/templates

on the first scaffold, while the suite stayed green. A test suite that only ever runs from the
repo cannot see what users receive.

These cases are cheap and static (they read `pyproject.toml` and, when present, the built
wheel). The wheel case SKIPS when `dist/` is absent rather than silently passing — and CI
additionally asserts the same property directly against the artifact it is about to publish, so
the check does not depend on a developer having run `uv build` first.
"""
from __future__ import annotations

import glob
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover — py<3.11
        import tomli as tomllib
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Metadata PyPI requires (or that a consumer reads on the project page)
# ---------------------------------------------------------------------------
def test_pypi_metadata_is_complete():
    """The fields absent before 0.4.0, each of which degrades the release rather than blocking it.

    A missing `readme` publishes a package with a blank description page; a missing `license`
    shows "UNKNOWN"; missing `classifiers` drops it out of PyPI's filters. None of these fail
    the upload, which is why they need asserting rather than discovering.
    """
    proj = _pyproject()["project"]
    for field in ("name", "version", "description", "readme", "license",
                  "authors", "keywords", "classifiers", "requires-python"):
        assert proj.get(field), f"pyproject [project].{field} is missing or empty"

    assert (ROOT / proj["readme"]).is_file(), f"readme file {proj['readme']} does not exist"
    for pattern in _pyproject()["project"].get("license-files", []):
        assert list(ROOT.glob(pattern)), f"license-files pattern {pattern!r} matches nothing"


def test_license_file_exists_and_is_not_a_stub():
    lic = ROOT / "LICENSE"
    assert lic.is_file(), "LICENSE missing — `license-files` would fail the build"
    text = lic.read_text(encoding="utf-8")
    assert "MIT License" in text and "Copyright" in text


def test_urls_point_at_this_repository():
    urls = _pyproject()["project"].get("urls", {})
    assert urls, "[project.urls] missing — the PyPI page would link nowhere"
    assert any("iagent-mesh-sdk" in u for u in urls.values()), urls


def test_requires_python_matches_the_dependency_floor():
    """`mcp` needs >=3.10. Declaring >=3.9 made the project's own requirements unsatisfiable."""
    assert _pyproject()["project"]["requires-python"].startswith(">=3.10")


def test_the_template_catalogue_is_mapped_into_the_package():
    """The force-include that puts templates inside the wheel.

    Asserted on configuration as well as on the artifact, so the reason survives: a wheel
    without this mapping installs and imports perfectly and fails only at the first scaffold.
    """
    cfg = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]
    inc = cfg.get("force-include", {})
    assert inc.get("templates") == "iagent_mesh/templates", (
        "templates are no longer mapped into the package — scaffolding will raise "
        f"FileNotFoundError from an installed distribution; force-include = {inc}"
    )


# ---------------------------------------------------------------------------
# The built artifact itself
# ---------------------------------------------------------------------------
def _wheel() -> str | None:
    found = glob.glob(str(ROOT / "dist" / "*.whl"))
    return found[0] if found else None


@pytest.mark.skipif(_wheel() is None,
                    reason="no wheel in dist/ — run `uv build` (CI checks the artifact directly)")
def test_the_built_wheel_carries_the_templates():
    names = zipfile.ZipFile(_wheel()).namelist()
    tpl = [n for n in names if n.startswith("iagent_mesh/templates/")]
    assert tpl, (
        f"{_wheel()} carries no iagent_mesh/templates/ — this is the exact wheel a user would "
        "install, and scaffolding from it would raise FileNotFoundError"
    )
    # Every template directory in the repo must be present, not just one.
    shipped = {n.split("/")[2] for n in tpl if len(n.split("/")) > 3}
    on_disk = {d.name for d in (ROOT / "templates").iterdir() if d.is_dir()}
    assert shipped == on_disk, f"wheel templates {shipped} != repo templates {on_disk}"


@pytest.mark.skipif(_wheel() is None, reason="no wheel in dist/ — run `uv build`")
def test_the_wheel_does_not_leak_a_toplevel_templates_directory():
    """Mapped INTO the package, never top-level: `site-packages/templates/` is a name collision
    waiting for any other distribution that ships templates."""
    names = zipfile.ZipFile(_wheel()).namelist()
    assert not [n for n in names if n.startswith("templates/")], (
        "wheel installs a top-level `templates/` into site-packages"
    )


def test_every_graph_manifest_export_is_reachable_from_the_PACKAGE():
    """A name in `graph_manifest.__all__` must import from `iagent_mesh` too. DERIVED.

    v0.7.0 shipped `enforce_refusal`, `ref_basis`, `RefusalViolation` and `REF_COSMETIC` in the
    submodule's `__all__` and NOT in the package's re-exports, while all six names that predate
    them ARE top-level. So a consumer following the established idiom — `from iagent_mesh import
    compose, GraphManifest` — would not find the new ones.

    **That is the very problem 0.7.0 existed to fix, in 0.7.0 itself:** the release moved
    `enforce_refusal` here so a route-C host could inherit it, and then did not put it where
    that host would look. Half-wired exports are invisible to the module's own tests, which
    import from the submodule.

    Derived from `__all__` rather than listed, so the next export is covered by writing nothing.
    """
    from iagent_mesh import graph_manifest

    import iagent_mesh

    missing = [n for n in graph_manifest.__all__ if not hasattr(iagent_mesh, n)]
    assert not missing, (
        "these are exported by iagent_mesh.graph_manifest but NOT re-exported by the package, "
        "so a consumer using the documented import idiom cannot reach them:\n  "
        + "\n  ".join(missing)
    )
