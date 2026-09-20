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
    REF_COSMETIC,
    GraphManifest,
    ManifestError,
    SlotDecl,
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


# ── THE REF'S COVERAGE, DERIVED FROM THE HASH BASIS ─────────────────────────────────────────
# Added 0.7.0 after a real gap: dropping `referent` from the basis passed all fifteen tests
# here. `test_ref_covers_the_contract_and_ignores_cosmetics` varies `required` and `arity` and
# never `referent`, so it asserted the property FOR TWO FIELDS and was read as asserting it for
# the contract. A LIST GROWS WHEN SOMEONE REMEMBERS; A DERIVATION GROWS WHEN THE BASIS DOES.
#
# Found by a MIS-AIMED MUTATION rather than by the harness working: a mutation meant for
# `registration_payload` hit the identical line in `manifest_ref` instead, nothing went red,
# and investigating that anomaly is what surfaced this.

def test_every_model_field_is_classified_as_contract_or_cosmetic():
    """THE PARTITION. A field added to GraphManifest must land in the basis or in REF_COSMETIC.

    This is the test that makes the others durable: without it, a new contract-bearing field is
    simply absent from the ref and every assertion below still passes, because they only ever
    look at what the basis already contains.
    """
    from iagent_mesh.graph_manifest import REF_COSMETIC, GraphManifest, ref_basis

    m = GraphManifest(**VALID)
    covered = set(ref_basis(m))
    model_fields = set(GraphManifest.model_fields)
    unclassified = sorted(model_fields - covered - set(REF_COSMETIC))
    assert not unclassified, (
        "these GraphManifest fields are in neither the ref basis nor REF_COSMETIC, so whether "
        "they identify the contract is UNDECIDED — and undecided means absent from the ref:\n  "
        + "\n  ".join(unclassified)
        + "\nAdd each to ref_basis() or to REF_COSMETIC with the reason it does not identify "
          "the contract."
    )
    stale = sorted(set(REF_COSMETIC) - model_fields)
    assert not stale, f"REF_COSMETIC names fields the model no longer has: {stale}"


#: `graph_id` is the ref's PREFIX so a change is visible without hashing; `slots` is covered
#: field-by-field by `test_changing_any_SLOT_field_mints_a_new_ref` below, which is stronger
#: than one perturbation of the whole list. Both excluded by NAME with the reason, rather than
#: left to fall through to a skip — a skip here would be the silent kind this file is fixing.
@pytest.mark.parametrize("field", sorted(set(GraphManifest.model_fields) - set(REF_COSMETIC)
                                        - {"graph_id", "slots"}))
def test_changing_any_CONTRACT_field_mints_a_new_ref(field):
    """Derived from the basis, so a field added to it is covered with nothing written here."""
    base = manifest_ref(GraphManifest(**VALID))
    alt = {
        "verb": "mesh:somethingElse",
        "input_uri": "http://invincible-agent/fin#ControlAccount",
        "output_uri": "http://invincible-agent/mesh#AgentResponse",
        "arity": "set",
        "refusal": "fail",
    }
    assert field in alt, (
        f"{field!r} is in the ref basis and has NO perturbation here, so its coverage is "
        f"unasserted. Add one — do not skip, which is how the referent gap survived."
    )
    row = _row(**{field: alt[field]})
    if field == "arity":
        row["slots"][0]["required"] = False   # arity=set is refused while a referent forces single
    assert manifest_ref(GraphManifest(**row)) != base, (
        f"{field} is in the ref basis but changing it did NOT move the ref"
    )


#: TWO SLOTS, and the second one is not decoration. `narrowed_by` names a sibling slot, and
#: `_narrowed_by_names_resolve` refuses a name that is not a slot of the same row — correctly,
#: because a narrowing pointed at nothing is the silent failure that validator exists to catch.
#: A one-slot row therefore cannot perturb `narrowed_by` at all: the only legal value would be
#: the slot's own name, which `_narrowed_by_is_well_formed` refuses in its own right. The
#: population a derivation needs is the population the field can legally take.
def _two_slot_row(**over):
    d = _row(**over)
    d["slots"] = [
        {"name": "program_id", "kind": "spoken-mandatory", "type": "string",
         "required": True, "referent": "http://invincible-agent/fin#Program"},
        {"name": "vintage", "kind": "spoken-optional", "type": "string"},
    ]
    return d


#: The perturbation per SlotDecl field. Separate from the test so the arm below can assert the
#: table COVERS the model rather than quietly iterating whatever happens to be written here.
_SLOT_ALT = {
    "name": "program_ref",
    "kind": "spoken-optional",
    "type": "integer",
    "required": False,
    "referent": "http://invincible-agent/fin#ControlAccount",
    "values": ["FY24", "FY25"],
    "default": "P-1",
    "narrowed_by": ["vintage"],
}


@pytest.mark.parametrize("slot_field", sorted(SlotDecl.model_fields))
def test_changing_any_SLOT_field_mints_a_new_ref(slot_field):
    """DERIVED FROM `SlotDecl.model_fields`, which is what this file said it was doing and was
    not. The parametrize was the hand list `["kind", "type", "required", "referent"]`, under a
    docstring claiming coverage "by derivation: slots go into the basis via `model_dump`, so
    every declared SlotDecl field is covered". The BASIS was derived. The ASSERTION was not, and
    a derivation nobody iterates is a claim about code that never runs.

    IT HAD ALREADY DRIFTED THREE FIELDS BEFORE `narrowed_by` MADE IT FOUR. `name`, `values` and
    `default` were never in the list. Then 247ff5e added `narrowed_by` two commits ago — a field
    whose entire purpose is to change what a row means — and the arm that claims to fire on ANY
    slot field never saw it. Nothing went red, because nothing was looking: the list grew when
    someone remembered, and nobody did.

    THE SAME DEFECT SHAPE AS THE ONE THIS SECTION WAS BUILT FOR, one level down. `referent`'s
    omission from the ref basis passed all fifteen tests here because the seal varied two fields
    and was read as covering the contract. This list varied four and was read as covering the
    slot. A derivation grows when the basis does; a list grows when someone remembers."""
    base = manifest_ref(GraphManifest(**_two_slot_row()))
    assert slot_field in _SLOT_ALT, (
        f"SlotDecl declares {slot_field!r} and _SLOT_ALT has NO perturbation for it, so its "
        f"coverage is unasserted. Add one — do not skip, which is how `referent` survived, and "
        f"do not drop it from the parametrize, which is how `narrowed_by` arrived uncovered."
    )
    row = _two_slot_row()
    row["slots"][0][slot_field] = _SLOT_ALT[slot_field]
    assert manifest_ref(GraphManifest(**row)) != base, (
        f"slot.{slot_field} changed and the ref did not move — the ref does not identify the "
        f"contract it claims to"
    )


def test_the_SLOT_perturbation_table_names_no_field_the_model_dropped():
    """THE OTHER DIRECTION, and it is why the table is a module-level dict rather than a local.

    A stale entry here is harmless to the arms above — the parametrize iterates the MODEL, so a
    perturbation for a deleted field is simply never used. That is exactly what makes it
    dangerous to read: it documents a field the model no longer has, and the next person deriving
    something from this table inherits the ghost. `test_every_model_field_is_classified_as_
    contract_or_cosmetic` already does this for REF_COSMETIC; slots get the same treatment."""
    stale = sorted(set(_SLOT_ALT) - set(SlotDecl.model_fields))
    assert not stale, f"_SLOT_ALT perturbs fields SlotDecl no longer declares: {stale}"


@pytest.mark.parametrize("field", sorted(REF_COSMETIC))
def test_changing_a_COSMETIC_field_keeps_the_ref(field):
    """The other direction, and it is what stops the fix from becoming "hash everything".

    A ref that moved on a reflowed description would churn on every edit, which is the property
    `ruleset_ref`'s content-only discipline exists to avoid.
    """
    base = manifest_ref(GraphManifest(**VALID))
    alt = {
        "module": "graphs.somewhere_else", "builder": "make", "name": "other_name",
        "description": "entirely reworded, same contract", "synonyms": ["x"],
        "anti_synonyms": ["y"], "owner_persona": "COST_ANALYST", "domains": ["PRODUCTION_COST"],
        "cost_class": "low", "requires_human_approval": True, "timeout_s": 5.0,
        "checkpointer": False,
    }
    assert field in alt, f"REF_COSMETIC names {field!r} with no perturbation here to prove it"
    assert manifest_ref(GraphManifest(**_row(**{field: alt[field]}))) == base, (
        f"{field} is declared cosmetic but changing it moved the ref"
    )


# ── enforce_refusal: ONE implementation, so route C inherits it ──────────────────────────────

def test_enforce_refusal_REJECTS_holes_under_fail():
    from iagent_mesh.graph_manifest import RefusalViolation, enforce_refusal

    m = GraphManifest(**_row(refusal="fail"))
    with pytest.raises(RefusalViolation) as exc:
        enforce_refusal(m, {"summary": "two of three", "holes": [{"source": "inner_b"}]})
    assert "refusal=fail" in str(exc.value) and "inner_b" in str(exc.value)
    assert "contract disagreement" in str(exc.value), (
        "the error reads as a runtime fault; it is a disagreement between a row and its module"
    )


def test_enforce_refusal_PASSES_the_same_holes_under_named_hole():
    """THE CONTROL. Without it, "rejects holes under fail" is indistinguishable from "rejects
    holes from everyone" — which would break every named-hole graph while reading as success."""
    from iagent_mesh.graph_manifest import enforce_refusal

    m = GraphManifest(**_row(refusal="named-hole"))
    out = {"summary": "two of three", "holes": [{"source": "inner_b"}]}
    assert enforce_refusal(m, out) is out


def test_enforce_refusal_passes_a_complete_answer_under_fail():
    """The other control: `fail` must not reject an output that carries no holes."""
    from iagent_mesh.graph_manifest import enforce_refusal

    m = GraphManifest(**_row(refusal="fail"))
    out = {"summary": "all three views"}
    assert enforce_refusal(m, out) is out
