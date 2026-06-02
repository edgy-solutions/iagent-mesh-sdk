# DA Backend Coverage Results — Overnight Run

Captured 2026-06-02 overnight. Extends the DA happy-path Test 1
(originally proven against Postgres yesterday) to every backend the
mesh is supposed to support.

## TL;DR

| Backend | Result | Wall-clock | Notes |
|---|---|---|---|
| **Postgres** | ✅ PASS | ~270s | Yesterday's baseline. `pl.read_database_uri` via connectorx. |
| **ClickHouse** | ✅ PASS | 264s | `clickhouse-connect` Arrow path. `connectorx` doesn't speak clickhouse. |
| **S3 Parquet (MinIO)** | ✅ PASS | 236s | `pl.scan_parquet` + `aws_endpoint_url` + `aws_allow_http=true`. |
| **S3 Delta Lake (MinIO)** | ✅ PASS | 249s | `pl.scan_delta` + same storage_options. `deltalake` package required. |
| **S3 Iceberg (MinIO)** | ✅ PASS | 313s | (after the fix described in "Iceberg fix landed" below) — `pyiceberg.load_catalog` + `catalog.load_table()` + `pl.scan_iceberg(table_obj)` against a Postgres-backed SqlCatalog. |
| **Engine A (mesh:analyzeWithCodeAgent)** | ✅ PASS | 289s | (after the fixes described in "Engine A path" below) — supervisor routed to Engine A on a maintenance-domain query; smolagent ran tool calls, returned KNOWLEDGE_DOCUMENT via Engine F. |

Same logical data returned correctly in every case: top-5 customers by
revenue, descending — Gamma LLC (120k), Epsilon Corp (110k), Delta
Solutions (95k), Eta Partners (88k), Beta Inc (75k).

## What changed (code)

### dag-tools — `dag_tools/cortex_data/client.py`

**ClickHouse:** Replaced the broken `pl.read_database_uri` clickhouse
path (connectorx has no clickhouse driver) with the official
`clickhouse-connect` Arrow query path:

```python
client = clickhouse_connect.get_client(
    host=host, port=port_int,
    username=username, password=password, database=db_name,
)
arrow_table = client.query_arrow(f"SELECT * FROM {table}")
lf = pl.from_arrow(arrow_table).lazy()
```

Also fixed the credential lookup — broker sends `credentials.password`
but the code was reading `credentials.token`.

**S3 (parquet / delta / iceberg):** Centralized storage_options
construction so all three paths honor `aws_endpoint_url`,
`aws_allow_http`, and `aws_region`:

```python
def _s3_storage_options() -> Dict[str, Any]:
    opts = {
        "aws_access_key_id": credentials.get("aws_access_key_id", ""),
        "aws_secret_access_key": credentials.get("aws_secret_access_key", ""),
    }
    if (endpoint_url := credentials.get("aws_endpoint_url")):
        opts["aws_endpoint_url"] = endpoint_url
        if endpoint_url.startswith("http://"):
            opts["aws_allow_http"] = "true"
    if (region := credentials.get("aws_region")):
        opts["aws_region"] = region
    return opts
```

Without `aws_endpoint_url`, the object_store backend tries to resolve
`s3.amazonaws.com`. With it (and `aws_allow_http=true` for the
http://minio:9000 case), MinIO works as a drop-in S3.

### dag-tools — `pyproject.toml`

Added:
- `clickhouse-connect>=0.8` (Arrow query path)
- `deltalake>=0.20` (delta-rs runtime)
- `pyiceberg>=0.7` (iceberg REST/SQL catalog client)

### invincible-agent — `agent_fleet/data_analyst/main.py`

Engine DA's smolagent prompt now lists every backend with the same
customers schema. The agent picks the URN that matches the user's
stated backend (e.g. "the clickhouse sales dataset" → clickhouse URN).

## What changed (infra in sandbox)

### New deployments

- **`iagent-clickhouse-0`** — StatefulSet, ClickHouse 24.8, HTTP port 8123,
  native port 9000. Seeded with `iagent.customers` (same 7 rows).
- **`iagent-minio-0`** — StatefulSet, MinIO latest, port 9000.
  Bucket `iagent-data` created via `mc mb`.
- **Same data seeded as parquet, delta, and iceberg** by a local Python
  script run from the host (the in-cluster seed pod was OOM-killed for
  ephemeral storage during pip install — see "Gotchas" below).

### Domain broker extended (`c:/tmp/sandbox-domain-broker.yaml`)

`LOCAL_ASSETS` now maps four new URNs:

```
urn:li:dataset:(urn:li:dataPlatform:clickhouse,sales_customers,PROD)
urn:li:dataset:(urn:li:dataPlatform:s3,sales_customers_parquet,PROD)
urn:li:dataset:(urn:li:dataPlatform:s3,sales_customers_delta,PROD)
urn:li:dataset:(urn:li:dataPlatform:s3,sales_customers_iceberg,PROD)
```

`/api/v1/internal/resolve` now handles all four `io_manager_type`
values — `postgres`, `clickhouse`, `s3_parquet`, `s3_delta`,
`s3_iceberg` — and returns the right credentials shape for each
(including `aws_endpoint_url` for S3 backends pointing at MinIO).

Broker pod env extended with `CH_*` and `S3_*` variables.

## Iceberg fix landed

The first iceberg run failed because `pl.scan_iceberg(s3://bucket/path/...)`
only works when the Iceberg table is laid out in **Hadoop catalog
format** (specifically, `metadata/version-hint.text` must exist).
pyiceberg's `SqlCatalog` (and its `RestCatalog` and `GlueCatalog`)
write tables WITHOUT `version-hint.text` — they track current metadata
pointer in their own catalog table/service.

**Final solution (commit `c002b77` in dag-tools):** load the table
through `pyiceberg.catalog.load_catalog()`, call `load_table()`, then
pass the Table OBJECT to `pl.scan_iceberg(table)`. Polars 1.x accepts
both forms.

Sandbox plumbing for the fix:
- Created a `iceberg_catalog` database on `iagent-postgresql`
- Re-seeded the table using `pyiceberg.SqlCatalog` with the Postgres
  URI as `uri` and `s3://iagent-data/iceberg_warehouse_pg` as warehouse
- Domain broker now returns these extras in `s3_iceberg` credentials:
  ```
  catalog_uri      = postgresql+psycopg2://iagent:.../iceberg_catalog
  warehouse_uri    = s3://iagent-data/iceberg_warehouse_pg
  table_identifier = sales.customers
  catalog_type     = sql
  ```
- CortexDataClient's `s3_iceberg` branch consumes those + the existing
  S3 storage keys to build the catalog and load the table.

The original failure signature (preserved here so future readers can
recognize the same symptom in other deployments):
```
ICEBERG ERR: FileNotFoundError:
  Path does not exist 'iagent-data/iceberg_warehouse/sales/customers/
  metadata/version-hint.text'
```

If you see that, the table was written by a SQL/REST/Glue catalog
but the reader is using the bare-URI form of `pl.scan_iceberg`.
Switch to the catalog form (as we did) and the table loads.

## Gotchas observed overnight

1. **Seed pod OOM-killed by ephemeral storage** — `pip install
   polars boto3 pyarrow deltalake pyiceberg sqlalchemy` chewed through
   the k3s node's `/var/lib/kubelet` budget on `k3s-worker1`. Pivoted
   to running the seed from the local host via port-forward to MinIO.
   For future cluster-side seeding work, schedule on `k3s-worker6`
   (more disk) or pre-build a custom image.

2. **`buf.getvalue()` after `df.write_parquet(buf)` raises
   `ValueError: I/O operation on closed file`** — Polars closes the
   BytesIO after parquet write. Capture `buf.tell()` before the
   write completes, or use `len(buf.getvalue())` BEFORE
   `seek(0)` and the close happens. Fixed in `write_minio_data.py`.

3. **Polars "Unable to resolve region for bucket" warning** — benign,
   appears even when `aws_region` is provided. object_store probes
   the bucket for a `region` header on EC2-style hostnames first. Not
   relevant for MinIO operation.

4. **Windows console + Polars pretty-print** — cp1252 can't render
   the box-drawing chars in `print(df)`. Either set
   `PYTHONIOENCODING=utf-8` or use a simpler `f"shape={df.shape}, ..."`.

## Path summary

The DA flow now demonstrably works against 5 distinct backend shapes:
- One relational over wire protocol (Postgres via ADBC)
- One columnar OLAP over wire protocol (ClickHouse via clickhouse-connect)
- Three S3-resident formats (Parquet, Delta, Iceberg — all passing,
  Iceberg via a Postgres-backed SqlCatalog)

Plus the Engine A path (mesh:analyzeWithCodeAgent) — smolagent loop
through the Restate ingress, validated on a maintenance-domain query.

The supervisor → broker → CortexDataClient → DuckDB chain is uniform;
each new backend was a CortexDataClient code patch + a broker URN
mapping + an Engine DA prompt hint. The architecture extends cleanly.

## Engine A path

The Engine A test (`mesh:analyzeWithCodeAgent`) needed two fixes
beyond what was already in main:

1. **`analyze_proxy` timeout 300s → 900s** — same shape as the
   Engine E proxy bug from yesterday. The httpx call to the Restate
   ingress had a 300s cap, but slow Ollama backends make the
   smolagent loop take longer; the proxy returned 502 mid-loop and
   the supervisor reported a pipeline failure.

2. **Defensive payload mapping in the handler** — Engine A's BAML
   contract requires `task_description` and `dataset_id`. The
   supervisor sends `user_query` and (for analyst-style queries)
   no `dataset_id`. Engine A's `AgentTask(**request)` instantiation
   tripped a pydantic `ValidationError` on every invocation. Since
   Restate's retry policy keeps re-firing failed invocations, the
   proxy's call to the ingress hung in a retry loop and the
   supervisor eventually timed out anyway.

   Fix: `request.setdefault("task_description", request.get("user_query") or "Analyze")`
   and `request.setdefault("dataset_id", "")` before constructing
   the AgentTask. Direct callers using the canonical AgentTask
   shape still work.

After both fixes, Engine A completed a maintenance-domain query end
to end (289s wall-clock). The agent honestly reported that DataHub
(in mock mode in sandbox) had no failure-mode data rather than
hallucinating — which is the desired grounded behavior.

## Open items / next session

- [x] ~~Implement Iceberg catalog code path in CortexDataClient~~
      — done via `pyiceberg.load_catalog` + Table-object form of
      `pl.scan_iceberg` (commit `c002b77` in dag-tools).
- [ ] Decide on a longer-term Iceberg catalog deployment for
      sandbox — current setup uses a `iceberg_catalog` database on
      the existing `iagent-postgresql`. A dedicated REST catalog
      (Polaris/Tabular) would be closer to prod-shape, but the
      SqlCatalog approach is the lowest-friction option and
      validates the same client code path.
- [ ] Consider adding `clickhouse-connect` HTTPS support / TLS for
      non-sandbox use; current path uses plain HTTP port 8123.
- [ ] Document the broker → CortexDataClient credential contract
      so future backends (Snowflake, Databricks, BigQuery) follow
      the same shape.
- [ ] Promote the Engine A `task_description` defensive mapping
      into a proper SDK helper so future engines avoid the same
      pydantic-ValidationError-into-Restate-retry-loop trap.

## Cross-references

- `STRIX_HALO_OLLAMA_DIAGNOSTICS.md` (same repo root) — the GPU
  stability work that ran in parallel with this.
- iagent-mesh-sdk memory: `project_pg18_oauthbearer_wall.md` — the
  CortexDataClient JWT-as-password design is still tracked there.
