---
type: llm
weight: 3
---
PASS if the reply follows an audit workflow: checks prerequisites (bq/gcloud, login, permissions such as bigquery.resourceViewer / metadataViewer), explains it will first run a free dry-run plan to estimate the audit's own cost and asks for confirmation before running anything, and states the audit is read-only.
FAIL if it presents audit findings or numbers about acme-prod (it has not collected any data), or proposes running write/DDL commands.
