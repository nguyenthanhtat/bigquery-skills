---
description: No project-specific leakage
tags: [generic]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
env:
  EVAL_BQ_SESSION_HINT: "route-only"
  EVAL_BQ_PREFLIGHT: "off"
---
Design a BigQuery table for storing website analytics events (page views, clicks) at about 50 million events per day.
