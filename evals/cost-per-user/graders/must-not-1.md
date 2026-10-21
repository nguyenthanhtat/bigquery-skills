---
type: regex
pattern: 'POW\\(\\s*10\\s*,\\s*12\\s*\\)|1e12|1000000000000'
flags: i
match: not_contains
---
Billing is per TiB, not per 10^12 bytes
