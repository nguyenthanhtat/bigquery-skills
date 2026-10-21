---
description: Exact BigQuery limits
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
For a BigQuery table partitioned by day, what's the maximum number of partitions, and how many years of daily data is that? What should I do if I need more history?
