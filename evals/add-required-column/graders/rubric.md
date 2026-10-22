---
type: llm
weight: 3
---
PASS if the reply says a REQUIRED/NOT NULL column cannot be added to an existing table, adds it as NULLABLE (optionally with DEFAULT 'unknown' for new rows), backfills existing rows with an UPDATE that has a WHERE clause (e.g. WHERE signup_source IS NULL) after a dry run, and enforces non-null going forward in the pipeline or by rebuilding into a new table with the column REQUIRED.
FAIL if it runs ALTER TABLE ... ADD COLUMN ... NOT NULL as if it works, or recreates the live table with CREATE OR REPLACE.
