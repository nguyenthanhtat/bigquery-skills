# Cost checks

Prices: `analysis/summary.json → pricing` (US list by default). On-demand bills `total_bytes_billed` (10 MiB minimum per table referenced, 0 on cache hit) per **TiB** (1024⁴). The first 1 TiB/month is free per billing account; ignore it for anything but tiny projects.

## C2 — Spend concentrated in one query pattern
A normalized query hash ≥20% of bytes billed. Usually a dashboard or scheduled job.
- Root causes: full scan of an unpartitioned/unclustered table; `SELECT *`; re-aggregating raw events every run; cache defeated by `CURRENT_TIMESTAMP()`/`RAND()`.
- Fixes, least risky first: add/repair the partition filter → select needed columns → precompute into an incremental summary table or a materialized view → BI Engine for dashboards.
- Cross-check the same `query_hash` in performance findings; describe the fix once and reference it.

## C3 — One principal dominates spend
- Often a service account behind a BI tool or pipeline. Not a problem by itself; flag when unexpected or uncapped.
- Fix: custom quota `QueryUsagePerUserPerDay`; job labels for attribution; a reservation assignment for that workload if on editions.

## C4 — Single jobs over 1 TiB / no guardrails
- Fixes: `--maximum_bytes_billed` (bq) / `maximumBytesBilled` (API) on app and scheduled queries; project custom quota `QueryUsagePerDay`; `require_partition_filter` on big tables (schema S3).
- Budgets only **alert**; they do not cap spend. Say so if the user relies on them.

## C5 — Storage billing model
Logical: active $0.02/GiB, long-term $0.01/GiB, time travel & fail-safe free. Physical: active $0.04, long-term $0.02, time travel and fail-safe **billed**. Physical wins when compression ratio is high (often >2×).
- Fix: `ALTER SCHEMA \`p.ds\` SET OPTIONS(storage_billing_model = 'PHYSICAL');` Takes ~24 h; cannot change again for 14 days. Requires approval.
- Under PHYSICAL, also consider `max_time_travel_hours = 48` (min 48, default 168) on datasets with heavy churn.
- Long-term rate applies per table/partition after 90 consecutive days without modification — not based on creation time.

## C6 — Large tables not read or written in the window
- Evidence is weak by design: `JOBS_BY_PROJECT` only sees jobs **run in this project**. Reads from other projects, Looker/Data Studio billed elsewhere, and copy/extract by other tools are invisible.
- Recommendation is always: confirm with owner → set `expiration_timestamp` (reversible until it fires) or snapshot/export to GCS → delete only later and only by the owner. Never write a DROP in the fix.

## C8 — On-demand vs editions
- Estimate = consumed slot-hours × edition rate. Real autoscaling bills at least 1 minute in 50-slot steps and only up to the max you set, so treat it as an upper-bound comparison, confidence low.
- Recommend a pilot (one reservation, one workload assignment, max slots capped) and comparing a week of `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`, not a switch.

## Always mention when relevant
- Dry run before running anything heavy: `bq query --dry_run --use_legacy_sql=false '...'`.
- `LIMIT` does not reduce bytes billed (except on clustered tables in some cases).
