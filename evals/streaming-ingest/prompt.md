---
description: Storage Write API over insertAll
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
What's the recommended way to stream rows into BigQuery from a Python service today? Show a minimal example.
