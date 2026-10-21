---
type: llm
weight: 3
---
PASS if the reply uses CREATE ROW ACCESS POLICY ... ON sales.orders GRANT TO ("group:eu-team@acme.com") FILTER USING (region = 'EU') with the principal-type prefix, and warns that once any row access policy exists, users not granted by a policy see no rows (so other teams/admins need their own policy, e.g. FILTER USING (TRUE)).
FAIL if the grantee is written without the group:/user: prefix, or the zero-rows side effect is not mentioned.
