# Performance checks

Plans live in `INFORMATION_SCHEMA.JOBS.job_stages` and the console's Execution details. BigQuery has **no EXPLAIN statement**. To inspect a sample job, give the user:
```sql
SELECT stage.name, stage.slot_ms, stage.records_read, stage.records_written,
       stage.shuffle_output_bytes, stage.shuffle_output_bytes_spilled
FROM `PROJECT`.`region-REGION`.INFORMATION_SCHEMA.JOBS_BY_PROJECT, UNNEST(job_stages) stage
WHERE job_id = 'SAMPLE_JOB_ID'
ORDER BY stage.slot_ms DESC;
```

## P1 — Scans most of a large table
`avg_scan_ratio` = average bytes processed by single-table queries ÷ table logical size.
- Partitioned table, still ~100% scanned → pruning fails. Causes:
  - Partition column wrapped in a function that blocks pruning, e.g. `DATE(ts) = ...` on a table partitioned by `TIMESTAMP_TRUNC(ts, DAY)` is fine, but `FORMAT_TIMESTAMP(...)`, `CAST(ts AS STRING)`, or arithmetic on the column is not.
  - Filter compares to a subquery/join result instead of a constant or a query parameter (dynamic pruning is limited).
  - No filter on the partition column at all.
  - `_TABLE_SUFFIX` filter missing on wildcard tables.
- Not partitioned → refer to schema S1.

## P6 — Costly or slow query patterns
Regex hints are only hints — read `sample_query` and confirm before reporting.
- `SELECT *` on wide tables → explicit columns or `SELECT * EXCEPT(...)`.
- `ORDER BY` without `LIMIT` on large results → single-worker sort; add LIMIT or drop the ORDER BY.
- `COUNT(DISTINCT x)` over billions of rows → `APPROX_COUNT_DISTINCT` if ~1% error is acceptable, or HLL sketches for rollups.
- Window functions without `PARTITION BY` → one worker processes everything.
- JOIN row explosion → join keys not unique on one side; dedupe or aggregate before joining. A join on `COALESCE(key, 'x')` matches all NULLs to each other — never suggest it.
- Filters on clustered columns placed after expensive transforms → move them early.
- Repeated JSON parsing of a STRING column → materialize the fields or use the JSON type.
- `REGEXP_*` over large text → `STARTS_WITH`, `LIKE`, or search indexes (`SEARCH()`).
- Do not claim that moving a WHERE into a CTE helps — the optimizer pushes filters down already. Do not suggest reordering LEFT JOINs (changes results).
Show the rewritten SQL with real names, and how to compare `total_bytes_billed`/`total_slot_ms` before vs after.

## P7 — Heavy SELECT repeated many times
- Materialized view (incremental, smart tuning can rewrite queries automatically) if the query fits MV limitations; otherwise a scheduled summary table written by MERGE or partition overwrite.
- BI Engine reservation for dashboard traffic.

## P5 — Bursty load
- Matters on reservations (queueing) more than on-demand. Suggest staggering scheduled jobs and checking `INFORMATION_SCHEMA.JOBS_TIMELINE` for those hours.
