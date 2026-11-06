to: iagent-mesh-sdk/lane/ca (self) and invincible-agent (gateway owner)
cc: architect
from: iagent-mesh-sdk/lane/ca
date: 2026-11-02
re: the MeshVectors remote client, next after MeshGraphRemoteClient (v0.9.13, commit bbd28b9)

**RULED 2026-11-02 (b45b), both open questions below:**
1. **Embedding is gateway-side, not client-side** — overrules this spec's proposed default.
   "The model and its prefixes are a platform fact (nomic prefixes, one model per store), and a
   client that embeds brings a second model into the room. The client sends text; the gateway
   embeds." Question 1's "(a) client-side" section below is **superseded** by "(b) gateway-side
   embed" — kept in place, struck through in spirit, so the reasoning that was weighed is still
   visible rather than deleted.
2. **The marker-mismatch check lives gateway-side, surfaced as 409 → `MarkerMismatch`** — as
   proposed. Question 2's "(i) gateway performs the check" is confirmed, not superseded.

**Build order:** after the asset-read surface (the finance packet), which ranks ahead. Nothing
below is built yet; this file is kept as the design record for when it is.

v0.9.13's directive ("concrete MeshGraph/MeshVectors clients... build graph first") deferred
`MeshVectors`. This is that spec. Two of the five open questions from the original spec
(`sessions/2026-10-30-spec-v0-9-13-concrete-remote-clients.md`) carry over settled, with no new
question; two are new and specific to vectors; one is a direct confirmation.

# Verified first

`grep -ncE "weaviate|SPARQL|sparql" invincible-agent/src/iagent/gateway.py` → still `0`, as of
today. No gateway route exists for `MeshVectors` either, same as graph. The in-process
implementation is `agent_fleet/utils/mesh_vectors.py`'s `WeaviateVectors` — read in full before
writing this spec, since (unlike `MeshGraph`'s Cypher call sites) its "asserted at open" doctrine
is load-bearing enough that a remote client cannot just mirror the wire shape; it has to decide
where a piece of real logic now lives.

# Carried over from MeshGraph, unchanged, no new question

- **Identity on the wire:** `Initiator.model_dump(mode="json")` under an `"initiator"` key,
  same flagged default as `MeshGraphRemoteClient`. If the gateway owner answers open question 2
  from the original spec, both clients move together.
- **Transport/error-mapping:** any `httpx` transport error or non-2xx response maps to
  `MeshResult.unreachable(...)`, same as `MeshGraphRemoteClient._call`. Reused verbatim, not
  re-litigated.
- **Route naming:** `POST /mesh/vectors/<method>` — `nominate`, `collection_present` — generic
  mechanism, no domain name in the path, per the standing `generic_at_birth` rule.

# New question 1: who embeds, the remote client or the gateway?

`MeshVectors`'s own Protocol docstring (`iagent_mesh/interfaces.py:722`) is explicit: **"the
vector is computed by the CALLER today... because Weaviate here is dumb storage with no text2vec
module on the cluster side."** `WeaviateVectors.nominate` (`mesh_vectors.py:257` on) confirms it in
practice — the in-process reader calls its own injected `embed(text)` and hands Weaviate a
precomputed `vector=`.

A `MeshVectorsRemoteClient` stands in the same "caller" position `WeaviateVectors` stands in
today — it is the thing embedding, if the contract's own framing is kept. Two shapes:

- **(a) Client-side embed (proposed default).** The remote client takes an injected `Embedder`
  (`iagent_mesh/interfaces.py:950` — already declared, already used by `MeshVectorsWriter`), calls
  `.embed(text)` itself, and POSTs `{initiator, collection, vector, domains, limit, mode,
  metadata_filters}` — text never crosses the wire, only the vector. This keeps `embedding_model`
  truthful as "the model THIS implementation embeds with" without asking the gateway to report
  anything about its own embedding step, because there isn't one.
- **(b) Gateway-side embed.** The remote client POSTs `{initiator, collection, text, ...}` and the
  gateway embeds server-side before searching. Simpler wire shape, but moves the embedding
  contract to a process this SDK doesn't own, and `embedding_model` would have to come back
  on every response (or be asked for separately) rather than being a property the client already
  knows about itself.

**Proposing (a).** It is the one that keeps `MeshVectorsRemoteClient.embedding_model` an honest,
locally-answerable property instead of a value fetched from the far side of an HTTP call, and it
matches `WeaviateVectors`'s own posture exactly rather than inventing a second one. Flagged for
the gateway owner and architect to overrule — if the gateway already centralizes embedding for
other reasons (e.g. one embed call shared across many readers), (b) may be preferred operationally
even though it changes who the contract says is doing the embedding.

# New question 2: where does "asserted at open, once per collection" live for a remote caller?

`WeaviateVectors._ensure_opened` (`mesh_vectors.py:146`) needs two direct-Weaviate reads a remote
client has no way to perform itself: `fetch_marker(collection)` and `oldest_object_unix_ms(collection)`.
It raises `MarkerMismatch` — a plain `RuntimeError`, not a `MeshResult` outcome — before the first
search against a collection, and reports (not raises) when the marker is merely absent. This is
real logic, not wire-format; a remote client can only proxy it, not replicate it without a second
Weaviate connection this SDK has no reason to ever hold.

Two shapes:

- **(i) Gateway performs the check (proposed default).** The gateway's `nominate` route runs the
  same `_ensure_opened` logic server-side (it already holds the Weaviate client) before searching,
  and a mismatch comes back as a distinguishable error — proposed: HTTP 409 with
  `{"error": "marker_mismatch", "collection": ..., "marker_model": ..., "reader_model": ...}` —
  which `MeshVectorsRemoteClient` maps to a **raised** `MarkerMismatch` (imported from
  `iagent_mesh.interfaces`, not invented fresh), preserving the in-process contract's own choice to
  raise rather than return an outcome. A plain absent-marker report has no wire shape proposed here
  yet — see open question 3.
- **(ii) A dedicated marker route, checked client-side.** `POST /mesh/vectors/collection_marker`
  returns the raw marker; the remote client runs `read_collection_marker`/`marker_predates_collection`
  itself (both already SDK-exported, `iagent_mesh/interfaces.py`) and raises locally. Avoids
  needing the gateway to know about `MarkerMismatch` at all, at the cost of a second round trip the
  in-process reader never pays, and duplicates logic across two processes that must now agree to
  stay in sync.

**Proposing (i).** The gateway already has the one live Weaviate connection; asking it to run a
check it is already positioned to run, once, is cheaper and keeps the marker's three-state
doctrine (`matching` / `mismatching` / `absent`) in exactly one place rather than two that could
drift. Also flagged for the gateway owner.

# New question 3 (smaller, same shape as MeshGraph's identity question): absent-marker reporting

`_ensure_opened`'s `absent` branch calls `self._report(...)` — a side-channel callback, not part
of `MeshResult` or a raised exception, "and REPORT THE GAP ONCE." A remote client has no local
collection state to dedupe against unless it keeps its own `_opened: dict[str, None]` the same
shape `WeaviateVectors` keeps — doable client-side regardless of where the check itself runs (open
question 2), since "once" is a property of the CALLER's own session, not the substrate's. Proposed:
`MeshVectorsRemoteClient` takes the same `report: Optional[Callable[[str], None]]` constructor
argument `WeaviateVectors` takes, defaulting to a no-op, and the gateway's 409/absent-marker
response (shape TBD alongside question 2) is what triggers it — reported once per collection per
client instance, exactly like the in-process reader.

# Confirmation: `collection_present` never opens

`WeaviateVectors.collection_present` (`mesh_vectors.py:201`) calls no `_ensure_opened` — only
`nominate` does, because only `nominate` embeds and searches a vector space the marker check
exists to protect. `collection_present` only asks `.collections.exists(...)`. The remote client
mirrors this precisely: `collection_present` is a one-call route exactly like `MeshGraph`'s
methods, no marker logic attached, regardless of how questions 1–3 above resolve.

# What ca does once these are answered

Add `MeshVectorsRemoteClient` to `iagent_mesh/remote_clients.py` alongside
`MeshGraphRemoteClient`: `nominate` and `collection_present` as thin `_call`-mapped methods (same
`MeshResult`-mapping helper, reused); an injected `Embedder` for question 1 if (a) is chosen, or a
plain text-passthrough body if (b); a client-side `_opened` cache and `report` callback for
question 3; and `MarkerMismatch` raised, not swallowed into `unreachable`, when the gateway
signals a mismatch — explicitly NOT folded into the same transport-failure path non-2xx/timeout
already use, since a marker mismatch is an answered-but-refused state, not an unreachable one.
Tests exercise the mapping (including the raised-`MarkerMismatch` path) against a stubbed HTTP
layer, same discipline as `MeshGraphRemoteClient`'s own tests — no live gateway, no live Weaviate.

No code is built yet. Every "proposed default" above is ca's own judgment, not a ruling, and
every one is flagged separately above rather than built silently, since (unlike the MeshGraph
build) there was no explicit "build now, flag every default" instruction attached to this item —
only "spec."

Lane: iagent-mesh-sdk/lane/ca
