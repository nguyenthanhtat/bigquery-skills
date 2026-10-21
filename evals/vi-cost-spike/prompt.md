---
description: Vietnamese cost investigation
tags: [routing, vi]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
Tiền BigQuery tháng này tăng gấp đôi so với tháng trước. Giúp tôi tìm nguyên nhân.
