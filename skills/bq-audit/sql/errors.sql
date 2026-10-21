-- Recurring failure signatures across all job types (digits normalized).
SELECT
  job_type,
  error_result.reason AS reason,
  REGEXP_REPLACE(LEFT(error_result.message, 300), r'[0-9]+', 'N') AS message_pattern,
  COUNT(*) AS occurrences,
  COUNT(DISTINCT user_email) AS users,
  ANY_VALUE(user_email) AS sample_user,
  ANY_VALUE(job_id) AS sample_job_id,
  MAX(creation_time) AS last_seen
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE {{JOBS_FILTER}}
  AND error_result IS NOT NULL
  AND statement_type IS DISTINCT FROM 'SCRIPT'  -- a failed script repeats its child's error
GROUP BY 1, 2, 3
ORDER BY occurrences DESC
LIMIT 100
