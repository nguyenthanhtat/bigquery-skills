# Reliability checks

## R1 — High failure rate
Group by reason (R2) — a single broken scheduled job or app can dominate.

## R2 — Recurring error signatures
| reason | Usual cause | Direction |
|---|---|---|
| `quotaExceeded`, `rateLimitExceeded` (HTTP 403) | table update ops/day, concurrent DML, API rate | batch writes, backoff, spread schedules |
| `resourcesExceeded` | ORDER BY without LIMIT, OVER() without PARTITION BY, huge ARRAY_AGG/STRING_AGG, skewed join keys | rewrite the query shape |
| `billingTierLimitExceeded` | on-demand CPU-heavy query vs bytes scanned | simplify, or run on a reservation |
| `accessDenied` | removed member, rotated SA key, Drive scope missing for Sheets external tables | check run-as identity |
| `notFound` | table renamed/deleted upstream, or job location ≠ dataset location | fix reference / `--location` |
| `invalidQuery` | schema change upstream | fix SQL, add contract checks |
| "Could not serialize access" | concurrent DML on one table | serialize writers |
| `backendError`, `internalError` | transient | retry with exponential backoff; escalate if persistent |
Show the user how to read one failure: `bq show -j --format=prettyjson SAMPLE_JOB_ID`.

## R3 — Scheduled query failing now
- The latest run failed → downstream data is stale. Fix the cause, or disable the schedule (console: Scheduled queries → Disable, or Data Transfer API `disabled: true`) after telling the owner.
- Recommend notifications: Pub/Sub topic or email set in the console/API (the bq CLI cannot set notifications).
- Reruns/backfills: `bq mk --transfer_run --start_time=... --end_time=... projects/P/locations/L/transferConfigs/ID`. Ensure the query is idempotent first (MERGE or writes to `{run_date}` partition with WRITE_TRUNCATE), otherwise reruns duplicate rows.

## R4 — Schedules owned by a person
- `bq update --transfer_config --update_credentials --service_account_name=sa@p.iam.gserviceaccount.com projects/P/locations/L/transferConfigs/ID`
- The SA needs `bigquery.jobUser` + write access to the destination dataset.
