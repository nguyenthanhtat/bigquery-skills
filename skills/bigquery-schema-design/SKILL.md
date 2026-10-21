---
name: bigquery-schema-design
description: "Design and change Google BigQuery tables: partitioning (time, ingestion-time, integer range), clustering, data types, nested/repeated fields, schema changes, retention and expiration of old data, and safely repartitioning or reclustering an existing table. Use when the user creates or restructures a BigQuery table, asks how to partition or cluster, wants old data deleted automatically, or needs to change a column or schema."
---

# BigQuery schema design

Answer in the user's language. When the problem is project-wide (many tables unpartitioned, storage cost) → suggest the bq-audit skill.

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

## First, establish
1. **How the table is queried**: which column nearly every query filters on (usually a date/timestamp), and which columns are filtered/joined next.
2. **Size and growth**: GB/day, total size, retention needed.
3. **Write pattern**: append-only, daily partition overwrite, upserts (MERGE), streaming.
4. Inspect what exists before changing it:
```sql
SELECT ddl FROM mydataset.INFORMATION_SCHEMA.TABLES WHERE table_name = 'events';
SELECT * FROM mydataset.INFORMATION_SCHEMA.TABLE_OPTIONS WHERE table_name = 'events';
```

## Partitioning
Partition when the table is large (rule of thumb: >10 GB) and queries filter by one column.

| Type | When | DDL |
|---|---|---|
| Time-unit column | Event/business timestamp exists | `PARTITION BY DATE(event_ts)` or `TIMESTAMP_TRUNC(event_ts, HOUR)` / `DATE_TRUNC(d, MONTH)` |
| Ingestion time | No reliable timestamp | `PARTITION BY _PARTITIONDATE` or `TIMESTAMP_TRUNC(_PARTITIONTIME, DAY)` |
| Integer range | Partition by an integer key | `PARTITION BY RANGE_BUCKET(customer_id, GENERATE_ARRAY(0, 1000000, 10000))` |

- Limits: **10,000 partitions per table** (daily ≈ 27 years); a single job can modify at most **4,000 partitions** — split large backfills by date range. If partitions would average <1 GB, prefer coarser granularity (MONTH/YEAR) plus clustering on the date.
- `require_partition_filter = TRUE` on large tables blocks accidental full scans (queries without a filter on the partition column fail).
- Pruning only works when the filter is on the partition column in a form BigQuery can use: `WHERE DATE(event_ts) BETWEEN ...` on a `DATE(event_ts)` partition is fine; wrapping the column in other functions (`FORMAT_TIMESTAMP`, `CAST(... AS STRING)`) or comparing to a subquery result may prevent it. Verify with a dry run: bytes should drop.
- Ingestion-time partitioned tables **cannot be created with CTAS**. Create the empty table with DDL, then INSERT.

```sql
CREATE TABLE mydataset.events (
  event_id STRING NOT NULL,
  event_ts TIMESTAMP NOT NULL,
  event_name STRING,
  user_id STRING,
  params JSON
)
PARTITION BY DATE(event_ts)
CLUSTER BY event_name, user_id
OPTIONS (require_partition_filter = TRUE);
```

## Clustering
- Up to **4 columns**, top-level, non-repeated. Order by how often they are filtered, most-filtered first. FLOAT64 and JSON columns can't be clustering columns.
- Good: IDs, event names, status, country. Pointless: columns never filtered on.
- Works with or without partitioning; on small partitions it can replace partitioning.
- Change on an existing table:
```bash
bq update --clustering_fields=event_name,user_id mydataset.events
```
This applies to data written afterwards; existing data is not reorganized until rewritten. To recluster history, rewrite into a new table (see below).

## Types
- IDs: INT64 if numeric (smaller, faster joins); STRING for UUIDs or IDs with leading zeros/letters.
- Money: NUMERIC/BIGNUMERIC, never FLOAT64.
- Time: TIMESTAMP for instants (UTC), DATE for calendar dates, DATETIME only for wall-clock without zone.
- Semi-structured: JSON type (`PARSE_JSON`, `TO_JSON`, `JSON_VALUE`) or STRUCT/ARRAY when the shape is known. `TO_JSON_STRING` returns STRING, not JSON.
- Nested/repeated fields avoid joins for 1-to-many data (order → line items):
```sql
CREATE TABLE mydataset.orders (
  order_id STRING NOT NULL,
  order_date DATE NOT NULL,
  customer STRUCT<id STRING, name STRING, email STRING>,
  items ARRAY<STRUCT<sku STRING, qty INT64, price NUMERIC>>
)
PARTITION BY order_date
CLUSTER BY order_id;

-- Build from normalized tables: aggregate with GROUP BY
SELECT o.order_id, o.order_date,
       STRUCT(c.id, c.name, c.email) AS customer,
       ARRAY_AGG(STRUCT(i.sku, i.qty, i.price)) AS items
FROM mydataset.orders_flat o
JOIN mydataset.customers c ON c.id = o.customer_id
JOIN mydataset.order_items i ON i.order_id = o.order_id
GROUP BY o.order_id, o.order_date, c.id, c.name, c.email;

-- Query: field names must match the STRUCT definition
SELECT order_id, customer.name, item.sku
FROM mydataset.orders, UNNEST(items) AS item
WHERE order_date = '2026-10-20';
```
- Primary/foreign keys can be declared `NOT ENFORCED`; they help the optimizer (join elimination) but don't validate data.

## Schema changes
| Change | How |
|---|---|
| Add NULLABLE column | `ALTER TABLE t ADD COLUMN c STRING` |
| Add REQUIRED column | Not allowed on existing tables — add NULLABLE, backfill, enforce in pipeline |
| Relax NOT NULL | `ALTER TABLE t ALTER COLUMN c DROP NOT NULL` |
| Widen type | `ALTER TABLE t ALTER COLUMN c SET DATA TYPE NUMERIC` (INT64→NUMERIC/BIGNUMERIC/FLOAT64, NUMERIC→BIGNUMERIC/FLOAT64) |
| Rename / drop column | `ALTER TABLE t RENAME COLUMN a TO b`, `ALTER TABLE t DROP COLUMN c` (dropped column storage is freed after time travel) |
| Other type change, repartition, recluster history | Rewrite into a new table (below) |
| Default value | `ALTER TABLE t ALTER COLUMN c SET DEFAULT CURRENT_TIMESTAMP()` |

## Repartition / restructure an existing table safely
A table can't be partitioned or re-partitioned in place.
1. Estimate cost: dry-run the SELECT (it scans the whole table).
2. Create the new table alongside:
```sql
CREATE TABLE mydataset.events_new
PARTITION BY DATE(event_ts)
CLUSTER BY event_name, user_id
OPTIONS (require_partition_filter = TRUE)
AS SELECT * FROM mydataset.events;
```
3. Verify: row counts (overall and per day), a few checksums/aggregates match.
4. Pause or redirect writers (scheduled queries, loads, streams), copy any rows written meanwhile. A table with rows still in the legacy streaming buffer can't be renamed — wait for the buffer to flush (`bq show` → no `streamingBuffer`).
5. Swap names in a quiet window:
```sql
ALTER TABLE mydataset.events RENAME TO events_old;
ALTER TABLE mydataset.events_new RENAME TO events;
```
Views referencing the table by name keep working; jobs/streams writing by table ID must be checked.
6. Keep `events_old` for rollback with an expiration: `ALTER TABLE mydataset.events_old SET OPTIONS (expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 14 DAY));`

## Retention: deleting old data automatically
- **Partitioned table** → partition expiration deletes whole partitions older than N days:
```sql
ALTER TABLE mydataset.events SET OPTIONS (partition_expiration_days = 365);
```
Takes effect immediately for existing partitions past the limit — confirm the number and back up first if unsure (snapshot or export).
- **Not partitioned** → partition it first (above), or a scheduled `DELETE FROM t WHERE event_date < DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)` (dry-run; DML on large tables is costly).
- **`expiration_timestamp` deletes the entire table** at that time — use it only for temp/staging tables, never to trim old rows.
- Dataset defaults: `default_partition_expiration_days`, `default_table_expiration_days` (scratch datasets).

## Recovery and copies
- Time travel: query or copy the table as of any point in the window (2–7 days, `max_time_travel_hours`, default 7 days): `SELECT * FROM t FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)`. A **dropped** table is restored with `bq cp mydataset.t@<epoch_ms> mydataset.t_restored`.
- Fail-safe: 7 more days after time travel, recoverable only through Google support.
- Table snapshot (`CREATE SNAPSHOT TABLE ... CLONE t`) = cheap read-only point-in-time copy; table clone (`CREATE TABLE ... CLONE t`) = writable copy billed only for changed data. Use before risky changes.

## Storage billing
- Logical (default): bills uncompressed bytes; active vs long-term (table/partition unmodified 90 days → ~50% cheaper). Time travel and fail-safe are free.
- Physical: bills compressed bytes at a higher per-GiB rate, plus time travel and fail-safe. Usually cheaper when compression ratio is high. Set per dataset: `ALTER SCHEMA mydataset SET OPTIONS (storage_billing_model = 'PHYSICAL')`; can't change again for 14 days. Compare with `INFORMATION_SCHEMA.TABLE_STORAGE` before switching.
