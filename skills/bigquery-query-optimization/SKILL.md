---
name: bigquery-query-optimization
description: "Make a BigQuery query faster or cheaper, or fix wrong row counts: slow or expensive queries, too many bytes scanned or billed, partition pruning not working, JOIN row explosion / duplicate rows after a join, heavy DISTINCT, window functions or aggregations, slot usage. Use when the user shares a query (or job) that is slow, costs too much, scans too much, or returns more rows than expected. Not for jobs that fail with an error message (use bigquery-troubleshooting)."
---

# BigQuery query optimization

Answer in the user's language. Work on the user's actual query and table names.

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

When the problem is project-wide (many queries, a bill spike, "everything is slow") → suggest the **bq-audit** skill instead of tuning one query.

## 1. Gather facts first
Ask for (or find) what you don't have:
1. The SQL text, or a job ID.
2. Table layout: `bq show --format=prettyjson project:dataset.table` → `timePartitioning` / `rangePartitioning`, `clustering`, `numBytes`, `numRows`, `requirePartitionFilter`.
3. What the run cost: bytes billed, slot-ms, duration — from the job:
   ```bash
   bq show -j --format=prettyjson --location=LOCATION JOB_ID
   ```
   or
   ```sql
   SELECT job_id, total_bytes_processed, total_bytes_billed, total_slot_ms,
          TIMESTAMP_DIFF(end_time, start_time, SECOND) AS seconds, cache_hit
   FROM `PROJECT`.`region-LOCATION`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
   WHERE job_id = 'JOB_ID';
   ```
4. Where the time goes. BigQuery has **no EXPLAIN statement**. Use the console's *Execution details / Execution graph*, or:
   ```sql
   SELECT s.name, s.slot_ms, s.records_read, s.records_written,
          s.shuffle_output_bytes, s.shuffle_output_bytes_spilled,
          s.wait_ms_avg, s.compute_ms_max, s.compute_ms_avg
   FROM `PROJECT`.`region-LOCATION`.INFORMATION_SCHEMA.JOBS_BY_PROJECT,
        UNNEST(job_stages) AS s
   WHERE job_id = 'JOB_ID'
   ORDER BY s.slot_ms DESC;
   ```
   Read it as: one stage with most slot-ms = the bottleneck; `compute_ms_max` ≫ `compute_ms_avg` = data skew; `shuffle_output_bytes_spilled` > 0 = shuffle too big; `records_written` ≫ `records_read` in a join stage = row explosion.

## 2. Decide what kind of problem it is
| Symptom | Go to |
|---|---|
| Bytes billed ≈ table size although the query filters by date | §3 pruning |
| Reads many columns / `SELECT *` | §4 columns |
| More rows than expected after a JOIN | §5 joins |
| One stage dominates, skew, spill | §6 heavy operators |
| Same query runs many times a day | §7 reuse |
| Fine once, but costs add up over thousands of tiny queries | §8 small queries |

Cost model to keep in mind: on-demand bills `total_bytes_billed` per **TiB** (1024⁴ bytes), minimum 10 MiB per table referenced, 0 on cache hit. Bytes depend on **columns read × partitions/blocks scanned**, not on rows returned. `LIMIT` does not reduce bytes billed (except some clustered-table cases).

## 3. Partition pruning and clustering
Pruning happens when the filter on the partitioning column can be evaluated before reading data.
- Works: `WHERE event_date BETWEEN '2026-01-01' AND '2026-01-31'` on a DATE-partitioned table; `WHERE DATE(ts) = '2026-01-15'` or `WHERE ts >= TIMESTAMP('2026-01-15')` on a table partitioned by `DATE(ts)` / `TIMESTAMP_TRUNC(ts, DAY)`; `_PARTITIONTIME` / `_PARTITIONDATE` filters on ingestion-time tables; query parameters (`@start_date`).
- Breaks or weakens: wrapping the column in non-pruning expressions (`FORMAT_TIMESTAMP('%Y-%m', ts) = '2026-01'`, `CAST(ts AS STRING) LIKE '2026-01%'`, arithmetic on the column); filtering on a different column than the partition column; comparing to a subquery result (`WHERE d = (SELECT MAX(d) FROM ...)` — dynamic pruning is limited; compute the value first with a script variable or pass a parameter); filter missing on one side of a join.
- Wildcard tables: always filter `_TABLE_SUFFIX` with constants.
- Verify: dry-run the rewritten query and compare estimated bytes with the original.
- Clustering prunes blocks when filtering on clustered columns in order (first column most important). Filters must be on the raw column, not a function of it.
- Table-level fixes (partition/cluster a table, `require_partition_filter`) → bigquery-schema-design. Never rewrite the live table in place.

Where a CTE puts its WHERE does not matter — the optimizer pushes filters down. Don't present "move the filter into a CTE" as an optimization.

## 4. Read fewer columns
- Replace `SELECT *` with needed columns, or `SELECT * EXCEPT(big_col1, big_col2)`.
- Nested data: select `s.field` rather than the whole STRUCT/ARRAY.
- For exploration, use table preview (free) or `TABLESAMPLE SYSTEM (1 PERCENT)` instead of `SELECT * ... LIMIT`.

## 5. JOIN row explosion / duplicate rows
Cause: the join key is not unique on at least one side, so every match multiplies rows.
1. Prove it:
   ```sql
   SELECT customer_id, COUNT(*) AS n
   FROM `p.ds.customers`
   GROUP BY customer_id
   HAVING n > 1
   ORDER BY n DESC
   LIMIT 20;
   ```
2. Fix at the source of duplication, before the join:
   ```sql
   WITH customers_latest AS (
     SELECT *
     FROM `p.ds.customers`
     WHERE TRUE
     QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC) = 1
   )
   SELECT o.*, c.name
   FROM `p.ds.orders` AS o
   LEFT JOIN customers_latest AS c USING (customer_id);
   ```
   or aggregate the many-side first (`GROUP BY key`) when you need totals.
3. Check: `COUNT(*)` of the result equals `COUNT(*)` of the driving table.
- Don't use `SELECT DISTINCT` on the final result as the fix — it hides the cause and is expensive.
- Never join on `COALESCE(key, 'x')` or `IFNULL(...)`: it matches all NULL keys to each other and creates the explosion. Keep NULL keys unmatched or handle them explicitly.
- Don't swap `a LEFT JOIN b` to `b LEFT JOIN a` for speed — it changes the result. BigQuery chooses join order/broadcast itself; put the largest table first in INNER joins only if the plan shows a bad choice.
- Many-to-many joins inside a time window: join on key **and** a time range, or pre-aggregate per key/time bucket.

## 6. Heavy operators
- `ORDER BY` without `LIMIT` on a large result sorts on one worker → add `LIMIT`, or drop the ORDER BY and sort downstream.
- Window functions: always `PARTITION BY` when possible; `OVER (ORDER BY ...)` with no partition runs on one worker. `LAST_VALUE`/`NTH_VALUE` need an explicit frame:
  ```sql
  LAST_VALUE(status) OVER (PARTITION BY order_id ORDER BY ts
                           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
  ```
  For "latest row per key", `QUALIFY ROW_NUMBER() ... = 1` or `ARRAY_AGG(t ORDER BY ts DESC LIMIT 1)[OFFSET(0)]` is cheaper. A named `WINDOW` clause is shorthand only, not faster.
- `COUNT(DISTINCT x)` over billions of rows: `APPROX_COUNT_DISTINCT(x)` (~1% error) if acceptable; for rollups use HLL (`HLL_COUNT.INIT/MERGE`).
- Skew (one key holds most rows): filter or handle the hot key separately, or add a salt and aggregate twice.
- Large `ARRAY_AGG`/`STRING_AGG` without `LIMIT`: cap them or aggregate in stages.
- Regex on large text: prefer `STARTS_WITH`, `LIKE`, or a search index with `SEARCH()`.
- Repeated JSON extraction from a STRING column: parse once in a CTE, or store as the JSON type / extracted columns.
- `CROSS JOIN` / joins with inequality-only conditions: confirm intent; they grow quadratically.
- User-defined JavaScript functions are slow; prefer SQL UDFs or built-ins.

## 7. Queries that run many times
- Cache only works for identical, deterministic queries on unchanged tables. `CURRENT_TIMESTAMP()`, `RAND()`, `SESSION_USER()` disable it — pass the date as a parameter instead.
- Dashboards re-aggregating raw events: a materialized view (incremental refresh; smart tuning can rewrite matching queries) if the query fits MV limits, otherwise a scheduled summary table (see bigquery-scheduled-queries), or BI Engine for interactive dashboards.

## 8. Many tiny queries
Each query is billed at least 10 MiB per referenced table. Thousands of small lookups/polls cost far more than the data they read. Batch them into fewer queries, cache results in the application, move point lookups to a serving store, or run that workload on a small reservation.

## 9. Report the result
Show: original vs rewritten SQL, dry-run bytes before/after, and what to compare after running (`total_bytes_billed`, `total_slot_ms`, duration from INFORMATION_SCHEMA.JOBS). Mention trade-offs (approximate results, extra storage for summary tables).
