---
type: llm
weight: 3
---
PASS if the reply recommends the BigQuery Storage Write API (default stream for at-least-once, or committed/pending streams for exactly-once) as the preferred streaming method, and notes legacy insertAll/insert_rows_json is the older API.
FAIL if it presents insert_rows_json / tabledata.insertAll as the recommended approach without mentioning the Storage Write API, or claims streamed rows take ~90 minutes to become queryable.
