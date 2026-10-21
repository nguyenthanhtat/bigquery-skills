# Evals

Each folder is one case: `prompt.md` (the user's request + run settings) and `graders/*.md` (how the answer is judged). Run them with Claude Code's plugin eval runner.

```bash
# from the repo root
claude plugin eval . --runs 3 -j 4 --max-cost-usd 20 --no-publish
claude plugin eval . --case 'delete-*' --runs 3        # one case or a glob
```

By default each case runs twice: with the plugin and without it. The report shows `WITH`, `W/OUT` and `Δ` — Δ is what the plugin adds over plain Claude. Results land in `evals/results/<timestamp>/` (gitignored); open `report.html`.

## Improve a skill (the loop)

1. **Capture the failure.** When Claude gives a wrong, unsafe, or vague BigQuery answer, copy the request into a new case.
2. **Write what "good" means** in `graders/rubric.md` as PASS/FAIL sentences. Be specific: name the correct statement, option, or step, and the wrong one.
3. **Run that case** and confirm it fails (otherwise the case isn't testing anything).
4. **Fix the skill** — the smallest change to the relevant `skills/*/SKILL.md`.
5. **Run the whole suite** with `--runs 3` and check nothing else dropped.
6. Commit the case and the fix together, and bump the version in `.claude-plugin/plugin.json` and `marketplace.json`.

## Case template

`evals/my-case/prompt.md`
```markdown
---
description: one line on what this checks
tags: [correctness]          # routing | correctness | safety | generic | audit | vi
runs: 1
max_turns: 12
allowed_tools: [Read, Glob, Grep, Skill]
---
The user's request, exactly as they'd type it.
```

`evals/my-case/graders/rubric.md` — judged by a model, majority of 3 votes
```markdown
---
type: llm
weight: 3
---
PASS if …
FAIL if …
```

`evals/my-case/graders/skill-fired.md` — reported as an indicator, not scored
```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?bigquery-schema-design"'
---
```

`evals/my-case/graders/must-not-1.md` — hard rule on the final answer
```markdown
---
type: regex
pattern: 'expiration_timestamp'
flags: i
match: not_contains
---
Why this must never appear.
```

## Rules for good cases
- Use generic names (`sales.orders`, `acme-prod`) — the plugin must work for any customer.
- One behaviour per case. If you're testing two things, write two cases.
- Rubrics judge substance, not wording; regex graders only for facts that must or must not appear.
- Keep each case cheap: no Bash unless the case needs it, `max_turns` ≤ 12.
