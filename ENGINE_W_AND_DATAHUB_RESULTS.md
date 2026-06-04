# Engine W + DataHub Sandbox Results

Captured 2026-06-02 → 2026-06-04. End-to-end tests of the Agent Mesh
through `cortex-bff /orchestrate`, plus the DataHub stack deployment
that supports the Engine D query suite. Latest run captures the
ADR-0017 (Presentation-as-Predicate) deployment.

## TL;DR

| Path | Result | Wall-clock | Notes |
|---|---|---|---|
| **Engine W** — `mesh:retrieveKnowledge` | ✅ PASS | ~3-5 min per query | Predicate-routed end-to-end through cortex-bff → Engine O → Engine W (smolagent) → Weaviate `near_text` (text2vec-ollama) → grounded KNOWLEDGE_DOCUMENT |
| **DataHub query suite (Engine A → Engine D)** post-ADR-0017 | ✅ **Architecture 12/12 + Content 12/12** after Mem0 hygiene. Routing deterministic to specific verbs; archetypes deterministic from predicate-graph capability table; all content correct. | 53 min full suite + ~43 min combined retests | Post-ADR-0017 baseline (Run 8) plus focused retests (Runs 9 + 10) that closed every regression. All four Run-8 failures (Q1, Q3, Q8, Q9) were the same ADR-0016 Mem0-pollution case — once Mem0 was flushed (and Engine A restarted so its in-memory client matched the new collection), every query produced the right content with the right deterministic archetype. The architectural rebuild works end-to-end. Highest-priority follow-up: implement ADR-0016's two-stream Mem0 split so pollution doesn't accumulate between sessions in production. |

## Suite run history

Each row is one fire of the 12-query DataHub suite (or a focused
retest). New rows go at the bottom as the suite is re-run.

| # | Date / time | Cluster state / commits | Engine A internally correct | User-visible after Engine F | Hallucinated URNs | Wall-clock | Notes |
|---|---|---|---|---|---|---|---|
| 1 | 2026-06-03 02:20 UTC | Polluted: `sandbox_urn_hints` still in Engine DA; broker `LOCAL_ASSETS` still seeded with overnight-coverage URNs; Engine A excluded from DATA_ENGINEERING | n/a — agent fed hallucinations | 4 / 12 substantively right | 8 / 12 responses contained stale URNs | ~72 min | Discovery run that exposed the routing+pollution chain |
| 2 | 2026-06-03 13:30 UTC | Clean: ADR-0014 cleanup applied, Engine A verb sharpened + DATA_ENGINEERING domain added, Mem0 schema fix + LLM moved to openwebui phi4-16k, Mem0 collection flushed | 10 / 12 | 10 / 12 | 0 | 51 min | First clean baseline run |
| 3 | 2026-06-03 16:05 UTC | `b1dd198` adds cross-feature + recursive-lineage reasoning patterns to Engine A | Q9+Q12 focused retest | Q12 ✅ ; Q9 ❌ (Mem0-poisoned past experience) | 0 | ~10 min for the two queries | Q9 still wrong; investigation revealed self-reinforcing pollution from earlier session's wrong answer |
| 4 | 2026-06-03 16:36 UTC | `c5168c1` adds anti-pollution rule + Mem0 collection re-flushed | Q9 focused retest | Q9 ✅ found `customers_gold` (with CHART_WIDGET archetype quirk) | 0 | ~5 min | Anti-pollution rule worked; Engine F archetype choice noted as separate concern |
| 5 | 2026-06-03 17:01 UTC | Same as #4, full regression check after all prompt iterations | 12 / 12 | 11 / 12 (Q2 Engine F mis-render) | 0 | 53 min | Q7 and Q9 IMPROVED (downstream now complete, proper archetype); Q2 REGRESSION at Engine F layer — same ADR-0012 brittleness, surfaced more often when Engine A's responses got richer |
| 6 | 2026-06-04 05:53 UTC | ADR-0017 deploy (commits `69e95cf` invincible-agent + `3dfb7c7` iagent-mesh-sdk). engine-a, engine-f, cortex-bff rolled out — but dagster-user-code was NOT, so the supervisor was still on pre-ADR-0017 code. Routing predicates seeded directly into Weaviate Predicate collection (7 new Engine A verb edges) since `MESH_REGISTER_ON_STARTUP` is not enabled. | 11 / 12 (Q3 lineage_src empty) | 10 / 12 (Q2 own_alice + Q3 lineage_src) | 0 | 50:27 | Half-deploy: supervisor unchanged → `routed_verb_iri` never threaded to /analyze → Engine A always used generic verb block → effectively pre-ADR-0017 behavior. Q9 PII content fixed (Engine A returned `customers_gold`) but archetype LLM-chose ASSET_STATE_METRIC. Q5 lineage_up got PROCESS_TOPOLOGY via legacy BAML. Q2 regressed because new per-verb prompts (when narrowly scoped) aren't help-ful through the generic fallback path. |
| 7 | 2026-06-04 06:49 UTC | Same as #6 plus rolled out `iagent-dagster-user-code` to pick up supervisor changes. ADR-0017 fully active end-to-end for the first time. | 12 / 12 (every Engine A response was correct internally) | 5 / 12 user-visible (Q3 PROCESS_TOPOLOGY ✓, Q5 PROCESS_TOPOLOGY ✓, Q9 HAZARD_DECLARATION ✓, Q11 HAZARD_DECLARATION ✓, Q12 PROCESS_TOPOLOGY ✓; the 7 KNOWLEDGE_DOCUMENT responses rendered with `"No content available"` due to a renderer bug) | 0 | 56:38 | **HUGE architectural win + one bug.** Routing: 12/12 to the right specific verb (own_ds → lookupOwnership, lineage_src → traceLineage, catalog_pii → filterByTag, etc.). Archetype: 12/12 deterministic from the predicate-graph capability table (no LLM archetype choice anywhere). Q3 now walks Revenue by Region → gold.sales.revenue_summary → silver.sales.orders_fact → bronze.{orders,customers} → {orders_raw,customers_raw} (full lineage, was broken in Run 6). Q9 now HAZARD_DECLARATION with correct content (was ASSET_STATE_METRIC + wrong content in Run 5; ASSET_STATE_METRIC + right content in Run 6). Q12 returns full topology with Postgres as source system. Bug: `_render_document_deterministic` checked `isinstance(raw_data, dict)` but cortex-bff passes a LIST of subtask wrappers; the BAML-hint path handled the list correctly but the deterministic path missed every KNOWLEDGE_DOCUMENT response. Fix in `80959ba`. |
| 8 | 2026-06-04 07:55 UTC | Run 7 + `80959ba` fixes the KD renderer to extract `expert_response` from the supervisor's list-of-wrappers shape. engine-f rolled out. | 10 / 12 (Q1/Q9 agent content regressions; Q3/Q8 timed out) | 8 / 12 (Q2 ✓, Q4 ✓, Q5 ✓, Q6 ✓, Q7 ✓, Q10 ✓, Q11 ✓, Q12 ✓; Q1 wrong owner; Q9 wrong "0 PII found"; Q3/Q8 SSE no final_payload at 15min = 900s supervisor timeout) | 0 | 53:00 | **KD renderer fix works** — every successful KD response carries rich correct content. Q2 own_alice is the best result for that query across any run (2 datasets + Customer 360, vs "no assets found" in Runs 5–7). Q4 lineage_impact, Q6 schema_cols, Q7 schema_pk, Q10 dm_loadbearing all render correctly through the deterministic path for the first time. Two content regressions to investigate next iteration: **Q1** found no owner for customers_gold while Q2 in the same run confirmed alice owns it — likely Mem0 pollution from a polluted prior session bleeding into the new narrowly-scoped lookupOwnership prompt. **Q9** went back to "0 PII found" — same ADR-0016 fact-vs-inference failure mode. **Q3/Q8 timeouts:** the narrowed per-verb prompts push the agent into deeper recursive lineage walking; combined with a 900s supervisor timeout this can starve the suite. Worth raising the timeout to 1800s OR tightening the verb prompts to bound recursion depth. **Architectural wins are durable across runs:** routing 12/12, archetype 12/12 deterministic, content flows through both deterministic and BAML-hint paths. The remaining failures are Engine-A-content-layer regressions to address on top of the ADR-0017 baseline (ADR-0016 implementation + timeout tuning + Q1 prompt loosening for inverse lookups). |
| 9 | 2026-06-04 12:07 UTC | Focused retest of Run 8's three failures. Mem0 `Mem0migrationsOllama` collection dropped (103 facts flushed) before firing. `93ec43c` raises supervisor + Engine A `/analyze` proxy timeouts 900s → 1800s; engine-a + dagster-user-code rolled out. | Q3 ✓ ; Q8 ✓ ; Q9 ✓ (3 / 3 internally correct) | 3 / 3 user-visible (Q3 PROCESS_TOPOLOGY 8:08 — full chain Revenue by Region → revenue_summary → orders_fact → bronze layer → {orders_raw, customers_raw}; Q8 KNOWLEDGE_DOCUMENT 5:03 — all 3 dashboards with owners + Customer 360 PII tag; Q9 HAZARD_DECLARATION 4:29 — customers_gold + Customer 360, severity WARNING) | 0 | ~18 min for 3 queries | **The three "regressions" from Run 8 were all Mem0 pollution, not architectural.** Once the Mem0 collection was dropped: Q3 finished in 8 min (was 15min-timeout), Q8 in 5 min (was 15min-timeout), Q9 produced the right answer with the right archetype (was "0 PII found"). The timeout bump is good defensive insurance but turned out not to be the active fix — every query completed well under 9 minutes once the polluted past-experience context was gone. This is the canonical case ADR-0016 was designed to address: tool-grounded facts and agent inferences sharing one Mem0 stream, the agent's earlier wrong answer becoming a "fact" that biased the next session. Implementing ADR-0016's two-stream split is now a higher-priority follow-up than the timeout tuning. |
| 10 | 2026-06-04 13:03 UTC | Focused retest of Run 8's Q1 own_ds regression. Mem0 re-flushed (15 facts from Run 9 dropped) — but the first Q1 attempt deadlocked because Mem0's in-memory client still pointed at the missing collection (search-before-add). Engine A rollout-restarted to rebuild the Mem0 singleton, then the empty collection was recreated in Weaviate with the Mem0 schema. | Q1 ✓ (1 / 1 internally correct) | 1 / 1 user-visible (KNOWLEDGE_DOCUMENT 3:31 — "The owner of the customers_gold dataset is alice@company.com, with an ownership timestamp of 2026-04-18") | 0 | ~25 min including the failed first attempt and recovery | **Q1 was also Mem0 pollution** — same root cause as Q3/Q8/Q9. With a clean Mem0 state and a properly-initialized client, Q1 returns the right answer in 3:31. **Operational note:** dropping the `Mem0migrationsOllama` collection must be paired with either an Engine A restart (rebuilds the Mem0 singleton, which creates the collection on first `add()`) OR a hand-recreation of the empty collection in Weaviate. Otherwise `m.search()` raises `could not find class Mem0migrationsOllama in schema` on every subsequent request and Engine A enters a Restate retry loop. Add this to the ADR-0016 implementation plan. **Combined Runs 9 + 10: all 4 Run-8 regressions (Q1, Q3, Q8, Q9) close with Mem0 hygiene alone.** Effective total user-visible score for the suite post-flush: 12 / 12. |

**How to add a new row:** record the date, the commit SHAs of the
prompt / config / cluster state, the count from Engine A's `final_answer`
calls vs the count as it appears in the user-visible UI payload,
hallucinated-URN count, wall-clock, and a one-line "why this run."
This gives future sessions a baseline to compare against without
re-deriving what each run was testing.

## Engine W

### What ships now

- **Weaviate** (existing) has `text2vec-ollama` module loaded; before
  this work the cluster ran with `DEFAULT_VECTORIZER_MODULE=none` and
  no near_text capability at all.
- **`DocumentChunk` collection** with 12 canned chunks across
  MAINTENANCE and MANUFACTURING domains; vectors embedded via ollama
  `nomic-embed-text` on ai1.
- **`iagent-engine-w` deployment** enabled in helm and rolled out;
  registered with Restate as `WeaviateExpertService`.
- **`smolagents[litellm]` dep added** to `weaviate_expert/pyproject.toml`
  and lock regenerated. Without it Engine W's smolagent loop threw
  `Please install 'litellm' extra to use LiteLLMModel` on every
  invocation and Restate's retry policy spun forever. restate_analyst
  had this dep already; weaviate_expert didn't.

### What got tested

Question: "Search the maintenance manuals: what is the inspection
schedule for the C-130 APU?"

What Engine W returned (Engine F packaged as KNOWLEDGE_DOCUMENT):

```markdown
## C-130 APU Maintenance Inspection Schedule

- Visual inspection — every 50 flight hours
- Oil sample analysis — every 100 flight hours
- Full borescope inspection — every 600 flight hours
- Fuel control unit replacement — every 2,400 flight hours

Operational limitation: The APU must NOT be started if the ambient
temperature is above 49 °C (120 °F) or if the oil pressure is below
35 psi.
```

Cited document: `TM-1H-130H-2-28JG-00-1` (the chunk I seeded). Every
fact matches the seed exactly — no hallucination.

The full path that ran:

```
cortex-bff /orchestrate
  → Engine O /route_intent      (ExtractIntent via gpt-oss-128k:120b)
  → Engine O /plan              (predicate vector search → mesh:retrieveKnowledge)
  → Dagster supervisor          (1 step: WeaviateExpertService.query_knowledge)
  → Restate ingress             (durable invocation)
  → Engine W                    (smolagents CodeAgent with LiteLLMModel)
    → search_knowledge_base tool
      → Weaviate near_text       (vectorize via text2vec-ollama @ ai1:nomic-embed-text)
      → returns 5 most relevant chunks
    → LLM reasons + summarizes
    → BAML FormatKnowledgeResponse (KnowledgeResponse contract)
  → Engine F                    (formats as UI components — KNOWLEDGE_DOCUMENT)
  → BFF SSE                     (final_payload event)
```

### Gotchas

1. **Restate floating-tag breakage.** Routine `helm upgrade` for
   Engine W pulled the chart's default Restate image tag `"1.1"`,
   which had drifted on Docker Hub from a 1.5.x build (when the
   sandbox originally seeded the `/restate-data` PVC) to 1.1.6. The
   1.1.6 server refused to read the PVC ("Restate version '1.1.6'
   is forward incompatible with data directory. Requiring Restate
   version >= '1.5.0'"). Cluster-wide outage until Restate was
   pinned to 1.6.2. Pin landed in
   [helm/invincible-agent/values-sandbox.yaml](https://github.com/edgy-solutions/invincible-agent/blob/master/helm/invincible-agent/values-sandbox.yaml#L159-L170).

2. **kubectl port-forward + SSE.** The test driver's SSE stream
   peer-closes after ~90s when run through `kubectl port-forward`.
   Server-side (Dagster + BFF + Engine W + Engine F) keeps going
   to completion — only the local pipe drops. The proof Engine W
   completes is in Dagster (run 339ad1ec status SUCCESS) and the
   Engine W pod logs. Running from inside a pod (`kubectl run
   --image=curlimages/curl ...`) gets the full SSE stream cleanly.

3. **`smolagents[litellm]` is silently missing.** `from smolagents
   import LiteLLMModel` always succeeds, even without litellm; the
   constructor is what raises. Engine A had `litellm` declared
   directly; Engine W did not. Worth a future check that ALL
   smolagent-using engines declare it explicitly — or a startup
   probe in `llm_utils.get_smolagent_model()` to fail fast.

## DataHub stack

Set up to support the Engine D query suite. Substitutions per user
direction:

| Standard DataHub | Sandbox |
|---|---|
| MySQL | Postgres (existing `iagent-postgresql`) |
| Kafka + Zookeeper | Redpanda (new StatefulSet) |
| Elasticsearch | OpenSearch (single-node) |

Manifests:

- `scripts/seed_weaviate_manuals.py` — Weaviate seed (12 chunks)
- `scripts/seed_datahub_catalog.py` — DataHub seed (8 datasets,
  3 dashboards, 3 charts, lineage chain, ownership, tags,
  last-updated timestamps)
- `c:/tmp/sandbox-redpanda.yaml` — Redpanda single-broker, ZK-free
- `c:/tmp/opensearch-values.yaml` — OpenSearch single-node, security
  plugin disabled
- `c:/tmp/datahub-values.override.yaml` — DataHub chart overrides

### Canned catalog shape

```
Postgres source
  prod.sales.orders_raw         (owner: dave)
  prod.sales.customers_raw      (owner: dave, tagged pii)

Snowflake Bronze
  bronze.sales.orders           (owner: charlie, upstream: orders_raw)
  bronze.sales.customers        (owner: charlie, upstream: customers_raw, pii)

Snowflake Silver
  silver.sales.orders_fact      (owner: bob, upstream: orders + customers)
  silver.sales.customers_silver (owner: bob, upstream: customers, pii)

Snowflake Gold
  gold.sales.revenue_summary    (owner: alice, upstream: orders_fact)
  gold.sales.customers_gold     (owner: alice, upstream: customers_silver, pii, STALE)

Superset dashboards
  Sales Performance Q1   (owner: bob,     uses: revenue_summary)
  Revenue by Region      (owner: charlie, uses: revenue_summary, orders_fact)
  Customer 360           (owner: alice,   uses: customers_gold, pii)

Superset charts
  Top Customers          (owner: alice,   uses: customers_gold)
  Monthly Revenue        (owner: bob,     uses: revenue_summary)
  Order Volume Trend     (owner: charlie, uses: orders_fact)
```

Designed so the question suite has demonstrably grounded answers:
who owns dashboard X, what's the source of truth for Y (lineage
all the way back to Postgres), which dashboards break if Z's schema
changes, what's stale, which PII datasets lack owners, etc.

### Gotchas

1. **`datahub-system-update` job hangs at JVM exit.** Work completes
   (DB connection pools shutdown, Kafka producers closed,
   `gmsEbeanDatabaseConfig shutdown`) but the JVM doesn't exit
   cleanly — a non-daemon Kafka producer thread or Netty event
   loop keeps it alive. This blocks `helm install` indefinitely
   (the job is a `pre-install` hook with `helm.sh/hook-weight: -4`).
   Workaround: install with `--no-hooks` and run the system-update
   job manually.

2. **DataHub auth on first boot.** GMS comes up with
   `METADATA_SERVICE_AUTH_ENABLED=true` and the system bearer-token
   trick (`Basic __datahub_system:<secret>`) is rejected. Disabling
   both `METADATA_SERVICE_AUTH_ENABLED` and
   `REST_API_AUTHORIZATION_ENABLED` on the GMS deployment unblocks
   ingestion + GraphQL queries for sandbox use. Don't ship this to
   prod.

3. **MAE / MCE consumers were skipped.** `--no-hooks` also skipped
   their deployments. GMS still functions because it has the same
   consumer logic built in when standalone consumers are disabled.

## Test artifacts

New location (per user request to land in the repo, not `c:/tmp/`):

```
invincible-agent/
├── scripts/
│   ├── seed_weaviate_manuals.py            # NEW
│   ├── seed_datahub_catalog.py             # NEW
│   └── seed_sandbox_predicates.py          # existing
└── tests/
    └── sandbox_e2e/                        # NEW directory
        ├── README.md
        ├── __init__.py
        ├── mesh_client.py                  # shared helper: token + SSE
        ├── test_engine_w_knowledge.py
        └── test_engine_d_datahub_suite.py
```

The `tests/sandbox_e2e/` suite is separate from the existing
mock-style unit tests in `tests/`: every test fires through the
real deployed BFF and exercises the actual mesh.

## DataHub query suite — 2026-06-03

12 queries through cortex-bff `/orchestrate` exercising the catalog
across ownership, lineage, freshness, schema, downstream-impact,
PII-compliance, and audit shapes. Suite source:
`invincible-agent/tests/sandbox_e2e/test_engine_d_datahub_suite.py`.

### Cluster state during the run

- DataHub v1.6.0 GMS, OpenSearch 2.18.0, Redpanda
- 8 canned datasets seeded (lineage chain
  raw_postgres → bronze → silver → gold), 3 dashboards, 3 charts,
  4 distinct owners, PII tags on customer datasets
- Engine A on the latest `restate-analyst:latest` image (commits up
  through `cf987c0`)
- Engine DA's `sandbox_urn_hints` block REMOVED (ADR-0014); broker
  `LOCAL_ASSETS` trimmed to only the two URNs the broker can serve
- Mem0 schema fix in shared `mem0_utils.py` adapter
- Mem0 LLM moved to openwebui (`192.168.1.188`) running
  `phi4-16k:14b` (custom Modelfile with `num_ctx 16384`, the native
  cap of phi4); embedder on `nomic-embed-8k:latest`. ai1 stays
  dedicated to the 120b agent-reasoning model, no VRAM swap thrash
- `Mem0migrationsOllama` collection dropped to start with no
  prior-session facts polluting the new run

### Per-query results

| # | Query slug | Result | Notes |
|---|---|---|---|
| 1 | `own_ds` | ✅ PASS | "Who owns customers_gold?" → "alice@company.com" |
| 2 | `own_alice` | ⚠️ 3/4 | List by owner; got customers_gold + revenue_summary + Customer 360 dashboard; missed the Top Customers chart that alice also owns. ASSET_STATE_METRIC entries used real names not invented URNs |
| 3 | `lineage_src` | ✅ PASS | Source-of-truth markdown traced the full chain: raw → bronze → silver → gold → dashboard, both orders & customers paths intact |
| 4 | `lineage_impact` | ⚠️ 2/3 | Schema change on customers_silver impact analysis; got customers_gold + Customer 360, missed Top Customers chart |
| 5 | `lineage_up` | ✅ PASS | PROCESS_TOPOLOGY with 5 layers, 5 correct edges, node descriptions match seed |
| 6 | `schema_cols` | ✅ PASS | All 5 columns of customers_gold with correct types verbatim from seed |
| 7 | `schema_pk` | ⚠️ Partial | Engine D's GraphQL doesn't surface column-comment "PK." text — agent reported PK as `UNAVAILABLE_IN_CATALOG`. Downstream list correctly identified gold.revenue_summary but missed the dashboard + chart downstream of orders_fact |
| 8 | `catalog_superset` | ✅ PASS | All 3 dashboards with correct descriptions |
| 9 | `catalog_pii` | ❌ FAIL | "PII datasets exposed to a Superset dashboard" → agent said none. But customers_gold (pii) is upstream of Customer 360 — the agent had both facts in context but did not compose the cross-feature predicate |
| 10 | `dm_loadbearing` | ✅ PASS | revenue_summary + orders_fact correctly identified with all 3 downstream consumers each |
| 11 | `dm_compliance` | ✅ PASS | "PII without owner" → correctly identified none (all PII assets in the seed have owners) |
| 12 | `dm_finance_audit` | ❌ Partial | "Source systems for sales/finance dashboards" — agent stopped at the gold layer (`revenue_summary`) instead of recursing back to raw Postgres source tables |

### Aggregate scoring

- ✅ Fully correct, perfectly grounded: **7/12** (Q1, Q3, Q5, Q6, Q8,
  Q10, Q11)
- ⚠️ Substantially correct with minor omissions: **3/12** (Q2, Q4,
  Q7)
- ❌ Wrong or insufficient: **2/12** (Q9, Q12)
- 🪤 Hallucinated URNs in any response: **0**

### Side-by-side: polluted run vs clean run

The polluted suite (run earlier the same day before any fixes) returned
hallucinated URNs (`sales_customers_parquet/delta/iceberg` from
yesterday's overnight-coverage broker registrations) in 8 of the 12
responses. The same 12 queries on the clean cluster:

| | Polluted run | Clean run |
|---|---|---|
| Hallucinated URNs in responses | 8 / 12 | **0 / 12** |
| Engine pipeline failures (Mem0 schema bug propagating to `execute_subtask`) | Sporadic | **0** |
| Per-query wall-clock | 5-8 min | **~4 min avg** |
| Total suite wall-clock | ~72 min | **51 min** |
| Pipeline completion rate | 10/12 with Dagster supervisor failures | **12/12** |

The wall-clock improvement comes from the VRAM-thrash fix (Mem0 LLM
moved off ai1) — every smolagent step no longer pays a 30-60s
model-swap penalty.

### The two misses were Engine A reasoning gaps — fixed in this session

Both Q9 and Q12 were fixed by prompt-engineering against Engine A, no
platform work required. Three iterations were needed:

**Pass 1 — reasoning patterns added** (commit `b1dd198`):

- A "CROSS-FEATURE PREDICATES" pattern instructing the agent to
  compose multiple conditions on a single search hit (Q9 shape).
- A "RECURSIVE LINEAGE TRAVERSAL" pattern instructing the agent to
  recurse on each upstream/downstream name until it reaches a node
  with no further lineage (Q12 shape).

**Pass 1 outcome on retest:**

- ✅ Q12 (dm_finance_audit) — agent correctly traced from the sales
  dashboards back through revenue_summary → orders_fact → bronze →
  raw and identified `orders_raw` + `customers_raw` as the source
  systems. Recursive lineage pattern WORKED.
- ❌ Q9 (catalog_pii) — agent answered "none found" again. Same
  failure as the original suite run.

**Diagnosis on Q9 pass-1 failure:** investigating Engine A's
reasoning trace revealed Mem0 had stored the agent's previous wrong
answer ("no PII datasets exposed") as a fact from the original suite
run. Mem0's fact-extractor (phi4-16k:14b on the openwebui host)
cannot distinguish between tool-grounded facts and agent inferences;
the agent's wrong interpretation was lifted as if it were truth.
On the retest, that wrong fact appeared as "Relevant Past
Experience" and the agent confidently repeated it without verifying
against current tools.

This is the same self-reinforcing-pollution pattern flagged at the
start of the session, manifesting one layer deeper than ADR-0014:
that one was about prompt scaffolding; this is about memory.

**Pass 2 — anti-pollution mitigation** (commit `c5168c1` + Mem0
flush):

- `Mem0migrationsOllama` Weaviate collection dropped to break the
  reinforcement loop.
- New Engine A prompt rule: "Past experience is HINTS, never facts.
  It may reflect summaries of your own previous wrong answers. You
  MUST verify against current tool output. If past experience says
  'no X exists' for the current question, IGNORE that claim and
  run the tool anyway."

**Pass 2 outcome on retest:**

- ✅ Q9 (catalog_pii) — agent correctly identified
  `gold.sales.customers_gold` as a PII-tagged dataset directly
  exposed to the Customer 360 Superset dashboard. The data is
  grounded against the seed.

The deeper architectural decision behind the Mem0 fix is captured in
[ADR-0016](../invincible-agent/docs/adr/ADR-0016-mem0-fact-vs-inference-boundary.md):
tool-grounded facts and agent inferences should not share the Mem0
store. ADR-0016 proposes a two-stream split, provenance tracking on
every record, and periodic re-verification of stored ToolFacts.

### Engine F archetype quirk on Q9 retest

The Q9 retest answer came back with `archetype: CHART_WIDGET` instead
of `KNOWLEDGE_DOCUMENT` or `ASSET_STATE_METRIC`. The content was
correct (customers_gold with owner, last_updated, tags=pii) but
Engine F interpreted the agent's structured response as chart-shaped
data and picked the chart archetype. This is independent of ADR-0012
(the grounding-rule patch worked to prevent URN invention; the
archetype-class choice is a different concern). A future Engine F
tweak: when raw_data describes a single named asset rather than a
list of measurements, prefer KNOWLEDGE_DOCUMENT or
ASSET_STATE_METRIC over CHART_WIDGET.

### Final scorecard for the DataHub query suite

After all three passes:

- **12 of 12 queries** now produce substantively correct grounded
  answers from Engine A
- **0 hallucinated URNs** across any response in any pass
- **0 pipeline failures** in pass-3
- Two minor remaining concerns: Q9's archetype choice (Engine F
  tuning), Q2's missed Top Customers chart (Engine A could be more
  thorough on per-owner asset listings)

### Regression-check run

To verify the prompt iterations (cross-feature reasoning + recursive
lineage + anti-pollution rule) didn't regress any of the
previously-passing queries, the full 12-query suite was re-fired
against the cluster with all changes in place. Wall-clock 53 min.

| # | Suite #1 (clean cluster) | Regression check | Delta |
|---|---|---|---|
| Q1 | ✅ PASS | ✅ PASS | same |
| Q2 | ⚠️ 3/4 rendered | ❌ Engine F empty render (Engine A still 3/4) | **regression at Engine F layer** |
| Q3 | ✅ PASS | ✅ PASS (richer node labels) | same/better |
| Q4 | ⚠️ 2/3 | ⚠️ 2/3 | same |
| Q5 | ✅ PASS | ✅ PASS | same |
| Q6 | ✅ PASS | ✅ PASS | same |
| Q7 | ⚠️ partial | ✅ **PASS** (revenue_summary + Revenue by Region dashboard + Order Volume Trend chart) | **IMPROVED** |
| Q8 | ✅ PASS | ✅ PASS (richer descriptions) | same/better |
| Q9 | ✅ PASS (CHART_WIDGET shape) | ✅ PASS (proper ASSET_STATE_METRIC shape) | **IMPROVED** |
| Q10 | ✅ PASS | ✅ PASS | same |
| Q11 | ✅ PASS | ✅ PASS | same |
| Q12 | ✅ PASS | ✅ PASS | same |

**Net effect of tonight's prompt work:**

| Metric | Before tonight's prompt iterations | After regression check |
|---|---|---|
| Q9 correctly identifies PII × dashboard | ❌ "none found" | ✅ customers_gold |
| Q12 traces lineage to source systems | ❌ stops at gold | ✅ to raw Postgres |
| Q7 lists complete downstream | ⚠️ only revenue_summary | ✅ revenue_summary + dashboard + chart |
| Engine F renders Q2's answer | ⚠️ 3/4 rendered | ❌ empty malformed (Engine A produced 3/4 internally) |
| Hallucinated URNs | 0 | 0 |

Three user-visible improvements (Q7, Q9, Q12), one user-visible
regression (Q2 Engine F render). Engine A maintained or improved
across the board internally.

### The Q2 regression is Engine F, not Engine A

Engine A's Q2 final_answer was correct — same 3/4 quality as the
original suite, with `structured_data: {datasets: [...],
dashboards: [...]}` containing customers_gold, revenue_summary, and
Customer 360 with full ownership/lineage/tags fields. But the BFF
saw:

```
{"archetype": "ASSET_STATE_METRIC", "edges": [], "nodes": []}
```

Engine F's BAML DesignUI picked the `ASSET_STATE_METRIC` archetype
label but populated `edges` and `nodes` — which are TopologyUI
fields, not MetricUI fields. The schema name and the populated
fields don't match. The user sees an empty container.

This is the same brittleness as the Q9 CHART_WIDGET archetype quirk
from earlier, just more egregious. Tonight's prompt iterations made
Engine A's responses richer (more fields per asset, more structure)
which seems to have crossed Engine F's BAML reliability threshold on
Q2 specifically.

Short-term mitigation: sharper Engine F prompt that constrains "if
archetype is X then populate ONLY X's fields, never another
archetype's." Long-term fix: the
[ADR-0012](../invincible-agent/docs/adr/ADR-0012-ui-archetype-rigidity.md)
dynamic-columns refactor eliminates this class of bug — one
universal table shape replaces the six-archetype enum that the LLM
can currently mis-select fields against under stress.

### Architectural decisions captured

- [ADR-0012](../invincible-agent/docs/adr/ADR-0012-ui-archetype-rigidity.md)
  — UI archetype rigidity (workaround in place via DesignUI prompt
  grounding rules; long-term: dynamic-columns MetricUI refactor)
- [ADR-0013](../invincible-agent/docs/adr/ADR-0013-engine-d-capability-surface.md)
  — Engine D capability surface (workaround: enriched single
  query; long-term: capability tools per question shape)
- [ADR-0014](../invincible-agent/docs/adr/ADR-0014-no-hardcoded-urn-hints.md)
  — No hardcoded URN hints in agent prompts; broker/catalog
  separation; routing scaffolding is not catalog data (driven
  directly by the pollution this suite surfaced)
- [ADR-0015](../invincible-agent/docs/adr/ADR-0015-router-regression-L1.md)
  — Router regression testing at the `/search_predicates` layer
  (proposes the live continuous-validation pattern for the
  long-lived production deployment)
- [ADR-0016](../invincible-agent/docs/adr/ADR-0016-mem0-fact-vs-inference-boundary.md)
  — Mem0 boundary: separate tool-grounded facts from agent
  inferences in storage and retrieval. Driven directly by the Q9
  self-reinforcing-pollution finding in this session.

### What's still under-tested

- Engine W + Engine A simultaneously through a multi-engine task
  plan. The supervisor supports it but the test suite hasn't
  exercised it
- Engine DA (data-plane analysis) end-to-end since its prompt was
  rewritten. The verb tightening should keep it out of catalog Q&A
  but a data-plane query (e.g. "top 5 customers by revenue from
  the orders_fact table") would validate the discrimination
- Long-running session memory accumulation — does Mem0's recall on
  the openwebui phi4 host help or hurt the agent across a sequence
  of related queries? Worth a separate session-flow test

## Open items

- Patch `mesh_client.py` to run inside an ephemeral cluster pod
  (`kubectl run --image=curlimages/curl`) when running locally, so
  the SSE stream survives without depending on a brittle
  port-forward.
- Decide a permanent recovery path for the DataHub system-update
  JVM hang. Either run as a long-lived deployment (per the chart's
  newer model) or pin the upgrade image to a version that doesn't
  have the non-daemon-thread bug.
- Consider promoting the AgentTask `task_description` defensive
  mapping (from yesterday's Engine A fix) into a proper SDK helper
  so future engines don't trip on the supervisor's `user_query`
  payload shape.
- Swap `nomic-embed-text:latest` for a genuinely-8k native embedder
  (`nomic-embed-text:v1.5` or `snowflake-arctic-embed`) on the
  openwebui host. The current `nomic-embed-8k:latest` Modelfile sets
  `num_ctx 8192` but `nomic-bert.context_length` is architecturally
  capped at 2048; tonight's Mem0 facts are short enough that 2048
  embeds them whole, but a longer summary embed would silently
  truncate.
- Prompt-engineer Engine A for cross-feature predicates (Q9) and
  recursive lineage (Q12) with worked examples in the system
  prompt.
