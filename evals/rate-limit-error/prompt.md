---
description: Quota errors are 403
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
Our BigQuery jobs fail with: 'Exceeded rate limits: too many table update operations for this table'. What's going on and how do we fix it?
