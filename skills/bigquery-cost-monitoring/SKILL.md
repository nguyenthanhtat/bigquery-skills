---
name: bigquery-cost-monitoring
description: "Measure and control Google BigQuery spend: query cost per user/query/label from INFORMATION_SCHEMA.JOBS, editions slot cost, storage cost and logical vs physical billing, budgets and guardrails (maximum_bytes_billed, custom quotas, require_partition_filter). Use when the user asks how much BigQuery costs, who or what is spending, why a query or table is expensive, or how to cap spend. For a whole-project cost investigation or a bill spike, use bq-audit."
---

# BigQuery cost monitoring

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

**Bill spiked or "audit our costs"?** Recommend the `bq-audit` skill: a read-only audit of the whole project that shows its own cost with a free dry-run plan first, then reports spend by user, query pattern, table and storage with fixes.

## Pricing facts (US list; other regions differ — say so)
| Item | Price |
|---|---|
| On-demand queries | $6.25 per **TiB** of `total_bytes_billed` (1 TiB = 1024⁴ bytes). First 1 TiB/month free per billing account. Minimum 10 MiB per table referenced; cache hits are free. |
| Editions (capacity) | Standard $0.04, Enterprise $0.06, Enterprise Plus $0.10 per slot-hour (pay-as-you-go; commitments cheaper). Bytes don't matter, slot-hours do. |
| Logical storage | active $0.02/GiB/month, long-term $0.01. Time travel and fail-safe not billed. |
| Physical storage | active $0.04/GiB/month, long-term $0.02. Time travel and fail-safe **billed**. |
| Long-term | Table or partition not modified for 90 consecutive days (not based on creation time). |
| Batch load and export jobs | Free on the shared slot pool (you pay GCS storage/egress). |

The billing export to BigQuery (Cloud Billing → export) is the source of truth for what was actually charged. INFORMATION_SCHEMA gives estimates for attribution.

## Query cost by user (on-demand)
```sql
SELECT
  user_email,
  COUNT(*) AS jobs,
  SUM(total_bytes_billed) / POW(1024, 4) AS tib_billed,
  SUM(total_bytes_billed) / POW(1024, 4) * 6.25 AS est_usd
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT   -- match the data's region
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND job_type = 'QUERY'
  AND statement_type IS DISTINCT FROM 'SCRIPT'           -- parent script jobs repeat their children's bytes
GROUP BY user_email
ORDER BY tib_billed DESC;
```
- Use `total_bytes_billed`, never `total_bytes_processed`, for cost.
- `JOBS_BY_PROJECT` needs `bigquery.jobs.listAll` (e.g. `roles/bigquery.resourceViewer`). `JOBS_BY_USER` shows only your own jobs. `JOBS_BY_ORGANIZATION` covers all projects in the org (needs org-level permission).
- Querying INFORMATION_SCHEMA is itself billed — dry-run it on large projects.

## Most expensive query shapes
```sql
SELECT
  query_info.query_hashes.normalized_literals AS query_hash,
  COUNT(*) AS runs,
  COUNTIF(cache_hit) AS cache_hits,
  SUM(total_bytes_billed) / POW(1024, 4) * 6.25 AS est_usd,
  ANY_VALUE(user_email) AS sample_user,
  ANY_VALUE(job_id) AS sample_job_id,
  ANY_VALUE(LEFT(query, 500)) AS sample_query
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND job_type = 'QUERY' AND statement_type IS DISTINCT FROM 'SCRIPT'
GROUP BY query_hash
ORDER BY est_usd DESC
LIMIT 20;
```
Group by `labels` (e.g. `(SELECT value FROM UNNEST(labels) WHERE key = 'team')`) for attribution. Ask teams to label jobs (`--label=team:growth`) rather than parsing query text.

## Editions / reservations cost
Bytes are irrelevant under editions. Estimate from slot time:
```sql
SELECT
  reservation_id,
  SUM(total_slot_ms) / (1000 * 60 * 60) AS slot_hours
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND statement_type IS DISTINCT FROM 'SCRIPT'
GROUP BY reservation_id;
```
Autoscaling bills what is scaled (50-slot steps, 1-minute minimum), not what jobs consumed, so real cost is higher than consumed slot-hours × rate. For capacity actually billed, use `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` in the admin project or the billing export.

## Storage cost and billing model
```sql
SELECT
  table_schema AS dataset,
  SUM(active_logical_bytes) / POW(1024, 3) AS active_logical_gib,
  SUM(long_term_logical_bytes) / POW(1024, 3) AS long_term_logical_gib,
  SUM(active_physical_bytes) / POW(1024, 3) AS active_physical_gib,       -- includes time travel
  SUM(long_term_physical_bytes) / POW(1024, 3) AS long_term_physical_gib,
  SUM(time_travel_physical_bytes) / POW(1024, 3) AS time_travel_gib,
  SUM(fail_safe_physical_bytes) / POW(1024, 3) AS fail_safe_gib
FROM `region-us`.INFORMATION_SCHEMA.TABLE_STORAGE
WHERE NOT deleted
GROUP BY dataset
ORDER BY active_logical_gib + long_term_logical_gib DESC;
```
Compare per dataset:
- Logical cost = active_logical × 0.02 + long_term_logical × 0.01
- Physical cost = (active_physical + fail_safe) × 0.04 + long_term_physical × 0.02

Physical usually wins when compression is high (>~2×) and churn is low. Switch (with the user's approval):
```sql
ALTER SCHEMA `project.dataset` SET OPTIONS (storage_billing_model = 'PHYSICAL');
```
Takes effect within ~24 h and can't be changed again for 14 days. Under physical billing, consider `max_time_travel_hours = 48` (min 48, default 168) on high-churn datasets.

## Guardrails that actually limit spend
| Control | What it does |
|---|---|
| `--maximum_bytes_billed` / `maximumBytesBilled` | Job fails before running if it would bill more. Set it in apps, scheduled queries, BI connections. |
| Custom quotas | `QueryUsagePerDay` (project) and `QueryUsagePerUserPerDay` in IAM & Admin → Quotas. Hard daily cap for on-demand. |
| `require_partition_filter = TRUE` | Rejects queries on big partitioned tables without a partition filter. Check JOBS for existing unfiltered queries first — they will start failing. |
| Reservation max slots | Caps editions autoscaling. |
| Budgets | **Alert only** — they never stop spend. Thresholds are fractions: `--threshold-rule=percent=0.5` means 50%. Filter to BigQuery with `--filter-services`. Automating a shutoff needs a Pub/Sub-triggered function. |

## Cutting cost safely
- Partition pruning and clustering (see `bigquery-schema-design`), select only needed columns, avoid re-aggregating raw data on every dashboard refresh (summary tables or materialized views).
- `LIMIT` does not reduce bytes billed (except some clustered-table cases).
- Many tiny queries pay the 10 MiB-per-table minimum each: batch them, cache in the app, or move that workload to a small reservation.
- Retention: `partition_expiration_days` drops old **partitions**. `expiration_timestamp` deletes the **whole table** when it fires — never use it to trim old rows.
- "Unused" tables: `JOBS_BY_PROJECT` doesn't see reads from other projects, BI tools billed elsewhere, or external jobs. Treat candidates as review-only: confirm with owners, set an expiration or export to GCS first. Never DROP based on this query alone.
```sql
-- Large tables not modified in 90+ days (review list, not a delete list)
SELECT table_schema, table_name,
       total_logical_bytes / POW(1024, 3) AS logical_gib,
       storage_last_modified_time
FROM `region-us`.INFORMATION_SCHEMA.TABLE_STORAGE
WHERE NOT deleted
  AND storage_last_modified_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
ORDER BY total_logical_bytes DESC
LIMIT 50;
```
