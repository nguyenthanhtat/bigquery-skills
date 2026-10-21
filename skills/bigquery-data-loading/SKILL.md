---
name: bigquery-data-loading
description: "Get data into and out of Google BigQuery: batch loads from GCS or local files (CSV, JSON, Avro, Parquet, ORC) with bq load or LOAD DATA, streaming with the Storage Write API, upserts with MERGE, external/BigLake tables over GCS, and exports with EXPORT DATA or bq extract. Use when the user wants to load, import, ingest, stream, upsert, or export BigQuery data, or a load/export job fails."
---

# BigQuery data loading & export

Answer in the user's language. When the problem is project-wide (many failing loads, ingestion cost) → suggest the bq-audit skill.

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

## First, establish
1. **Source and volume**: GCS / local file / app events / another database; rows per day; batch or continuous.
2. **Latency need**: minutes-to-hours → batch load (free on the shared slot pool). Seconds → Storage Write API.
3. **Write semantics**: append, upsert (dedupe on a key), or replace one partition. Never default to replacing the whole table.
4. **Location**: the dataset and the GCS bucket must be in compatible locations (same region, or bucket in a region inside the dataset's multi-region). Mismatch → `Not found ... in location` or "Cannot read and write in different locations".
5. **Permissions**: `roles/bigquery.dataEditor` on the dataset, `roles/bigquery.jobUser` on the project, `roles/storage.objectViewer` on the bucket (objectCreator for exports).

## Choosing a method

| Need | Use |
|---|---|
| Files in GCS, periodic | `bq load` / `LOAD DATA` (free; quotas: 15 TB per load job, 10,000 URIs per job, 1,500 loads per table per day) |
| Continuous events, seconds latency | Storage Write API (default stream = at-least-once; committed stream with offsets = exactly-once) |
| Query files without loading | External or BigLake table (hive partitioning prunes by path) |
| CDC / upsert from staging | Load to staging → `MERGE` with a deduplicated source |
| Managed recurring sources (GCS, S3, SaaS) | BigQuery Data Transfer Service |
| Pub/Sub topic | Pub/Sub BigQuery subscription (no code) |

Legacy streaming (`tabledata.insertAll` / Python `insert_rows_json`) still works but is not the recommended path: it costs more per GB, has no exactly-once, and rows in its streaming buffer can't be modified by DML for up to ~90 minutes.

## Formats
- Prefer **Avro** (schema embedded, parallel, logical types) or **Parquet/ORC** (columnar, schema embedded). Format affects load speed and schema fidelity, not query speed once loaded.
- CSV/JSON: gzip is detected automatically, but compressed CSV/JSON can't be split, so loads are slower and limited to 4 GB per compressed file. Uncompressed files load in parallel.
- Parquet: set `--parquet_enable_list_inference` so LIST types become ARRAYs instead of nested `list.element` records.
- Avro: `--use_avro_logical_types` so timestamp/date logical types map to TIMESTAMP/DATE.
- Schema autodetect samples only part of the file (CSV up to 500 rows): a column that is empty early may be typed wrong; IDs with leading zeros become INT64. Give an explicit schema for anything recurring.

## Batch load patterns

```bash
# Append CSV files with an explicit schema
bq load --location=US --source_format=CSV --skip_leading_rows=1 \
  --write_disposition=WRITE_APPEND \
  mydataset.orders "gs://my-bucket/orders/2026-10-*.csv" ./orders_schema.json

# Parquet into one partition, replacing only that day (idempotent rerun)
bq load --location=US --source_format=PARQUET --replace \
  'mydataset.events$20261020' "gs://my-bucket/events/dt=2026-10-20/*.parquet"
```

`--replace` / `WRITE_TRUNCATE` overwrites data **and schema** of the target. Only use it on a partition decorator (`table$YYYYMMDD`) or a staging table, never on a shared table without the user's explicit OK. `WRITE_EMPTY` is the safe choice for one-off loads into new tables.

SQL equivalent:
```sql
LOAD DATA INTO mydataset.orders
FROM FILES (format = 'PARQUET', uris = ['gs://my-bucket/orders/*.parquet']);
-- LOAD DATA OVERWRITE replaces the table — same caution as WRITE_TRUNCATE.
```

### Bad records
`--max_bad_records=N` silently skips rows. If you use it, always check what was dropped:
```bash
bq show --format=prettyjson -j <job_id>   # status.errors lists skipped rows
```
and compare loaded row count (`statistics.load.outputRows`) to the source count. Prefer fixing the source over skipping.

### Schema evolution
New nullable columns or relaxed REQUIRED→NULLABLE during append:
```bash
bq load --schema_update_options=ALLOW_FIELD_ADDITION,ALLOW_FIELD_RELAXATION ...
```
Type changes are not allowed by load; see the bigquery-schema-design skill.

### Python load job
```python
from google.cloud import bigquery

client = bigquery.Client(project="my-project")
job_config = bigquery.LoadJobConfig(
    source_format=bigquery.SourceFormat.PARQUET,
    write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
)
job = client.load_table_from_uri(
    "gs://my-bucket/events/*.parquet", "my-project.mydataset.events",
    job_config=job_config, location="US",
)
job.result()  # raises on failure
print(job.output_rows, "rows loaded")
```

## Streaming: Storage Write API
Rows are queryable within seconds. Pricing is per GiB ingested with a monthly free tier; check current pricing.

```python
# pip install google-cloud-bigquery-storage protobuf
from google.cloud import bigquery_storage_v1
from google.cloud.bigquery_storage_v1 import types, writer
from google.protobuf import descriptor_pb2
import event_pb2  # generated from a .proto matching the table schema

client = bigquery_storage_v1.BigQueryWriteClient()
parent = client.table_path("my-project", "mydataset", "events")
stream_name = f"{parent}/streams/_default"  # default stream: at-least-once

proto_schema = types.ProtoSchema()
proto_descriptor = descriptor_pb2.DescriptorProto()
event_pb2.Event.DESCRIPTOR.CopyToProto(proto_descriptor)
proto_schema.proto_descriptor = proto_descriptor

template = types.AppendRowsRequest(write_stream=stream_name)
template.proto_rows = types.AppendRowsRequest.ProtoData(writer_schema=proto_schema)
stream = writer.AppendRowsStream(client, template)

rows = types.ProtoRows()
rows.serialized_rows.append(event_pb2.Event(event_id="e1", event_name="click").SerializeToString())
req = types.AppendRowsRequest()
req.proto_rows = types.AppendRowsRequest.ProtoData(rows=rows)
stream.send(req).result()
stream.close()
```
- Batch rows per append (hundreds to thousands); reuse the stream/connection.
- Exactly-once: create a COMMITTED stream and pass offsets; retries with the same offset are deduplicated.
- CDC: tables with a primary key can take upserts/deletes through `_CHANGE_TYPE` (UPSERT/DELETE).
- If the user must keep `insert_rows_json`: max 50,000 rows and 10 MB per request (≈500 rows recommended), set `row_ids` for best-effort dedup, and expect DML on fresh rows to fail while they are in the streaming buffer.

## Upsert with MERGE
Deduplicate the source first — MERGE fails if more than one source row matches a target row.
```sql
MERGE mydataset.customers T
USING (
  SELECT * EXCEPT(rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC) rn
    FROM mydataset.customers_staging)
  WHERE rn = 1
) S
ON T.customer_id = S.customer_id
WHEN MATCHED AND S.updated_at > T.updated_at THEN
  UPDATE SET name = S.name, email = S.email, updated_at = S.updated_at
WHEN NOT MATCHED THEN
  INSERT (customer_id, name, email, updated_at) VALUES (S.customer_id, S.name, S.email, S.updated_at);
```
On a partitioned target, add a partition filter to the ON clause (e.g. `AND T.event_date >= '2026-10-01'`) so MERGE doesn't scan the whole table. Dry-run it first.

## External and BigLake tables
```sql
CREATE EXTERNAL TABLE mydataset.raw_events
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://my-bucket/events/*'],
  hive_partition_uri_prefix = 'gs://my-bucket/events'
);
```
- Hive partition paths (`.../dt=2026-10-20/...`) are pruned when queries filter on `dt`.
- BigLake (`WITH CONNECTION`) adds fine-grained security and metadata caching; prefer it for governed lakes and Iceberg.
- Queries read GCS every time — for hot data, load it.

## Export
Export jobs on the shared pool are free (you pay GCS storage/egress). Each output file is at most 1 GB, so exports of larger tables **need a wildcard URI**.
```sql
EXPORT DATA OPTIONS (
  uri = 'gs://my-bucket/exports/orders/*.parquet',
  format = 'PARQUET',
  overwrite = true
) AS
SELECT * FROM mydataset.orders WHERE order_date >= '2026-10-01';
```
```bash
bq extract --location=US --destination_format=AVRO \
  mydataset.orders "gs://my-bucket/exports/orders/*.avro"
```
Copy files with `gcloud storage cp` / `gcloud storage ls` (gsutil is deprecated).

## Troubleshooting loads
| Error | Fix |
|---|---|
| `Not found: ... in location X` | dataset/bucket location mismatch, or `--location` missing |
| `Provided Schema does not match` | add `--schema_update_options` or fix the schema file |
| `Error while reading data ... CSV` | quoting/delimiter; `--allow_quoted_newlines`, `--field_delimiter`, check encoding (UTF-8 default; `--encoding=ISO-8859-1` otherwise) |
| `UPDATE or DELETE statement ... streaming buffer` | rows came from legacy insertAll; wait or move to Storage Write API |
| `Exceeded rate limits: too many table update operations` | batch loads into fewer, larger jobs |

Read a failed job with `bq show --format=prettyjson -j <job_id>`.
