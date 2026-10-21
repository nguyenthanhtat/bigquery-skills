---
type: llm
weight: 3
---
PASS if the query reads `region-us`.INFORMATION_SCHEMA.JOBS (or JOBS_BY_PROJECT), sums total_bytes_billed (not total_bytes_processed), converts to TiB with POW(1024,4) (or 1099511627776) and multiplies by the on-demand rate (about $6.25/TiB), and avoids double-counting script parent jobs (filter statement_type != 'SCRIPT' or parent_job_id handling) or explicitly notes it.
FAIL if it divides by POW(10,12)/1e12 as "TB", or uses total_bytes_processed as the billing basis.
