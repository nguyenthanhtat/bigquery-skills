# Security checks

Least privilege baseline:
- Analysts: `roles/bigquery.jobUser` on the project + `roles/bigquery.dataViewer` on specific datasets.
- Pipelines: a dedicated service account with `jobUser` + `dataEditor` on the datasets it writes.
- `roles/bigquery.user` lets holders create datasets — broader than most people need.
- Admins (`roles/bigquery.admin`, project owner/editor): a small group, not individuals or service accounts.

## SEC1 — Public dataset grants (critical)
`allUsers` / `allAuthenticatedUsers` on a dataset exposes it to anyone with a Google account.
- Fix (requires approval): `REVOKE \`roles/bigquery.dataViewer\` ON SCHEMA \`p.ds\` FROM "specialGroup:allAuthenticatedUsers";` or edit the ACL: `bq show --format=prettyjson p:ds > ds.json`, remove the entry, `bq update --source ds.json p:ds`.
- If sharing is intended, use Analytics Hub listings or authorized views/datasets.

## SEC2 — Broad project roles
- Service accounts with Editor/Owner (often the default compute SA) are the top lateral-movement risk.
- Use `GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`p.ds\` TO "group:analysts@corp.com";` for dataset scope; project roles via `gcloud projects add-iam-policy-binding` / `remove-iam-policy-binding` — removing must be coordinated with owners.

## SEC3 / SEC4 — Domain-wide writes, personal accounts
- Replace `domain:` writer/owner grants and `@gmail.com` users with groups.

## SEC6 — Columns that look like personal data (info)
- Name matching only. Recommend reviewing who can read those tables and, where needed:
  - Column-level security: policy tags in a taxonomy with access control enforced, applied via the table schema (`bq update` with a schema JSON or the console). Readers need `roles/datacatalog.categoryFineGrainedReader`.
  - Dynamic data masking: a data policy on the policy tag; masked readers get `roles/bigquerydatapolicy.maskedReader`.
  - Row-level security: `CREATE ROW ACCESS POLICY f ON \`p.ds.t\` GRANT TO ("group:x@corp.com") FILTER USING (region = 'EU');` — once any policy exists, principals not granted by some policy see zero rows.
  - Authorized views for curated subsets.

## Not covered by the collectors (mention as next steps when relevant)
VPC Service Controls perimeter, CMEK (`defaultEncryptionConfiguration` is in dataset_acl.json), Data Access audit logs retention, Sheets/Drive external tables.
