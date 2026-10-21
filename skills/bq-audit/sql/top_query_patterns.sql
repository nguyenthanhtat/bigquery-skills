-- Most expensive recurring query shapes (literals normalized).
SELECT
  COALESCE(query_info.query_hashes.normalized_literals, TO_HEX(MD5(query))) AS query_hash,
  COUNT(*) AS runs,
  COUNT(DISTINCT user_email) AS users,
  ANY_VALUE(user_email) AS sample_user,
  ANY_VALUE(statement_type) AS statement_type,
  SUM(total_bytes_billed) AS bytes_billed,
  MAX(total_bytes_billed) AS max_bytes_billed,
  SUM(total_slot_ms) AS slot_ms,
  AVG(TIMESTAMP_DIFF(end_time, start_time, MILLISECOND)) AS avg_duration_ms,
  MAX(TIMESTAMP_DIFF(end_time, start_time, MILLISECOND)) AS max_duration_ms,
  COUNTIF(cache_hit) AS cache_hits,
  COUNTIF(error_result IS NOT NULL) AS failed_runs,
  MAX(creation_time) AS last_run,
  ANY_VALUE(job_id) AS sample_job_id,
  ANY_VALUE(ARRAY_TO_STRING(ARRAY(
    SELECT CONCAT(rt.project_id, '.', rt.dataset_id, '.', rt.table_id)
    FROM UNNEST(referenced_tables) rt), ',')) AS referenced_tables,
  ANY_VALUE(LEFT(query, 2000)) AS sample_query
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE {{JOBS_FILTER}}
  AND job_type = 'QUERY'
  AND statement_type IS DISTINCT FROM 'SCRIPT'
GROUP BY query_hash
ORDER BY bytes_billed DESC
LIMIT 50
