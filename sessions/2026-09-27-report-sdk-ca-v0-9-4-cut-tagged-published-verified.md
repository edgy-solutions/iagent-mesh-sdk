# Report — v0.9.4 cut, tagged, published, verified

to: Chris
from: iagent-mesh-sdk / `lane/ca`, 2026-09-27

Ran the §1 runbook (`sessions/2026-09-19-handoff-sdk-ca-the-v0-9-4-draft-is-on-a-branch-and-uncut.md`)
against today's actual state, not its stale numbers.

1. **Branch check.** `origin/master...lane/ca` was `1 24` — master had one memory-doc commit
   lane/ca lacked; lane/ca had 24 (this session's work, unmerged). Checked both directions.
2. **Suite, declared form** (`uv run --extra dev python -m pytest -q`, the exact CI command):
   **492 passed, 2 skipped**, both before and after the merge.
3. **Merged `lane/ca` → `master`**, `--no-ff`, no squash (`0bb80f7`) — clean, no conflicts.
4. **PyPI checked live before tagging** (direct API hit, not WebFetch/cached): `GET
   /pypi/iagent-mesh/0.9.4/json` → 404. 0.9.4 did not exist; newest was 0.9.3.
5. **Bumped `pyproject.toml` to 0.9.4, `uv lock` regenerated** (`c75587e`), suite rerun green,
   tree clean. Tagged and pushed:

       git tag v0.9.4 && git push origin v0.9.4

6. **CI, all three jobs green:** Test → Build wheel → Publish to PyPI (run `36377337086`).
7. **Verified from the consumer side, neutral directory, printing `__file__`:** fresh `uv venv` +
   `uv pip install --no-cache iagent-mesh==0.9.4` in `c:\tmp\verify_iagent_mesh_094` (outside any
   git tree). `iagent_mesh.__file__` resolved to that venv's `site-packages`, not this checkout;
   dist-info `Version: 0.9.4`. Downloaded the published wheel directly from
   `files.pythonhosted.org` and its sha256 (`679a2f0d...940183`) matched PyPI's declared digest for
   that filename exactly. Scratch dir removed after.

**Tag:** `v0.9.4`, pushed. **PyPI:** live, `iagent-mesh==0.9.4`, wheel + sdist, digest-verified.
`lane/ca` fast-forwarded to the merged tip (`c75587e`) and pushed, so v0.9.5 work starts from the
cut, not behind it.

Moving to v0.9.5's write half now, per your five rulings — built on `lane/ca`, not released.

Lane: ia-ca/lane/ca
