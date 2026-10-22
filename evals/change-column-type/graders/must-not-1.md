---
type: regex
pattern: 'order_code\s+SET DATA TYPE\s+STRING'
flags: i
match: not_contains
---
INT64 to STRING is not a supported in-place type change
