---
description: Cost query uses billed bytes and TiB
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
Write a SQL query that estimates our BigQuery on-demand query cost per user for the last 30 days. Our data is in the US multi-region.
