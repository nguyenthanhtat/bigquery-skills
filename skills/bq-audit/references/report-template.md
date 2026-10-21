# BigQuery audit — {project} ({region})

{collected_at} · window {days} days · prices: {US list | custom}

## Summary

**Health score: {overall}/100** · estimated query spend ~${query_cost}/month · storage ~${storage_cost}/month · potential savings ~${savings}/month

| Area | Score | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| Cost | | | | | |
| Performance | | | | | |
| Schema & storage | | | | | |
| Security | | | | | |
| Reliability | | | | | |

**Top actions** (ordered by severity, then savings ÷ effort):
1. {title} — {impact} — effort {S/M/L}
2. …
3. …

**Not covered:** {collectors skipped and why; what that hides}

## Key metrics
{jobs, failed %, cache hit %, users, on-demand vs reservation share, slot-hours/month, storage logical vs physical, partitioned/clustered share}

## Findings

### {ID} · {severity} · {title}
- **Evidence:** {numbers and object names from analysis files}
- **Root cause:** …
- **Recommendation:** …
- **Fix** {⚠ requires approval}:
  ```sql
  -- dry run first; set maximum_bytes_billed
  …
  ```
- **Verify:** …
- **Risk / rollback:** …
- **Impact:** ~${savings}/month · effort {S/M/L} · confidence {high/medium/low}

(repeat, grouped by area, most severe first)

## Appendix
- Collector status from manifest.json
- Pricing used
- How to re-run: `bash scripts/collect.sh run --project … --region … --days …`
