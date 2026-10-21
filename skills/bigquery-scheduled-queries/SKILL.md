---
name: bigquery-scheduled-queries
description: "Design, create, fix and operate recurring BigQuery jobs: scheduled queries (Data Transfer Service), idempotent daily/hourly aggregations and incremental loads with MERGE or partition overwrite, @run_date/@run_time parameters, backfills and reruns, service-account ownership, failure notifications, plus when to use Dataform or Airflow instead. Use when the user wants to schedule, automate, backfill, rerun, or debug a recurring BigQuery query or SQL pipeline."
---

# BigQuery scheduled queries

Answer in the user's language. Use their real project, dataset, table and column names.

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

When the problem is project-wide → suggest the bq-audit skill.

## Before creating a schedule, establish
1. **What it writes**: a new table each run, one partition per run, or rows merged into a table. This decides idempotency (below).
2. **Location**: the scheduled query runs in the destination dataset's location; source and destination must match.
3. **Identity**: who it runs as. Prefer a service account (`--service_account_name`); a schedule owned by a person breaks when they leave or lose access. The account needs `roles/bigquery.jobUser` on the project and write access (e.g. `roles/bigquery.dataEditor`) on the destination dataset.
4. **Frequency and latency of source data**: late-arriving data needs a lookback window, not just "yesterday".
5. **Prerequisites**: BigQuery Data Transfer API enabled; the creator has `bigquery.transfers.update` and dataset access.

## Idempotency is the rule
Scheduled queries are rerun by people (after a failure) and by backfills. Every run for a given `@run_date` must produce the same result. Pick one:

**A. MERGE (recommended for aggregates and upserts)** — the query is DML, so set no destination table:
```sql
DECLARE d DATE DEFAULT DATE_SUB(@run_date, INTERVAL 1 DAY);

MERGE `proj.app.daily_stats` T
USING (
  SELECT d AS day, event_name, COUNT(*) AS events, COUNT(DISTINCT user_id) AS users
  FROM `proj.app.events`
  WHERE event_date = d                      -- partition filter on the source
  GROUP BY event_name
) S
ON T.day = S.day AND T.event_name = S.event_name
WHEN MATCHED THEN UPDATE SET events = S.events, users = S.users
WHEN NOT MATCHED THEN INSERT (day, event_name, events, users) VALUES (S.day, S.event_name, S.events, S.users)
WHEN NOT MATCHED BY SOURCE AND T.day = d THEN DELETE;   -- rows that disappeared from the source for that day
```

**B. Overwrite one partition (fast, simple, for partitioned destinations)** — a SELECT with a destination template and `WRITE_TRUNCATE`; only the targeted partition is replaced:
```bash
bq mk --transfer_config \
  --project_id=proj --location=US \
  --data_source=scheduled_query \
  --display_name='daily_stats' \
  --target_dataset=app \
  --schedule='every 24 hours' \
  --service_account_name=pipelines@proj.iam.gserviceaccount.com \
  --params='{
    "query": "SELECT @run_date AS day, event_name, COUNT(*) AS events FROM `proj.app.events` WHERE event_date = @run_date GROUP BY event_name",
    "destination_table_name_template": "daily_stats${run_date}",
    "write_disposition": "WRITE_TRUNCATE"
  }'
```
`{run_date}` renders as YYYYMMDD; `{run_time|"%Y%m%d"}` formats the run timestamp. For a different day than the run date, keep the query and the partition decorator aligned (both on the same date) — check the template offset syntax in the docs before relying on it, or use pattern A.

**C. DELETE + INSERT inside a transaction** (when MERGE is awkward):
```sql
BEGIN TRANSACTION;
DELETE FROM `proj.app.daily_stats` WHERE day = DATE_SUB(@run_date, INTERVAL 1 DAY);
INSERT INTO `proj.app.daily_stats` (day, event_name, events)
SELECT DATE_SUB(@run_date, INTERVAL 1 DAY), event_name, COUNT(*)
FROM `proj.app.events` WHERE event_date = DATE_SUB(@run_date, INTERVAL 1 DAY)
GROUP BY event_name;
COMMIT TRANSACTION;
```

Never use plain `WRITE_APPEND` / `INSERT` without one of these — every rerun duplicates rows. Never "INSERT then DELETE from staging" outside a transaction: rows arriving in between are deleted without being copied.

### Parameters, not wall-clock functions
- `@run_time` (TIMESTAMP) and `@run_date` (DATE) are the *scheduled* time of the run, so reruns and backfills compute the same window. `CURRENT_DATE()` / `CURRENT_TIMESTAMP()` do not.
- Incremental loads: derive the window from `@run_time` (e.g. `ts >= TIMESTAMP_SUB(@run_time, INTERVAL 1 HOUR) AND ts < @run_time`) plus a lookback for late data, and make the write idempotent (MERGE on a unique key).
- Multi-statement scripts (`DECLARE`, transactions, several DML statements) are allowed; scripts and DML write through their own statements, so leave the destination table empty.

## Schedules
- Syntax: `every 24 hours`, `every 1 hours`, `every day 02:00`, `every mon,tue,wed,thu,fri 08:00`, `1st,15th of month 06:00`, `every 15 minutes`. Minimum interval is 5 minutes.
- Times are UTC. Convert from the user's timezone and say so.
- Stagger jobs that touch the same table: concurrent DML on one table can fail with "Could not serialize access … due to concurrent update".

## Operate
```bash
bq ls --transfer_config --transfer_location=US --project_id=proj
bq show --format=prettyjson --transfer_config projects/PROJECT_NUMBER/locations/us/transferConfigs/CONFIG_ID
bq ls --transfer_run --run_attempt=LATEST projects/PROJECT_NUMBER/locations/us/transferConfigs/CONFIG_ID

# Change query or schedule
bq update --transfer_config --params='{"query":"..."}' --schedule='every day 03:00' projects/.../transferConfigs/CONFIG_ID
# Move ownership to a service account
bq update --transfer_config --update_credentials \
  --service_account_name=pipelines@proj.iam.gserviceaccount.com projects/.../transferConfigs/CONFIG_ID
```
- **Reruns and backfills**: there are no automatic retries. Rerun or backfill a range (one run per schedule slot):
  `bq mk --transfer_run --start_time='2026-10-01T00:00:00Z' --end_time='2026-10-08T00:00:00Z' projects/.../transferConfigs/CONFIG_ID`
  Only safe when the query is idempotent.
- **Notifications**: the bq CLI cannot set them. Use the console (Edit → Notification options: email on failure, or a Pub/Sub topic) or the Data Transfer API fields `emailPreferences.enableFailureEmail` / `notificationPubsubTopic`.
- **Pause**: disable in the console or set `disabled: true` via the API; don't delete a config you might need — export its params first (`bq show --format=prettyjson`).
- **History and cost** of runs: scheduled jobs have IDs starting `scheduled_query`:
```sql
SELECT DATE(creation_time) AS day, COUNT(*) AS runs, COUNTIF(error_result IS NOT NULL) AS failed,
       SUM(total_bytes_billed) / POW(1024, 4) AS tib_billed,
       ANY_VALUE(error_result.message) AS sample_error
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
  AND job_id LIKE 'scheduled_query%'
GROUP BY day ORDER BY day DESC;
```

## Debugging a failing schedule
1. `bq ls --transfer_run --run_attempt=LATEST <config>` and open the failing run's job: `bq show -j --format=prettyjson JOB_ID` (with `--location`).
2. Common causes: run-as identity lost access (`accessDenied`), source table renamed/region mismatch (`notFound`), upstream schema change (`invalidQuery`), concurrent DML on the destination, quota/rate limits on frequent writes (403 `rateLimitExceeded`).
3. Reproduce by running the query manually with `@run_date`/`@run_time` set via `--parameter='run_date:DATE:2026-10-20'`, dry-run first.
4. After fixing, backfill the missed dates (idempotent queries only).

## Cost
- Each run is billed like any query: filter on the source's partition column using `@run_date`, select only needed columns, and test the query manually with `--maximum_bytes_billed` before scheduling.
- A 5-minute schedule runs ~8,600 times a month; even small queries add up (each referenced table is billed at least 10 MiB on-demand). Prefer longer intervals or incremental windows.

## When a scheduled query is the wrong tool
- **Dependencies between steps, tests, versioned SQL** → Dataform (SQL workflows with `ref()` dependencies, assertions, incremental tables, Git integration).
- **Cross-system orchestration** (wait for a file, call an API, then query) → Cloud Composer / Airflow. Use `BigQueryInsertJobOperator` with standard SQL:
```python
from airflow import DAG
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
import pendulum

with DAG("daily_stats", schedule="0 2 * * *", start_date=pendulum.datetime(2026, 1, 1, tz="UTC"), catchup=False) as dag:
    BigQueryInsertJobOperator(
        task_id="merge_daily_stats",
        configuration={"query": {"query": "{% include 'sql/daily_stats_merge.sql' %}", "useLegacySql": False}},
        location="US",
    )
```
  (`schedule`, not the deprecated `schedule_interval`; set `useLegacySql: False` — the API defaults to legacy SQL.)
- **Near-real-time** (seconds) → continuous queries or streaming pipelines, not schedules.
