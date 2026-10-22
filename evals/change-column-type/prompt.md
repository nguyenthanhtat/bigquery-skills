---
description: Widening vs incompatible type change
tags: [correctness, safety]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
In BigQuery, I need to change sales.orders.amount from INT64 to NUMERIC, and sales.orders.order_code from INT64 to STRING. How?
