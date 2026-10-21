---
type: llm
weight: 3
---
PASS if the reply uses partition expiration (ALTER TABLE ... SET OPTIONS(partition_expiration_days=365)) when the table is partitioned, and explains what to do if it is not (partition it first, or a scheduled DELETE with a date filter), warns that expiration deletes immediately and is hard to undo, and suggests checking the partitioning/backup first.
FAIL if it recommends setting expiration_timestamp on the table to drop old rows (that deletes the entire table), or runs a DELETE without any preview/dry-run/caution.
