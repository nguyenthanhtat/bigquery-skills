---
type: llm
weight: 3
---
PASS if the reply points to the query plan in the console's Execution details/graph and/or INFORMATION_SCHEMA.JOBS job_stages (or the jobs.get API), and explains what to look at (slot time per stage, shuffle/spill, records read vs written, skew).
FAIL if it presents an EXPLAIN statement as a way to get the plan in BigQuery.
