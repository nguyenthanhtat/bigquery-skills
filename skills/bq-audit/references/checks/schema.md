# Schema & storage checks

## S1 — Large, frequently queried table not partitioned
- Choose the column most queries filter by: event date/timestamp (DAY/HOUR/MONTH), ingestion time, or an INTEGER range. Up to 10,000 partitions per table.
- An existing table cannot be repartitioned in place. Safe path (requires approval):
  1. Dry-run the copy to know its cost.
  2. `CREATE TABLE \`p.ds.t_new\` PARTITION BY DATE(ts) CLUSTER BY a, b AS SELECT * FROM \`p.ds.t\`;` (a CTAS cannot create an *ingestion-time* partitioned table; for that, create the empty table with DDL then INSERT).
  3. Compare row counts; repoint writers; in a maintenance window rename (`ALTER TABLE ... RENAME TO`) old → `_old`, new → original name.
  4. Keep `_old` with an expiration for rollback.
- Never `CREATE OR REPLACE TABLE` the live table — it drops time-travel history continuity, breaks streaming writers, and loses data written during the rewrite.

## S2 — Many tiny partitions
- Average partition <100 MiB with thousands of partitions: metadata overhead, slow queries, risk of hitting the 10,000 limit. Use MONTH/YEAR granularity and cluster on the date column.

## S3 — No require_partition_filter on big partitioned tables
- `ALTER TABLE \`p.ds.t\` SET OPTIONS(require_partition_filter = TRUE);`
- Breaks every query without a partition filter — list them first from JOBS (`referenced_tables` contains the table and bytes ≈ table size).

## S4 — Heavily queried, no clustering
- Up to 4 columns, ordered by how often they are filtered and their selectivity. Good candidates: tenant/account IDs, event names, status.
- `bq update --clustering_fields=a,b p:ds.t` changes the spec; existing data is not reclustered until rewritten (automatic reclustering applies as data is written/modified).
- Clustering columns must be top-level, non-repeated; FLOAT64 is not allowed.

## S5 — Temp/backup tables without expiration
- `ALTER TABLE ... SET OPTIONS(expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 30 DAY));` after the owner confirms. Scratch datasets: `default_table_expiration_days`.
- `partition_expiration_days` deletes old partitions; `expiration_timestamp` deletes the **whole table**. Never mix them up.

## S6 — Date-sharded tables
- `events_20260101` style. Migrate to a single date-partitioned table; query via wildcard meanwhile.
- GA4/Firebase BigQuery exports (`events_YYYYMMDD`, `events_intraday_*` in `analytics_*` datasets) are sharded by design — mention as info, don't flag.

## Useful facts
- Adding a REQUIRED column to an existing table is not allowed; add NULLABLE.
- `ALTER COLUMN ... SET DATA TYPE` supports widening (INT64→NUMERIC/BIGNUMERIC/FLOAT64, NUMERIC→BIGNUMERIC); `ALTER COLUMN ... DROP NOT NULL` exists.
- Time travel window 2–7 days (`max_time_travel_hours`), then 7 days fail-safe (recoverable only via support).
