---
name: bigquery
description: "Index of the BigQuery skills. Use only for general or unclear Google BigQuery questions that span several areas or don't fit one specific skill; otherwise use the specific bigquery-* or bq-audit skill directly."
---

# BigQuery skills index

Pick the most specific skill below and load it. For project-wide health, cost, or "what should we fix" questions, use `bq-audit`.

| Skill | Use when |
|---|---|
| `bq-audit` | Audit a whole project: cost, performance, schema, security, reliability (read-only, free dry-run plan first) |
| `bigquery-query-optimization` | A query is slow or expensive, JOIN multiplies rows, reading a query plan |
| `bigquery-data-loading` | Loading/exporting files, streaming (Storage Write API), external tables |
| `bigquery-schema-design` | Designing or changing tables: partitioning, clustering, nested fields, retention |
| `bigquery-bqml` | Training, evaluating, or predicting with BigQuery ML or remote/Gemini models |
| `bigquery-scheduled-queries` | Scheduling recurring queries, incremental ETL, backfills |
| `bigquery-cost-monitoring` | Measuring spend, storage billing, guardrails (quotas, max bytes billed) |
| `bigquery-security` | IAM, row/column-level security, masking, authorized views, access audit |
| `bigquery-troubleshooting` | A job fails with an error, quota/rate limits, recovering deleted data |

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

## Conventions
- SQL is GoogleSQL (`--use_legacy_sql=false`). Qualify INFORMATION_SCHEMA by region: `` `region-us`.INFORMATION_SCHEMA.JOBS ``.
- Prices quoted are US list prices; other regions and contracts differ.
- Answer in the user's language.
