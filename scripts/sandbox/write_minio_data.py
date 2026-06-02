"""Bootstrap script: writes the customers data into MinIO as parquet,
delta, and iceberg formats so each backend path in CortexDataClient
can be exercised against the same logical dataset."""
import io
import os
import polars as pl
import boto3
from botocore.client import Config

S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "http://iagent-minio:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minio-sandbox")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minio-sandbox-secret")
BUCKET = "iagent-data"

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

# Same shape as postgres + clickhouse so the agent can run the same SQL.
df = pl.DataFrame({
    "customer_id": [1, 2, 3, 4, 5, 6, 7],
    "name": ["Acme Corp", "Beta Inc", "Gamma LLC", "Delta Solutions",
             "Epsilon Corp", "Zeta Holdings", "Eta Partners"],
    "revenue": [50000.0, 75000.0, 120000.0, 95000.0, 110000.0, 42000.0, 88000.0],
})

# --- 1. Plain parquet ---
buf = io.BytesIO()
df.write_parquet(buf)
size = buf.tell()
buf.seek(0)
s3.upload_fileobj(buf, BUCKET, "sales_customers_parquet/data.parquet")
print(f"wrote parquet: s3://{BUCKET}/sales_customers_parquet/data.parquet ({size} bytes)")

# --- 2. Delta lake ---
# Use deltalake to write to MinIO. write_deltalake honors storage_options.
try:
    from deltalake import write_deltalake
    storage_options = {
        "AWS_ACCESS_KEY_ID": S3_ACCESS_KEY,
        "AWS_SECRET_ACCESS_KEY": S3_SECRET_KEY,
        "AWS_ENDPOINT_URL": S3_ENDPOINT,
        "AWS_REGION": "us-east-1",
        "AWS_ALLOW_HTTP": "true",
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
    }
    write_deltalake(
        f"s3://{BUCKET}/sales_customers_delta",
        df.to_arrow(),
        mode="overwrite",
        storage_options=storage_options,
    )
    print(f"wrote delta: s3://{BUCKET}/sales_customers_delta/")
except Exception as exc:
    print(f"DELTA SKIPPED: {type(exc).__name__}: {exc}")

# --- 3. Iceberg ---
# pyiceberg requires a catalog. SQL/in-memory catalog over the same MinIO.
try:
    from pyiceberg.catalog.sql import SqlCatalog

    catalog = SqlCatalog(
        "sandbox",
        **{
            "uri": "sqlite:////tmp/iceberg_catalog.db",
            "warehouse": f"s3://{BUCKET}/iceberg_warehouse",
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": S3_ACCESS_KEY,
            "s3.secret-access-key": S3_SECRET_KEY,
            "s3.region": "us-east-1",
        },
    )
    try:
        catalog.create_namespace("sales")
    except Exception:
        pass
    arrow_tbl = df.to_arrow()
    try:
        catalog.drop_table("sales.customers")
    except Exception:
        pass
    iceberg_tbl = catalog.create_table(
        "sales.customers",
        schema=arrow_tbl.schema,
    )
    iceberg_tbl.append(arrow_tbl)
    print(f"wrote iceberg: s3://{BUCKET}/iceberg_warehouse/ sales.customers")
except Exception as exc:
    print(f"ICEBERG SKIPPED: {type(exc).__name__}: {exc}")

print("done")
