---
name: bigquery-troubleshooting
description: "Diagnose and fix a BigQuery job that failed with an error message: Access Denied / permission errors, Not found (including dataset location mismatch), quotaExceeded / rateLimitExceeded, Resources exceeded, billing tier errors, concurrent DML 'Could not serialize access', streaming buffer DML errors, load/export job errors, scheduled query failures; also recovering a dropped table or deleted rows with time travel. Use when the user pastes a BigQuery error or a job ID that failed. Not for queries that succeed but are slow or expensive (use bigquery-query-optimization)."
---

# BigQuery troubleshooting

Answer in the user's language. Work from the actual error text and job.

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

When failures are project-wide (many jobs failing, recurring errors across pipelines) → suggest the **bq-audit** skill for a full reliability review.

## 1. Get the full error
The message the user sees is often truncated. Get the job:
```bash
bq show -j --format=prettyjson --location=LOCATION JOB_ID   # status.errorResult, status.errors[]
```
Recent failures in the project:
```sql
SELECT creation_time, job_id, user_email, job_type, statement_type,
       error_result.reason, error_result.message
FROM `PROJECT`.`region-LOCATION`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND error_result IS NOT NULL
ORDER BY creation_time DESC
LIMIT 50;
```
(Needs `bigquery.jobs.listAll` to see other users' jobs. A failed script also records the error on its parent job — count once.)

Then match `error_result.reason` and the message below.

## 2. Error reference
API errors map to HTTP codes: invalid/invalidQuery 400, accessDenied/quotaExceeded/rateLimitExceeded/billingTierLimitExceeded 403, notFound 404, duplicate 409, backendError 500/503.

### accessDenied (403)
- "User does not have permission to query table / bigquery.tables.getData": grant `roles/bigquery.dataViewer` on the **dataset** (or table), not project-wide.
- "bigquery.jobs.create permission": the caller needs `roles/bigquery.jobUser` on the project that **runs** the job (can differ from the data project — check `--project_id`).
- "Permission denied while getting Drive credentials": the table is a Google Sheets/Drive external table. Use credentials with the Drive scope (`gcloud auth login --enable-gdrive-access`, or the scope on the service account client) and share the sheet with that identity. Dataset roles alone don't fix it.
- Column-level security / policy tag denial: the user needs Fine-Grained Reader on the tag, or read through an authorized view.
- Row-level security returns **zero rows, not an error**: once any row access policy exists on a table, users not covered by a policy see nothing.
- Scheduled query failing with access denied after someone left: the schedule runs as a person. Move it to a service account (`bq update --transfer_config --update_credentials --service_account_name=SA RESOURCE_NAME`).

### notFound (404)
- "Not found: Dataset P:ds was not found in location X": the job runs in a different location than the dataset. Pass `--location` matching the dataset (`bq show --format=prettyjson P:ds` → `location`). All tables in one query must be in the same location.
- Table not found: typo, wrong project qualifier (use backticks `` `p.ds.t` ``), the table was renamed/dropped upstream, or it is created lazily and doesn't exist yet for some datasets.

### quotaExceeded / rateLimitExceeded (403)
Read the message — it names the limit. Common ones:
- "too many table update operations for this table": frequent load/DML/copy/schema updates on one table. Batch writes into fewer, larger jobs; use the Storage Write API for streaming; spread writes over time; retry with exponential backoff.
- "Too many DML statements outstanding against table": too many queued mutating DML on one table. Serialize writers or merge statements.
- Concurrent/interactive query limits: queries now queue instead of failing; errors here mean the queue limit was hit — spread schedules.
- Project/user custom quota (QueryUsagePerDay / PerUserPerDay): an admin-set cap was reached; wait for reset or raise it deliberately.
Don't treat "request a quota increase" as the default fix; most of these are design issues.

### resourcesExceeded
"Resources exceeded during query execution" usually means one worker got too much:
- `ORDER BY` on a huge result without `LIMIT`.
- Window function without `PARTITION BY` (or a heavily skewed partition key).
- Huge `ARRAY_AGG`/`STRING_AGG` per group.
- Skewed JOIN/GROUP BY key (one value holds most rows).
- Very complex query (thousands of subqueries/UNIONs).
Fix the shape (see bigquery-query-optimization). Adding `LIMIT` at the end does not reduce what is scanned.

### billingTierLimitExceeded
On-demand query uses too much compute relative to bytes read (heavy JS UDFs, complex cross joins, regex on small data). Simplify the computation, or run it on a reservation (editions).

### invalidQuery / invalid (400)
- Syntax errors: check legacy vs GoogleSQL (`--use_legacy_sql=false`), backtick-quoted table names, reserved words.
- "Unrecognized name": a column was renamed/removed upstream, or an alias is used where it's not in scope (aliases can't be referenced in the same SELECT's WHERE).
- "Could not serialize access to table ... due to concurrent update": two DML statements changed the same table/partition concurrently. BigQuery retries some conflicts automatically; persistent ones need writers serialized or schedules offset, and the losing job retried.
- "UPDATE or DELETE statement over table ... would affect rows in the streaming buffer": rows inserted with the legacy streaming API (insertAll) can't be modified for a while (typically up to ~90 minutes). Filter DML to rows older than that, retry later, or switch ingestion to the Storage Write API / load jobs.

### Load and export jobs
- CSV errors: inspect `status.errors[]` for row/column; fix delimiter, quoting (`--allow_quoted_newlines`), header (`--skip_leading_rows=1`), encoding (default UTF-8; `--encoding=ISO-8859-1` if needed). Use `--max_bad_records` only as a diagnostic, and check `status.errors` afterwards — otherwise bad rows are dropped silently.
- Schema mismatch on append: add NULLABLE columns via `--schema_update_option=ALLOW_FIELD_ADDITION`; type changes need a new table.
- Location: the GCS bucket and dataset must be compatible locations.
- Export over 1 GB to a single file fails: use a wildcard URI (`gs://bucket/path/part-*.parquet`).

### backendError / internalError (500/503)
Transient. Retry with exponential backoff. Investigate only if it persists for the same job shape — then open a support case with the job ID.

## 3. Recovering data (time travel)
Time travel keeps changed/deleted data for the dataset's window (default 7 days, configurable 2–7 via `max_time_travel_hours`); after that, 7 days of fail-safe recoverable only through Google Cloud support.

**Dropped table** — `FOR SYSTEM_TIME AS OF` cannot read a deleted table. Copy a snapshot decorator to a **new** table:
```bash
# relative: one hour ago (milliseconds, negative offset)
bq cp --location=LOCATION 'p:ds.orders@-3600000' p:ds.orders_restored
# or absolute epoch milliseconds before the drop
bq cp --location=LOCATION 'p:ds.orders@1767225600000' p:ds.orders_restored
```
If a new table with the same name was created after the drop, restoring under the original name fails — restore to another name. Verify row counts, then rename if the user wants (`ALTER TABLE ... RENAME TO`).

**Dropped dataset**: `UNDROP SCHEMA \`p.ds\`;` within the time-travel window.

**Bad UPDATE/DELETE on an existing table** — read the old state into a new table, check it, then repair:
```sql
CREATE TABLE `p.ds.orders_before_fix` AS
SELECT * FROM `p.ds.orders`
  FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR);
```
Compare counts/keys with the current table, then fix with a targeted `MERGE` on the primary key after the user approves. Don't use `INSERT ... WHERE id NOT IN (...)` — it returns nothing if any id is NULL and re-inserts old versions of updated rows.

## 4. Scheduled query failures
- Find the run: console *Scheduled queries → Run history*, or `bq ls --transfer_run --run_attempt=LATEST projects/P/locations/L/transferConfigs/ID`.
- The run's job ID starts with `scheduled_query_`; inspect it with `bq show -j`.
- Common causes: run-as identity lost access; destination table schema changed; query not idempotent so a retry duplicated data or conflicted with a concurrent run.
- Notifications (email / Pub/Sub) are set in the console or API, not the bq CLI.

## 5. Reply format
State the cause in one sentence, the evidence (reason + key part of the message), the fix with real names, and how to confirm it (re-run, or no new errors of that reason in INFORMATION_SCHEMA.JOBS).
