"""The graph manifest is the `run_any_graph` refusal, so its refusals are the test.

ADR-0046 §2 refuses a generic graph runner by name. A rule people follow is not a refusal, so
what makes it one is that these models decline the shapes that reconstruct it — and this file
exists to prove they decline them, each for its own reason, with the valid row as the control.

A refusal suite with no positive control is the failure it is testing for: a model that raised
on everything would pass every assertion below.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from iagent_mesh.graph_manifest import (
    GraphManifest,
    ManifestError,
    compose,
    load_manifests,
    manifest_ref,
    registration_payload,
    validate_dir,
)

VALID = {
    "graph_id": "fin_program_brief",
    "module": "graphs.fin_program_brief",
    "verb": "mesh:finProgramBrief",
    "name": "engine_lg_program_brief",
    "description": "A grounded brief for one program.",
    "input_uri": "http://invincible-agent/fin#Program",
    "output_uri": "http://invincible-agent/mesh#StatefulSupportResponse",
    "domains": ["PROGRAM_FINANCE"],
    "slots": [{
        "name": "program_id", "kind": "spoken-mandatory", "type": "string",
        "required": True, "referent": "http://invincible-agent/fin#Program",
    }],
    "arity": "single",
    "refusal": "named-hole",
    "checkpointer": True,
}


def _row(**over):
    d = copy.deepcopy(VALID)
    d.update(over)
    return d


def test_the_valid_row_is_accepted():
    """POSITIVE CONTROL, first. Every refusal below is satisfied by a model that refuses
    everything; this is what distinguishes a discriminating validator from a broken one."""
    m = GraphManifest(**VALID)
    assert m.verb == "mesh:finProgramBrief"
    assert m.arity == "single"


@pytest.mark.parametrize(
    "label,mutate,expect",
    [
        # ADR-0046 §2 — run_any_graph reconstructed under another name
        ("payload:object slot",
         lambda d: d["slots"].append({"name": "payload", "kind": "spoken-optional",
                                      "type": "object"}), "untyped passthrough"),
        ("a slot merely NAMED body",
         lambda d: d["slots"].append({"name": "body", "kind": "spoken-optional",
                                      "type": "string"}), "untyped passthrough"),
        # the contract's own clauses
        ("arity omitted when a referent forces single",
         lambda d: d.pop("arity"), "declare arity: single"),
        ("input_uri as a CURIE",
         lambda d: d.update(input_uri="fin:Program"), "absolute class URI"),
        ("verb with no prefix",
         lambda d: d.update(verb="finProgramBrief"), "must be a CURIE"),
        ("referent on a handle slot",
         lambda d: d["slots"].append({"name": "h", "kind": "handle",
                                      "referent": "http://x#Y"}), "belongs on a SPOKEN slot"),
        ("an unmodelled field",
         lambda d: d.update(passthrough=True), "Extra inputs are not permitted"),
    ],
)
def test_each_refusal_fires_for_its_own_reason(label, mutate, expect):
    d = _row()
    mutate(d)
    with pytest.raises(Exception) as exc:
        GraphManifest(**d)
    assert expect in str(exc.value), f"{label}: refused, but not for the stated reason"


def test_ref_covers_the_contract_and_ignores_cosmetics():
    """`manifest_ref` says THIS CONTRACT. A reflowed description must not mint a new ref; a
    changed slot must."""
    base = manifest_ref(GraphManifest(**VALID))
    assert manifest_ref(GraphManifest(**_row(description="reworded entirely"))) == base
    assert manifest_ref(GraphManifest(**_row(cost_class="low"))) == base
    changed = _row()
    changed["slots"][0]["required"] = False
    changed["arity"] = "set"
    assert manifest_ref(GraphManifest(**changed)) != base


# ── ADR-0036 composition ──────────────────────────────────────────────────────────────────

def _write(d: Path, name: str, row: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(row, sort_keys=False), encoding="utf-8")


def test_overlay_replaces_by_key(tmp_path):
    seed, ov = tmp_path / "seed", tmp_path / "ov"
    _write(seed, "a.yaml", VALID)
    _write(ov, "a.yaml", _row(cost_class="low"))
    assert compose(seed)[0].cost_class == "medium"          # control: the seed value
    assert compose(seed, [ov])[0].cost_class == "low"


def test_overlay_can_DELETE_a_seeded_graph(tmp_path):
    """ADR-0036 §3c. Without this, the first customer who does not want a seeded graph
    registered in their mesh has to fork the seed."""
    seed, ov = tmp_path / "seed", tmp_path / "ov"
    _write(seed, "a.yaml", VALID)
    _write(ov, "a.yaml", {"graph_id": "fin_program_brief", "deleted": True})
    assert [m.graph_id for m in compose(seed)] == ["fin_program_brief"]   # control
    assert compose(seed, [ov]) == []


def test_a_stale_tombstone_is_an_error_not_a_no_op(tmp_path):
    """A tombstone for a graph the seed does not ship is how an overlay ROTS: the seed graph
    was renamed, the overlay keeps deleting a key nobody ships, and the graph the customer
    thought they removed is registered again under the new name with nothing to say so."""
    seed, ov = tmp_path / "seed", tmp_path / "ov"
    _write(seed, "a.yaml", VALID)
    _write(ov, "gone.yaml", {"graph_id": "not_in_seed", "deleted": True})
    with pytest.raises(ManifestError) as exc:
        compose(seed, [ov])
    assert "not_in_seed" in str(exc.value) and "seed does not ship" in str(exc.value)


def test_two_graphs_cannot_register_one_verb(tmp_path):
    """The registrar's compensate-on-rescope sweep DELETES rows matching (tool_urn, verb_iri)
    whose input_uri differs, so two rows sharing a verb replace each other silently."""
    seed = tmp_path / "seed"
    _write(seed, "a.yaml", VALID)
    _write(seed, "b.yaml", _row(graph_id="other", name="other_name"))
    with pytest.raises(ManifestError, match="same verb"):
        load_manifests(seed)


def test_an_invalid_row_names_its_file(tmp_path):
    """'a manifest is invalid' is not actionable at merge time; naming the file is what makes
    it fixable without a bisect."""
    seed = tmp_path / "seed"
    _write(seed, "broken.yaml", _row(verb="no_colon"))
    with pytest.raises(ManifestError, match="broken.yaml"):
        validate_dir(seed)


def test_registration_payload_carries_the_contract(tmp_path):
    p = registration_payload(GraphManifest(**VALID), endpoint_url="http://host:8098/g/x")
    assert p["verb_iri"] == "mesh:finProgramBrief"
    assert p["arity"] == "single"
    assert p["required_args"] == ["program_id"]
    assert p["slots"][0]["referent"] == "http://invincible-agent/fin#Program"
    assert p["mesh_graph_ref"].startswith("fin_program_brief@")
    assert p["endpoint_url"] == "http://host:8098/g/x"
