---
type: llm
weight: 3
---
PASS if the reply says a table can have at most 10,000 partitions (about 27 years of daily partitions) and suggests MONTH/YEAR partitioning (plus clustering on the date column) or splitting/archiving if more history is needed. Mentioning the separate limit of 4,000 partitions modified by a single job (relevant for backfills) is correct and fine.
FAIL if it states the per-table partition limit as anything other than 10,000.
