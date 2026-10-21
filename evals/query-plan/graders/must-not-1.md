---
type: regex
pattern: '\bEXPLAIN\s+(ANALYZE\s+)?SELECT'
flags: i
match: not_contains
---
BigQuery has no EXPLAIN statement
