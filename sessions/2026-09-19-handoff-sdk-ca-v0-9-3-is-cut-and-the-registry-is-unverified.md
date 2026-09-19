# Handoff — SDK lane (ca), 2026-09-19

to: iagent-mesh-sdk/master

**Read this before touching anything. It states what is true, what is in flight, and the one
next step.**

**THIS FILE IS IN `iagent-mesh-sdk/sessions/`, WHICH DID NOT EXIST UNTIL NOW.** The inbox lives
in `invincible-agent/sessions/`, and this lane's repo is elsewhere — so it structurally never
read its packets, and the census scored "ca → 1 unread" against a directory this session cannot
see. Same for cortex-60 and 7f: the delivery mechanism was measuring the wrong population for
three of ten lanes. Ruled 2026-09-19 — each repo a lane works in carries its own `sessions/`,
and the census derives per-lane inboxes from the LANE'S WORKTREE rather than from one directory.
**That derivation is Lane 1's and has not landed, so nothing automatically reads this file yet.**

## STATE

    base sha        iagent-mesh-sdk master 60fd1f6  (0 behind / 0 ahead of origin)
    tag             v0.9.3 -> b6d597f, published to PyPI 2026-09-19T15:49:26Z
                    workflow 35452975425 — Test / Build wheel / Publish all success
    fleet pin       v0.9.3 (b6d597f) — Lane 1 rolled it; fleet at 91d8d34
    suite           378 passed. CI green on master and on the tag.
    consumers       engine-lg swapped onto the shared ledger row (invincible-agent 262fedb),
                    both findings sealed at 9843f6f

**v0.9.3 SHIPPED ALL SIX DISPATCHED ITEMS**, each as its own commit before the bump:

    1  the interface surface reachable from the root — 24 names + the 11 ledger names
    2  the [server] extra, its own commit AFTER the guard's own green run
    3  mesh:enumerateInstances — one shape, `scoped_by` naming what the provider applied
    4  edge-type registries, trace writer DERIVED from the eo census (not `None`)
    5  the SOURCE_LEDGER row vocabulary moved in from the graph host
    6  the docs status line — whose claim had INVERTED, not merely gone stale

**VERIFIED FROM THE CONSUMER SIDE, against the published wheel rather than the tree:** installed
`iagent-mesh==0.9.3` from PyPI into a clean venv, imported from a NEUTRAL directory, and printed
`__file__`. All ten of engine-lg's names resolve from site-packages, root exports are the module
objects (identity, not equality), and `iagent_mesh.core` refuses cleanly without the extra.

## THE NEXT STEP, AND IT IS ONE THING

**Confirm the two conformance arms in `invincible-agent/tests/test_the_registrar_writes_what_the_sdk_declares.py`
now RUN rather than SKIP, and are green.**

They have skipped since the day they were written, with
*"THIS IS A SKIP, NOT A PASS: the registrar's writes are UNVERIFIED against any declaration until
the fleet pin moves."* The fleet was pinned below `edge_types`; it is now on 0.9.3, so those arms
should execute for the first time — 8 arms, both doors, both directions.

    cd invincible-agent && uv run --frozen pytest tests/test_the_registrar_writes_what_the_sdk_declares.py -v

**A red there is a REAL disagreement between the SDK's declaration and the writes, not a pin
artefact.** I verified them against the 0.9.3 tree on `PYTHONPATH` (5 passed then, 8 now with
both doors) but never against the installed pin — so this is the first honest run.

## IN FLIGHT / OPEN — none dispatched, all named

* **The `marker_is_stale` alias contracts in a LATER release, deliberately not 0.9.3.** The
  in-fleet caller moved (engine-o's `_ensure_opened`, with its own anti-drift seal) and no local
  repo imports it. **That audit covers repos on one machine, not the world** — the name was the
  REAL function in 0.9.0/0.9.1, so a PyPI consumer on those versions has a caller nobody here can
  see and gets one release of warning rather than an interval.
* **18 names are public in their modules and declined at the root, with reasons**, because FOUR
  names are exported by two modules each: `compose`, `json_schema`, `validate_dir`, `resolve`.
  `compose` has BOTH consumers shipped (graph_host/main.py:43-46 and human_tasks.py:536). A root
  carrying both sides answers one caller's question with the other's function. **Needs a naming
  decision before any of `declarations`, `discovery`, `task_kinds` can be promoted.**
* **`limit` needs the same treatment `scoped_by` got, and it is not implemented.** A truncated
  list wearing a complete menu is the same defect as a class-wide list wearing a scoped one. The
  ruling covered scoping, so 0.9.3 covers scoping — the symmetry is recorded, not invented, and
  wants its own ruling.
* **Six fleet engines declare no uvicorn** (data_analyst, finance_agent, neo4j_expert,
  planning_agent, restate_analyst, weaviate_expert) and now take it as a transitive of `mcp`,
  which we do not control. Accidental safety, not declared. Lane 1's, routed.
* **The NetworkPolicy the substrate allowlist named was never built.** The chart carries no
  manifest, so `tests/test_substrate_address_lint.py` is currently the ONLY instrument for the
  third arm of the dependency rule. Do not cite it as defence in depth. Lane 1's, routed.

## WHAT THIS LANE PAID FOR — read if you are about to verify something

* **A wheel check must assert WHERE it imported from.** I installed 0.9.3 from PyPI into a clean
  venv and imported it FROM THE REPO ROOT — cwd went on `sys.path`, so Python imported my working
  tree while `importlib.metadata.version` correctly reported the installed 0.9.3. Version from
  the distribution, module from my checkout. Print `__file__`; a version number identifies the
  DIST, not which copy of the code ran.
* **Deleting a guard is a VACUOUS MUTANT.** A guard against an abnormal condition cannot be
  tested by removing it — the condition is not present in a normal run, so nothing changes.
  Create the bad state instead. (invincible-agent-22 proved their `__file__` assertion by staging
  a stray `iagent_mesh/` ahead of site-packages, not by deleting the check.)
* **A count over a shared tree is a reading, not a state** — attach a time. And `A..B` is
  DIRECTIONAL: I reported "7 ahead" of a tree that was also 3 BEHIND. Use
  `git rev-list --left-right --count origin/master...HEAD`.
* **A grep finding zero callers measures NOTICE, not HARM.** `from iagent_mesh import` had zero
  occurrences fleet-wide, which is the argument FOR the export seal — a surface with local
  consumers defends itself; that one had no defence.
* **The layout argument outranked mine.** Three reasons to move `rows.py`: route C (a benefit),
  the producer/consumer split (a defect closed), and the image having no `agent_fleet` at all
  (`COPY ${AGENT_DIR}/ /app/`) — which was crash-looping engine-lg while every test stayed green.
  **An argument naming a cost already being paid outranks one naming a future benefit.**

Lane: iagent-mesh-sdk/master
