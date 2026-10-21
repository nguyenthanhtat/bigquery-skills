---
description: BQML classifier options
tags: [correctness]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---
Train a churn classifier in BigQuery ML on table ml.users. The label column is churned (BOOL); user_id is the key. Then evaluate it.
