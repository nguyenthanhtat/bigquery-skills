---
type: llm
weight: 3
---
PASS if the reply explains the row multiplication comes from the join key not being unique on one side (duplicates in customers), shows how to verify it (e.g. GROUP BY key HAVING COUNT(*) > 1), and fixes it by deduplicating/aggregating before the join (e.g. QUALIFY ROW_NUMBER() or a GROUP BY subquery). The reply is in Vietnamese.
FAIL if it suggests joining on COALESCE(key, constant) or similar NULL-matching tricks, recommends DISTINCT on the final result as the main fix without explaining the cause, or answers in English.
