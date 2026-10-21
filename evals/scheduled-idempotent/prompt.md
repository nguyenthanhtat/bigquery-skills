---
description: Idempotent scheduled query
tags: [correctness, safety]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
Set up a daily BigQuery scheduled query that aggregates yesterday's rows from app.events into app.daily_stats.
