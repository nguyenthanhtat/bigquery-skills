-- Spend per principal (users and service accounts).
SELECT
  user_email,
  COUNT(*) AS jobs,
  COUNTIF(error_result IS NOT NULL) AS failed_jobs,
  SUM(total_bytes_billed) AS bytes_billed,
  SUM(total_slot_ms) AS slot_ms,
  MAX(total_bytes_billed) AS max_bytes_billed_single_job
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE {{JOBS_FILTER}}
  AND job_type = 'QUERY'
  AND statement_type IS DISTINCT FROM 'SCRIPT'
GROUP BY user_email
ORDER BY bytes_billed DESC
LIMIT 50
