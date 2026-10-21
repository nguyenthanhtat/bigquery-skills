---
type: llm
weight: 3
---
PASS if the reply (in Vietnamese) gives a concrete investigation path: compare total_bytes_billed by day/user/query pattern from INFORMATION_SCHEMA.JOBS between the two months, check storage growth (TABLE_STORAGE) and billing model, check new scheduled queries or BI tools, and/or offers to run the read-only audit after asking for project ID and region.
FAIL if it answers in English, gives only generic tips without a way to find the cause, or invents numbers about the user's project.
