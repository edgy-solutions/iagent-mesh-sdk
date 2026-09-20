# iagent-mesh-sdk — project memory

## What this is

The `iagent_mesh` SDK core library plus the Data-Driven DevEx Hub for the iagent Mesh
platform: universal contracts (`MeshGraph` / `MeshOntology` / `MeshVectors`, `MeshResult`),
an infrastructure wrapper, a conformance suite, and scaffolding templates for domain nodes.
Version 0.9.3 is cut; a v0.9.4 draft sits uncut on `lane/ca`.

## Repos

- **Primary:** `C:\Users\cnogr\git\iagent-mesh-sdk` (this repo, branch `lane/ca`, main = `master`)
- **Sibling, referenced by handoffs and lane packets:** `C:\Users\cnogr\git\invincible-agent`
  (lane packets land in `invincible-agent/sessions/`; `src/iagent/`, `agent_fleet/`, `helm/`)

Only ~108 tracked files. The whole repo is small; the hazards are all untracked.

## Key directories and files

- `iagent_mesh/` — the library (21 files). Largest: `core.py` 639, `interfaces.py` 585,
  `graph_manifest.py` 537, `transport_auth.py` 526.
- `iagent_mesh/interfaces.py` — substrate interface surface; `docs/interfaces.md` (658) is its spec.
- `iagent_mesh/rows.py` — `reachable_for`, SOURCE_LEDGER vocabulary.
- `iagent_mesh/graph_manifest.py` — `SlotDecl`, `narrowed_by`.
- `tests/` — 36 files, pytest. Largest: `test_interfaces.py` 523, `test_core.py` 500.
- `templates/` — 5 scaffold templates (`01_pure_math`, `02_instructor_polars`, `03_baml_pandas`,
  `legacy_adapter`, `smolagents_subswarm`); force-included into the wheel by hatch.
- `mcp_server/`, `app.py` — the hub's server surface.
- `docs/architecture_manifesto.md`, `docs/interfaces.md`, `docs/jupyter_guide.md`.
- `docs/outbound/` — patches aimed at OTHER repos, not applied here.
- `scripts/scaffold.sh`, `scripts/sandbox/` (k8s yaml + minio writer).
- `sessions/` — dated handoffs; the newest file is the live handoff (see below).
- `schemas/`, `llms.txt`, `agents.md`, `.cursorrules`, `.cursorignore`.

## Run / test / build

    uv pip install -e ".[dev]"      # dev extra self-references [server]; do not duplicate bounds
    python -m pytest                # pytest.ini: asyncio_mode = auto
    uv run --extra dev python -m pytest -q    # what CI runs
    uv build                        # sdist + wheel, both (PyPI wants both)
    uvx twine check dist/*
    bash scripts/scaffold.sh        # new domain-node template

CI: `.github/workflows/build-package.yml`.

## Never read (context hazards) — inspect cheaply instead

- `uv.lock` (2855 lines) — **never read**. `grep -n '^name = ' uv.lock | wc -l`, or grep one package.
- `dist/` — build output, gitignored. `ls -1 dist/`. **Stale: holds 0.4.0 wheels while the
  project is at 0.9.3.** Never read a wheel or tarball.
- `__pycache__/`, `iagent_mesh/__pycache__/`, `mcp_server/__pycache__/`, `tests/__pycache__/`,
  `.pytest_cache/`, `.venv/`, `.coverage` — all gitignored, never read.
- `docs/outbound/*.patch` — diffs for other repos. `git apply --stat` or `grep '^+++'`, never cat.
- Long result logs at the root: `ENGINE_W_AND_DATAHUB_RESULTS.md` (508),
  `BACKEND_COVERAGE_RESULTS.md`, `STRIX_HALO_OLLAMA_DIAGNOSTICS.md` (351) — grep by heading
  (`grep -n '^#' <file>`), never read whole.
- `sessions/*.md` and `docs/HANDOFF-*.md` run to ~385 lines — read the head or grep a `##` section.
- `scripts/sandbox/*.yaml` — k8s manifests; `grep -n 'kind:\|name:'`.

## Handoff

Live handoff (newest file in `sessions/`, absolute path):

    C:\Users\cnogr\git\iagent-mesh-sdk\sessions\2026-09-19-handoff-sdk-ca-the-v0-9-4-draft-is-on-a-branch-and-uncut.md

There is deliberately **no root `HANDOFF.md`** — `sessions/` is the single home for in-flight
state, and a second file would diverge silently. Find the current one with
`ls -1t sessions/ | head -1`.

Also present, a narrower one: `docs/HANDOFF-meshtool-execute.md`.

## Conventions and gotchas visible from the survey

- **Handoffs live in `sessions/`, dated + slugged**, not in a single rolling file. Lane packets
  to other lanes go as files in `invincible-agent/sessions/` with `to:` / `Lane:` headers.
- **Do not squash lane commits.** Each commit carries its own justification in the subject line;
  subjects are full sentences, not conventional-commit stubs alone.
- **A handoff that lists its own commits is stale the moment it is committed.** The v0.9.4
  handoff says so explicitly: check the INVARIANT
  (`git diff --stat 711c6d0..lane/ca -- . ':!sessions'` → exactly 4 files), never a commit count.
- **Distribution name `iagent_mesh` is deliberate** — pyproject carries a comment explaining why
  it is NOT renamed. Do not "fix" it.
- **`mcp` dependency upper bound is load-bearing** — `mcp` 2.x renamed `FastMCP` → `MCPServer`.
- **`[dev]` self-references `[server]`** rather than restating bounds; two lists would drift.
- Templates are a top-level wheel name; hatch `force-include` handles them. Touching the build
  target config can silently drop them from the wheel.
- `.mcp.json` configures one server: `forge_extension` at `http://localhost:42385/mcp`.
