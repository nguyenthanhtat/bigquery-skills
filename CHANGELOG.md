# Changelog

## 3.2.1 — 2026-10-22
- `bq-audit` collector runs on macOS's default bash 3.2 (no associative arrays).
- README lists `python3`/`bash` requirements and Windows (Git Bash or WSL).

## 3.2.0 — 2026-10-22
- Preflight hook blocks only `bq-audit` when BigQuery isn't set up; how-to skills still answer and end with the setup steps.

## 3.1.0 — 2026-10-22
- `bigquery-schema-design`: safety copies (snapshot/clone) before risky changes; post-incident recovery lives in `bigquery-troubleshooting`. Per-job 4,000-partition limit; streaming buffer blocks rename.
- `bq-audit` runs its scripts directly instead of delegating to agents.
- Evals for adding a REQUIRED column and changing column types.

## 3.0.0 — 2026-10-21
- New `bq-audit` skill and `bq-audit-analyst` agent: read-only audit of cost, performance, schema & storage, security and reliability with a scored report.
- Rewrote the eight how-to skills and the index skill for any project; shared safety rules.
- Hooks: session hint (routes BigQuery questions that don't say "BigQuery") and preflight setup check.
- Eval suite.

## 2.0.0 — 2026-10-20
- Split out of `screen1-claude` as a standalone plugin.
