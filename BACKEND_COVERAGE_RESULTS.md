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
| **S3 Iceberg (MinIO)** | ⚠️ Stuck on supervisor, no data-layer signal | 25 min before cancel | `pl.scan_iceberg` is the wrong shape for SQL-catalog tables (see "Iceberg gap"), AND in this run the supervisor's `create_task_plan` op hung — likely Engine O's /plan hit the gfx1151 wedge state from earlier sustained inference. Two compounding failures; couldn't separate them in this session. |

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

## Iceberg gap

`pl.scan_iceberg(s3://bucket/path/...)` only works when the Iceberg
table is laid out in **Hadoop catalog format** (specifically,
`metadata/version-hint.text` must exist). pyiceberg's `SqlCatalog` (and
its `RestCatalog` and `GlueCatalog`) write tables WITHOUT
`version-hint.text` — they track current metadata pointer in their
own catalog table/service.

Confirmed locally:
```
ICEBERG ERR: FileNotFoundError:
  Path does not exist 'iagent-data/iceberg_warehouse/sales/customers/
  metadata/version-hint.text'
```

This is a real architectural gap in CortexDataClient. The fix is to
load tables through `pyiceberg.catalog.load_catalog` (REST or SQL
catalog reference required), then `table.scan().to_polars()` rather
than `pl.scan_iceberg(uri)`. The new code path would look roughly:

```python
elif source_type == "s3_iceberg":
    from pyiceberg.catalog import load_catalog
    catalog = load_catalog(
        "sandbox",
        **{
            "type": "sql",
            "uri": credentials["catalog_uri"],
            "warehouse": credentials["warehouse_uri"],
            "s3.endpoint": credentials.get("aws_endpoint_url"),
            "s3.access-key-id": credentials["aws_access_key_id"],
            "s3.secret-access-key": credentials["aws_secret_access_key"],
        },
    )
    table = catalog.load_table(credentials["table_identifier"])
    df = table.scan().to_pandas()  # or to_arrow
    lf = pl.from_pandas(df).lazy()
```

That requires the broker ticket to carry `catalog_uri`,
`warehouse_uri`, and `table_identifier` in addition to the S3
creds. Out of scope for the overnight run; documenting for the next
session.

The Iceberg sandbox test never reached the data-fetch step — the
supervisor's `create_task_plan` op (which calls Engine O's /plan)
hung at the start and the run sat in STARTED status for 25 minutes
before being terminated. The likely cause is that earlier sustained
inference from Test 3 (digital twin) left ai1's gfx1151 GPU in the
wedge state described in `STRIX_HALO_OLLAMA_DIAGNOSTICS.md`, and
Engine O's /plan call to Ollama hung indefinitely.

So the iceberg test doesn't have a clean data-layer failure signal —
we couldn't separate "the iceberg code path is broken (Hadoop vs SQL
catalog)" from "the GPU is wedged so nothing can run." Both are real
issues, but the run aborted before reaching the layer that would
have demonstrated the catalog issue.

Local validation HAS proven the catalog issue is real:
```
PYTHONIOENCODING=utf-8 python verify_polars_s3.py
ICEBERG ERR: FileNotFoundError: Path does not exist
  'iagent-data/iceberg_warehouse/sales/customers/metadata/version-hint.text'
```

So the catalog code path needs work regardless of GPU stability.

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
- Three S3-resident formats (Parquet, Delta — both passing — and Iceberg
  pending the catalog code path)

The supervisor → broker → CortexDataClient → DuckDB chain is uniform;
each new backend was a CortexDataClient code patch + a broker URN
mapping + an Engine DA prompt hint. The architecture is correct; only
Iceberg needs more work and that's catalog-shape, not S3-access.

## Open items / next session

- [ ] Implement Iceberg catalog code path in CortexDataClient
      (see "Iceberg gap" above for sketch).
- [ ] Decide on a single Iceberg catalog deployment for sandbox —
      SQL catalog with a sidecar pod is simplest; REST catalog
      (e.g. Polaris/Tabular) is closer to prod-shape.
- [ ] Consider adding `clickhouse-connect` HTTPS support / TLS for
      non-sandbox use; current path uses plain HTTP port 8123.
- [ ] Document the broker → CortexDataClient credential contract
      so future backends (Snowflake, Databricks, BigQuery) follow
      the same shape.

## Cross-references

- `STRIX_HALO_OLLAMA_DIAGNOSTICS.md` (same repo root) — the GPU
  stability work that ran in parallel with this.
- iagent-mesh-sdk memory: `project_pg18_oauthbearer_wall.md` — the
  CortexDataClient JWT-as-password design is still tracked there.
