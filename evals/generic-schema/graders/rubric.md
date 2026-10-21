---
type: llm
weight: 3
---
PASS if the design partitions by event date (DAY), clusters by up to four commonly filtered columns (e.g. event_name, user/session id), uses appropriate types (TIMESTAMP, JSON or STRUCT/ARRAY for params), sets require_partition_filter or explains it, and stays generic to the user's request.
FAIL if it refers to unrelated domains (cars, automotive, Vietnam market, ListenLayer) or unrelated example tables.
