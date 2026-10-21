-- Scheduled query runs grouped by destination; last status tells if the pipeline is broken now.
SELECT
  CONCAT(IFNULL(destination_table.dataset_id, '?'), '.', IFNULL(destination_table.table_id, '?')) AS destination,
  ANY_VALUE(user_email) AS run_as,
  COUNT(*) AS runs,
  COUNTIF(error_result IS NOT NULL) AS failed_runs,
  SUM(total_bytes_billed) AS bytes_billed,
  MAX(creation_time) AS last_run,
  ARRAY_AGG(STRUCT(creation_time, error_result.reason AS reason, LEFT(error_result.message, 300) AS message)
            ORDER BY creation_time DESC LIMIT 3) AS recent_runs
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE {{JOBS_FILTER}}
  AND job_id LIKE 'scheduled_query%'
GROUP BY destination
ORDER BY failed_runs DESC, bytes_billed DESC
LIMIT 200
