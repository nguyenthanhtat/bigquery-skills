---
description: JOIN fan-out question in Vietnamese
tags: [routing, correctness, vi]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
Query BigQuery của tôi JOIN bảng orders với bảng customers xong số dòng tăng gấp 10 lần so với orders. Sửa thế nào?
