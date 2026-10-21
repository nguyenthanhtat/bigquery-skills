---
name: bigquery-security
description: "Google BigQuery access control and data protection: least-privilege IAM, dataset/table GRANT and REVOKE, row-level security (row access policies), column-level security with policy tags, dynamic data masking, authorized views/datasets/routines, access auditing, CMEK and VPC Service Controls. Use when the user wants to restrict or grant access, hide or mask sensitive columns, isolate tenants, or check who accessed what in BigQuery."
---

# BigQuery security

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

Access changes can lock people out or expose data. Show the exact change, its effect, and the rollback; let the user run it or confirm before you do.

## Least privilege
| Who | Grant |
|---|---|
| Analysts | `roles/bigquery.jobUser` on the project (run jobs) + `roles/bigquery.dataViewer` on specific datasets |
| Pipelines | A dedicated service account with `jobUser` + `roles/bigquery.dataEditor` on the datasets it writes |
| Admins | `roles/bigquery.admin` for a small group only — never as a prerequisite for a task |

- `roles/bigquery.user` also lets holders create datasets — broader than most analysts need.
- Prefer groups over individual users; avoid `allUsers` / `allAuthenticatedUsers` unless the data is meant to be public.
- Legacy dataset ACL entries `projectReaders/projectWriters/projectOwners` inherit from project Viewer/Editor/Owner; project Editor therefore writes every dataset.

## Grant and revoke on datasets and tables
```sql
GRANT `roles/bigquery.dataViewer`
ON SCHEMA `project.sales`
TO "group:analysts@example.com";

REVOKE `roles/bigquery.dataViewer`
ON SCHEMA `project.sales`
FROM "user:former.employee@example.com";

GRANT `roles/bigquery.dataViewer`
ON TABLE `project.sales.orders`
TO "serviceAccount:reporting@project.iam.gserviceaccount.com";
```
CLI alternative: back up, edit, apply.
```bash
bq show --format=prettyjson project:sales > sales_acl.json   # keep a copy for rollback
# edit the "access" array
bq update --source sales_acl.json project:sales
```
Project-level roles: `gcloud projects add-iam-policy-binding` / `remove-iam-policy-binding` (coordinate with owners).

## Row-level security
```sql
CREATE ROW ACCESS POLICY eu_only
ON `project.sales.orders`
GRANT TO ("group:eu-team@example.com")
FILTER USING (region = 'EU');
```
- Grantees need a type prefix: `user:`, `group:`, `serviceAccount:`, `domain:`, or `allAuthenticatedUsers`.
- **Once any row access policy exists on a table, principals not granted by some policy see zero rows** — including admins and service accounts. Add policies for everyone who still needs access, e.g.:
  ```sql
  CREATE ROW ACCESS POLICY all_rows ON `project.sales.orders`
  GRANT TO ("group:data-admins@example.com", "serviceAccount:etl@project.iam.gserviceaccount.com")
  FILTER USING (TRUE);
  ```
- Multi-tenant pattern: filter with a lookup, e.g. `FILTER USING (tenant_id IN (SELECT tenant_id FROM project.security.user_tenants WHERE email = SESSION_USER()))`. The policy creator needs `bigquery.tables.getData` on the lookup table.
- Users also need normal read access (`dataViewer`) to the table; RLS only narrows it.
- List / remove: `SELECT * FROM project.sales.INFORMATION_SCHEMA.ROW_ACCESS_POLICIES;` and `DROP ROW ACCESS POLICY eu_only ON project.sales.orders;` (removing the last policy restores full access for table readers).

## Column-level security and masking
1. Create a taxonomy and policy tags (Dataplex / Data Catalog → Policy tags), e.g. `PII → email`, and **enforce access control** on the taxonomy.
2. Attach the tag to the column through the table schema — not with ALTER COLUMN:
   ```bash
   bq show --schema --format=prettyjson project:crm.customers > schema.json
   # add to the email field:
   #   "policyTags": {"names": ["projects/PROJECT/locations/LOCATION/taxonomies/TAXONOMY_ID/policyTags/TAG_ID"]}
   bq update project:crm.customers schema.json
   ```
   (or the console schema editor / tables.patch API).
3. Who sees what:
   - Raw values: `roles/datacatalog.categoryFineGrainedReader` on the tag.
   - Masked values: create a **data policy** on the tag (masking rule such as email mask, SHA-256, nullify, default value, or a custom masking routine) and grant `roles/bigquerydatapolicy.maskedReader` on that data policy.
   - Neither role: queries selecting the column fail with access denied (use `SELECT * EXCEPT(email)`).
4. Taxonomies are regional — create them in the dataset's location.

Simpler alternative when tags are overkill: an **authorized view** exposing only allowed columns (or a hashed version) in a separate dataset.

## Authorized views, datasets, and routines
Let users query a view without access to its source tables:
```bash
# 1. Create the view in a dataset the users can read (e.g. project:shared)
# 2. Authorize it on the source dataset:
bq show --format=prettyjson project:raw > raw_acl.json
# add to "access": {"view": {"projectId": "project", "datasetId": "shared", "tableId": "orders_view"}}
bq update --source raw_acl.json project:raw
```
- Authorized dataset: authorize every view in a dataset at once (`{"dataset": {"dataset": {...}, "targetTypes": ["VIEWS"]}}`).
- Authorized routines: same idea for UDFs and table functions.

## Who accessed what
```sql
SELECT
  user_email,
  CONCAT(t.dataset_id, '.', t.table_id) AS table_ref,
  COUNT(*) AS queries,
  MAX(creation_time) AS last_access
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT,
  UNNEST(referenced_tables) AS t
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND t.dataset_id = 'crm'
GROUP BY user_email, table_ref
ORDER BY queries DESC;
```
- Needs `bigquery.jobs.listAll`. Only covers jobs run in this project, and only 180 days.
- For a full trail (including reads from other projects and API reads), use Cloud Audit Logs: BigQuery Data Access logs (`bigquery.googleapis.com`, enabled by default for BigQuery) routed to a log sink/dataset for long retention.

## Perimeter and encryption
- **VPC Service Controls**: put the project in a perimeter with `bigquery.googleapis.com` restricted to stop exfiltration to outside projects.
- **CMEK**: dataset default key `bq update --default_kms_key=projects/P/locations/L/keyRings/R/cryptoKeys/K project:dataset`; the BigQuery service account needs `roles/cloudkms.cryptoKeyEncrypterDecrypter`. Applies to new tables; existing tables need a copy with the key.
- Sharing outside the org: Analytics Hub listings instead of public grants.

## Quick checks
```bash
bq show --format=prettyjson project:dataset | jq '.access'             # dataset grants
gcloud projects get-iam-policy PROJECT --flatten=bindings \
  --filter='bindings.role:(roles/owner OR roles/editor OR roles/bigquery.admin)' \
  --format='table(bindings.role, bindings.members)'                     # broad project roles
```
For a full read-only review of IAM, public datasets, and broad roles across the project, use the `bq-audit` skill.
