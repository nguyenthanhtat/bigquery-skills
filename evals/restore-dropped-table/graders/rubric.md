---
type: llm
weight: 3
---
PASS if the reply restores via time travel by copying a snapshot decorator of the deleted table to a table, e.g. `bq cp analytics.orders@<epoch_ms or -3600000> analytics.orders_restored` (or equivalent), mentions the time-travel window (default 7 days, configurable 2-7) and restoring to a new table name before swapping.
FAIL if the main method is `SELECT ... FOR SYSTEM_TIME AS OF` against the dropped table, or it claims the data is unrecoverable.
