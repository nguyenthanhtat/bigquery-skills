---
type: llm
weight: 3
---
PASS if the reply uses a Data Catalog/Dataplex policy tag taxonomy, attaches the tag to the column via the table schema (bq update with schema JSON, console, or API), creates a data policy (masking rule, e.g. email mask or SHA-256) for the analysts with roles/bigquerydatapolicy.maskedReader, and gives the support team Fine-Grained Reader. An authorized view is acceptable as an alternative if presented as such.
FAIL if it uses `ALTER TABLE ... ALTER COLUMN ... SET OPTIONS(policy_tags=...)` as the way to attach the tag.
