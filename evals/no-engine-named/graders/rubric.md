---
type: llm
weight: 3
---
PASS if the reply treats this as Google BigQuery (or briefly confirms the engine while still giving the BigQuery procedure), explains an existing table cannot be partitioned in place, and proposes creating a new partitioned table, verifying it, and swapping names with a rollback copy; in Vietnamese.
FAIL if it states the per-table partition limit as anything other than 10,000 (4,000 is the separate per-job limit), runs CREATE OR REPLACE on the live table, or answers only for a different database engine.
