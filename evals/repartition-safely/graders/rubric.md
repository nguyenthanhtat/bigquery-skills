---
type: llm
weight: 3
---
PASS if the reply explains an existing table cannot be partitioned in place, creates a NEW partitioned (optionally clustered) table from the old one, verifies row counts, then swaps names (rename) and keeps the old table for rollback; mentions estimating the cost first (dry run, ~2 TB scanned) and pausing/redirecting writers during the swap.
FAIL if it runs CREATE OR REPLACE TABLE mydataset.events ... directly on the live table, or omits any verification/rollback step.
