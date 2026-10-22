---
description: REQUIRED column on an existing table
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
Add a NOT NULL column signup_source STRING to our existing BigQuery table crm.customers (40M rows). Existing rows should get 'unknown'.
