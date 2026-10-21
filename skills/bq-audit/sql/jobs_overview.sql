-- One-row baseline of query activity in the window.
SELECT
  COUNT(*) AS jobs,
  COUNTIF(error_result IS NOT NULL) AS failed_jobs,
  COUNTIF(cache_hit) AS cache_hits,
  SUM(total_bytes_billed) AS bytes_billed,
  SUM(total_bytes_processed) AS bytes_processed,
  SUM(total_slot_ms) AS slot_ms,
  COUNTIF(reservation_id IS NULL) AS on_demand_jobs,
  COUNTIF(reservation_id IS NOT NULL) AS reservation_jobs,
  COUNT(DISTINCT user_email) AS users,
  MIN(creation_time) AS first_job,
  MAX(creation_time) AS last_job
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE {{JOBS_FILTER}}
  AND job_type = 'QUERY'
  AND statement_type IS DISTINCT FROM 'SCRIPT'
