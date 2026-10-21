---
description: Masking via policy tags + data policy
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
Mask the email column in crm.customers for analysts in BigQuery, but let the support team see it.
