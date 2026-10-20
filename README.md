# bigquery-skills

Claude Code plugin with skills for Google BigQuery (Standard SQL).

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

| Skill | Use for |
|---|---|
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
