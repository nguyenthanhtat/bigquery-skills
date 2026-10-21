---
description: Table question without saying BigQuery
tags: [routing, vi]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
Bảng sales.orders 2TB của tôi chưa partition, partition theo order_date giúp tôi.
