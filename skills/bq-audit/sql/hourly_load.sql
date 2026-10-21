-- Average slots per hour, to spot contention and size reservations.
SELECT
  TIMESTAMP_TRUNC(creation_time, HOUR) AS hour,
  COUNT(*) AS jobs,
  SUM(total_slot_ms) / (1000 * 60 * 60) AS avg_slots,
  SUM(total_bytes_billed) AS bytes_billed
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE {{JOBS_FILTER}}
  AND job_type = 'QUERY'
  AND statement_type IS DISTINCT FROM 'SCRIPT'
GROUP BY hour
ORDER BY hour
