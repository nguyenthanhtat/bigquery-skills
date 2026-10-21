---
type: llm
weight: 3
---
PASS if the design is idempotent so reruns/backfills don't duplicate rows: MERGE on the date key, or writing the {run_date}/{run_time} partition with WRITE_TRUNCATE, or DELETE+INSERT in a transaction; uses @run_date/@run_time parameters rather than CURRENT_DATE(); recommends a service account for the schedule and failure notifications (set in console/API).
FAIL if it uses plain WRITE_APPEND / INSERT with CURRENT_DATE() and no discussion of reruns or duplicates.
