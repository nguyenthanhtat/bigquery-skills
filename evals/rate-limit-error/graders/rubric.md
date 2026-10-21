---
type: llm
weight: 3
---
PASS if the reply explains this is a per-table rate limit on table metadata updates (frequent load/DML/copy jobs or schema updates into the same table in a short time), that it surfaces as a 403 rateLimitExceeded error, and fixes by batching writes (fewer, larger loads/DML), Storage Write API for streaming, or spreading writes across partitions/time, plus retry with exponential backoff.
FAIL if it says the error is HTTP 429, or only suggests requesting a quota increase.
