<div align="center">

# BigQuery Skills for Claude Code

**Audit, optimize and operate Google BigQuery from your terminal: read-only by default, cost-aware by design.**

[![Version](https://img.shields.io/badge/version-3.0.0-blue)](.claude-plugin/plugin.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-d97757)](https://code.claude.com/docs/en/plugins)
[![Evals](https://img.shields.io/badge/evals-17%2F18%20passing-brightgreen)](#quality-and-evals)

</div>

---

Most BigQuery problems repeat from project to project: a full scan of an unpartitioned table driving half the bill, a dashboard re-aggregating raw events every five minutes, a scheduled query silently failing for a week, a CI service account that can grant itself owner. This plugin turns the checks an experienced BigQuery engineer runs into skills Claude Code can apply to **your** project, using **your** credentials, without changing anything you haven't approved.

- **`bq-audit`** connects to a project, measures it, and returns a scored report with evidence, root causes and copy-paste fixes.
- **Nine how-to skills** cover day-to-day work: query tuning, schema design, loading, scheduling, cost control, security, BigQuery ML and troubleshooting.
- **Guardrails built in.** Every skill dry-runs first, caps bytes billed, and never starts with `CREATE OR REPLACE`, `DROP`, `TRUNCATE` or IAM changes.

## Contents

- [Quick start](#quick-start)
- [What you can ask](#what-you-can-ask)
- [Skills](#skills)
- [The audit](#the-audit)
- [Safety model](#safety-model)
- [Setup checks](#setup-checks)
- [Configuration](#configuration)
- [Quality and evals](#quality-and-evals)
- [Repository layout](#repository-layout)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)

## Quick start

**1. Install the plugin** in Claude Code:

```text
/plugin marketplace add nguyenthanhtat/bigquery-skills
/plugin install bigquery-skills@bigquery-skills
```

Restart Claude Code to load it.

**2. Connect to BigQuery** with the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud` and `bq`):

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID   # optional default
```

**3. Check the connection.** This is free and read-only:

```bash
bash ~/.claude/plugins/marketplaces/bigquery-skills/scripts/bq-preflight.sh --project YOUR_PROJECT_ID
```

```text
  ✓ gcloud    Google Cloud SDK 590.0.0
  ✓ bq        This is BigQuery CLI 2.1.40
  ✓ auth      you@company.com
  ✓ project   your-project-id
  ✓ bigquery  can list datasets in your-project-id

BigQuery: READY
```

You can skip this step. The plugin runs the same check before any skill loads and tells you what is missing.

**4. Ask a question** in plain language, in any language:

```text
> Audit my BigQuery project acme-prod in the US region
```

## What you can ask

| You say | What happens |
|---|---|
| *"Audit BigQuery project acme-prod, region US"* | `bq-audit`: free dry-run estimate, then on your OK a read-only audit and a scored report |
| *"Our BigQuery bill doubled this month — why?"* | Spend broken down by day, principal and query shape from `INFORMATION_SCHEMA.JOBS`, or a full audit |
| *"Top 10 most expensive queries in staging"* | One capped `JOBS` query ranked by `total_bytes_billed`, by individual job or by normalized query shape |
| *"This query takes 4 minutes, make it faster"* | Plan read from `job_stages`, pruning and join checks, a rewritten query, and a before/after comparison to run |
| *"Partition sales.orders (2 TB) by order_date"* | New partitioned table, verification, rename swap, rollback copy. Never an in-place `CREATE OR REPLACE` |
| *"Delete events older than a year automatically"* | `partition_expiration_days`, with a warning that `expiration_timestamp` drops the whole table |
| *"Job failed: Exceeded rate limits: too many table update operations"* | Root cause (per-table metadata rate limit, HTTP 403), batching strategy, retry with backoff |
| *"Mask the email column for analysts"* | Policy tag, data policy, `maskedReader` / Fine-Grained Reader roles, step by step |

## Skills

| Skill | Use it when |
|---|---|
| **`bq-audit`** | You want a health check of a **whole project**: cost, performance, schema & storage, security, reliability |
| `bigquery-cost-monitoring` | You need to know who or what is spending, storage cost, logical vs physical billing, or guardrails |
| `bigquery-query-optimization` | A query **succeeds** but is slow, expensive, scans too much, or returns too many rows after a join |
| `bigquery-troubleshooting` | A job **fails** with an error, or you need to recover a dropped table or deleted rows |
| `bigquery-schema-design` | You create or change a table: partitioning, clustering, types, schema changes, retention, repartitioning |
| `bigquery-data-loading` | You load, stream, upsert or export data (GCS, Storage Write API, `MERGE`, `EXPORT DATA`) |
| `bigquery-scheduled-queries` | You schedule, backfill, rerun or debug recurring SQL, and need it idempotent |
| `bigquery-security` | You grant or restrict access, use row-level security, mask columns, or audit who read what |
| `bigquery-bqml` | You train, evaluate or serve models with BigQuery ML, or call Gemini and embeddings from SQL |
| `bigquery` | Your question is broad or spans several of the above (an index that points to the right skill) |

Claude picks the skill from your request. You can also call one directly, for example `/bigquery-skills:bq-audit`.

## The audit

`bq-audit` works the way a careful consultant would: measure first, explain the evidence, and leave every change to you.

```text
 Plan ──────► Collect ──────────► Analyze ───────────► Review ─────────────► Report
 dry-run       11 read-only         deterministic        one analyst agent     REPORT.md
 estimate,     INFORMATION_SCHEMA   metrics and          per area confirms,    findings.json
 you approve   queries + bq/gcloud  candidate findings   finds root cause,     scored, with fixes
               reads, capped        (analyze.py)         writes the fix
```

### What it checks

| Area | Checks |
|---|---|
| **Cost** | Spend concentrated in one query shape · one principal dominating spend · single jobs over 1 TiB with no guardrails · logical vs physical storage billing per dataset · large tables not read or written in the window (review only) · on-demand vs editions estimate · bytes billed far above bytes processed (10 MiB per-table minimum on high-frequency queries) |
| **Performance** | Queries scanning most of a large table (pruning not working, or no partitioning) · anti-patterns in costly queries (`SELECT *`, `ORDER BY` without `LIMIT`, exact `COUNT(DISTINCT)`, unpartitioned windows, wildcard tables) · heavy queries re-run with little caching · bursty slot usage |
| **Schema & storage** | Large, frequently queried tables without partitioning or clustering · partitioned tables that allow unfiltered scans · many tiny partitions / near the 10,000 limit · temp/backup tables that never expire · date-sharded table families |
| **Security** | Datasets open to `allUsers` / `allAuthenticatedUsers` · personal accounts with access · domain-wide write grants · owner/editor/BigQuery admin on service accounts · **service accounts that can escalate to owner** (`projectIamAdmin`, `serviceAccountTokenCreator`, …) · columns that look like personal data |
| **Reliability** | Query failure rate · recurring error signatures, grouped across tenants and de-duplicated across script parent/child jobs · scheduled queries failing on their latest run · schedules owned by a person instead of a service account |

### What a finding looks like

*Illustrative example*

```text
### PER-P1-01 · high · Queries on analytics.events scan 96% of it on average (table is not partitioned)
- Evidence: 1,840 GiB table · 412 single-table queries in 30 days · ~$1,950/month on-demand
- Root cause: every dashboard query filters on event_date, but the table has no partitioning, so each query reads all of it.
- Fix ⚠ requires approval:
    1. Dry-run: bq query --dry_run --use_legacy_sql=false 'SELECT * FROM analytics.events'
    2. CREATE TABLE analytics.events_new PARTITION BY event_date CLUSTER BY event_name, user_id AS SELECT * FROM analytics.events;
    3. Compare row counts per day → pause writers → rename events → events_old, events_new → events
    4. Keep events_old 14 days for rollback
- Verify: bytes billed per dashboard query drops by >90% (INFORMATION_SCHEMA.JOBS)
- Impact: ~$1,170/month · effort M · confidence medium
```

### Cost, permissions, output

- **Audit cost.** The plan step shows the estimate before anything runs. On real projects, dry-run estimates of 70–110 GiB have billed under 10 GiB (cents at on-demand list price). Every query is capped with `--maximum_bytes_billed` (default 50 GiB per query).
- **Permissions.** Grant `roles/bigquery.resourceViewer`, `roles/bigquery.metadataViewer` and `roles/bigquery.jobUser` on the project. Add `roles/iam.securityReviewer` for the project IAM checks. When a permission is missing, the matching checks are skipped and the report marks that area **not assessed**. A missing area is never scored as healthy.
- **Output.** The audit writes `./bq-audit-<project>-<date>/` with `REPORT.md`, `findings.json`, `analysis/*.json` (the computed metrics) and `raw/*.json` (collector output). Re-audits compare against the previous `findings.json`.
- **Scope.** One project and one region per run. Audit each region separately.

> Reports contain IAM bindings, principal emails and query text. Treat them as internal documents.

## Safety model

Every skill follows the same rules:

1. **Dry-run first.** Before running anything that scans data, a skill shows the bytes it would bill (`--dry_run`), and runs it with `--maximum_bytes_billed`.
2. **No destructive first steps.** `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE` and IAM changes are never the first move. Changes go to a new table, which is verified and then swapped, and only after you approve.
3. **Your names, your project.** Commands use your real project, dataset and table names. When the location of a table is unclear, the skill asks before assuming your default project.
4. **"Unused" means "review".** A table that `JOBS_BY_PROJECT` never saw read may still be used by other projects or BI tools. Skills suggest an expiration or an archive, never a drop.

The audit adds two more rules:

- Collectors are an allowlist of `SELECT` statements, each checked for write keywords before it is sent.
- Every audit job carries the label `tool=bq-audit`, so audit jobs are excluded from the analysis and easy to find in billing.

## Setup checks

The plugin ships two hooks so new users are never left with half-working commands:

| Hook | When | What it does |
|---|---|---|
| **Session hint** | Session start (~20 ms, no network) | Tells Claude you work with BigQuery, so *"partition sales.orders"* reaches the right skill even when you don't say "BigQuery" |
| **Preflight** | Before any skill of this plugin loads | Checks the CLI, login and BigQuery access. **Not ready:** the skill is blocked and Claude walks you through the missing step (install, `gcloud auth login`, enable the API, or which role to ask your admin for). **Ready:** Claude is told your account and default project. Successful checks are cached for 10 minutes |

## Configuration

| Variable | Values | Effect |
|---|---|---|
| `BQ_SKILLS_PREFLIGHT` | `off` | Skip the preflight check (for example on machines that use only the docs-style skills) |
| `BQ_SKILLS_SESSION_HINT` | `off` · `route-only` | Disable the session hint, or keep the routing hint without your account and project |

**Pricing** used in estimates is the US multi-region list price (`skills/bq-audit/references/pricing.json`). For other regions, or for negotiated rates, copy the file, edit it, and pass `--pricing path/to/file.json` to `analyze.py`. Reports always say which prices were used.

## Quality and evals

The skills are tested with [Claude Code plugin evals](https://code.claude.com/docs/en/plugin-evals): 18 scenarios covering routing, technical correctness, safety, project-agnostic answers, the audit flow, and machines that aren't set up yet. Each case runs three times, with and without the plugin.

| | With plugin | Without plugin |
|---|---|---|
| Cases passing (3 runs each) | **17 / 18** | 11 / 18 |
| Question that doesn't name BigQuery | 1.00 | 0.00 |
| Machine without BigQuery set up | 1.00 | 0.00 |
| Audit asks for approval before running | 0.67 | 0.00 |
| Idempotent scheduled query · rate-limit error · column masking | 1.00 | 0.67 |

```bash
claude plugin eval . --runs 1 --ablation none --max-cost-usd 5      # quick check, ~$2
claude plugin eval . --runs 3 --max-cost-usd 25                     # release check, ~$12
claude plugin eval . --case 'partition-*' --runs 3                  # one area
```

See [`evals/README.md`](evals/README.md) for how to turn a wrong answer into a new test case.

## Repository layout

```text
.claude-plugin/        plugin.json, marketplace.json
skills/
  bq-audit/            SKILL.md · scripts/collect.sh · scripts/analyze.py · sql/ · references/
  bigquery-*/          one SKILL.md per how-to skill
agents/                bq-audit-analyst.md (reviews one audit area)
hooks/                 hooks.json · check-bigquery.sh · session-context.sh
scripts/               bq-preflight.sh (setup check)
evals/                 18 eval cases + README
```

## Limitations

- **One project and region per audit.** Organization-wide views (`JOBS_BY_ORGANIZATION`) and multi-region roll-ups are not collected yet.
- **Visibility.** `JOBS_BY_PROJECT` only sees jobs run in the audited project, so reads billed to other projects (BI tools, cross-project queries) are invisible. Findings that depend on this say so.
- **Editions.** Cost on reservations is estimated from slot-hours. Your Cloud Billing export remains the source of truth.
- **Not covered by collectors.** VPC Service Controls perimeters, Data Access audit log retention, and policy-tag coverage per column are left as next steps in reports.
- **Model output.** Fixes are written by an LLM from measured evidence. Review anything marked *requires approval* before you run it.

## Contributing

Issues and pull requests are welcome. For a change to a skill:

1. Add or update an eval case that fails without your change (`evals/<case>/`).
2. Make the smallest change to the relevant `skills/*/SKILL.md`.
3. Run `claude plugin eval . --runs 3` and include the before/after scores in the PR.
4. Bump the version in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, or users won't receive the update.

Keep skills generic: no company-specific names, use generic examples (`acme-prod`, `sales.orders`), and follow the [safety model](#safety-model).

## License

[MIT](LICENSE) © Nguyen Thanh Tat

*Not affiliated with or endorsed by Google. BigQuery is a trademark of Google LLC.*
