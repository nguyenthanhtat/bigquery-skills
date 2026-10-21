# bigquery-skills

Claude Code plugin that audits your Google BigQuery project and tells you what to fix — plus how-to skills for day-to-day BigQuery work.

## Audit your BigQuery project

Ask Claude: *"Audit my BigQuery project `my-project` in `US`"* (or `/bigquery-skills:bq-audit`).

1. **Plan** — dry-runs the collectors and shows what the audit will cost (usually cents). Nothing runs until you say yes.
2. **Collect** — read-only `INFORMATION_SCHEMA` queries plus `bq show` / `bq ls` / `gcloud get-iam-policy`, each capped with `--maximum_bytes_billed` and labelled `tool=bq-audit`.
3. **Analyze** — `analyze.py` computes metrics and candidate findings deterministically; analyst agents confirm them, find root causes and write fixes.
4. **Report** — `bq-audit-<project>-<date>/REPORT.md` and `findings.json`: health score per area, evidence, fix steps, risk, estimated monthly impact.

Areas: cost · performance · schema & storage · security · reliability.

The audit never changes anything. Fixes that write, rewrite, delete, or change access are marked *requires approval*.

**Check your setup** at any time: `bash scripts/bq-preflight.sh [--project PROJECT]`. The plugin runs the same check automatically before any of its skills loads, and tells you exactly what to install, log in to, or ask your admin for.

**You need:** the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`, `bq`), Python 3, and `gcloud auth login`. Roles on the project: `roles/bigquery.resourceViewer`, `roles/bigquery.metadataViewer`, `roles/bigquery.jobUser`; optionally `roles/iam.securityReviewer` for IAM checks. Missing roles skip the matching checks; the report says which.

## Install

```bash
# In Claude Code
/plugin marketplace add nguyenthanhtat/bigquery-skills
/plugin install bigquery-skills@bigquery-skills
```

Local test without publishing:

```bash
claude --plugin-dir /path/to/bigquery-skills
```

## Skills

## How-to skills

| Skill | Use for |
|---|---|
| `bq-audit` | Read-only health audit of a whole project (see above) |
| `bigquery` | Overview and routing when the task spans several areas |
| `bigquery-query-optimization` | Slow/expensive queries, JOIN duplication, bytes processed |
| `bigquery-data-loading` | Load/export CSV, JSON, Parquet…, streaming, federated queries |
| `bigquery-bqml` | BigQuery ML: classification, regression, clustering, forecasting |
| `bigquery-scheduled-queries` | Scheduled queries, incremental ETL, notifications |
| `bigquery-cost-monitoring` | Spend by project/user/query, budget alerts, slots |
| `bigquery-security` | Row/column-level security, IAM, audit logging |
| `bigquery-schema-design` | Partitioning, clustering, nested/repeated fields |
| `bigquery-troubleshooting` | Error messages, permissions, quotas |

Claude picks the right skill automatically from your request. To call one directly: `/bigquery-skills:bigquery-query-optimization <request>`.

## Requirements

- BigQuery API enabled in a GCP project
- Credentials with the needed BigQuery permissions
- `bq` CLI, or the Python / Node.js client library

## License

MIT
