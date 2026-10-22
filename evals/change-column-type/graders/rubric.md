---
type: llm
weight: 3
---
PASS if the reply uses ALTER TABLE ... ALTER COLUMN amount SET DATA TYPE NUMERIC for the widening change (allowed in place), and explains INT64 -> STRING is not a supported in-place change, so order_code needs a new column (ADD COLUMN + UPDATE with CAST) or a rewrite into a new table that is verified and swapped, with dry run / snapshot first.
FAIL if it claims INT64 -> STRING can be done with SET DATA TYPE, or rewrites the live table with CREATE OR REPLACE as the first step.
