---
description: Knowledge question on a machine without BigQuery setup
tags: [setup]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "simulate-fail"
---
In BigQuery, when should I partition a table and when should I cluster it? Give me a rule of thumb.
