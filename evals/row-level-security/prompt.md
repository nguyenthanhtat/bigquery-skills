---
description: RLS syntax
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
In BigQuery, restrict table sales.orders so the EU team (group eu-team@acme.com) only sees rows where region = 'EU'.
