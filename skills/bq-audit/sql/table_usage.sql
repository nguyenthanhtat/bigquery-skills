-- How each table is read. Single-table jobs let us compare bytes scanned to table size.
WITH base AS (
  SELECT creation_time, total_bytes_processed, total_bytes_billed, referenced_tables,
         ARRAY_LENGTH(referenced_tables) AS n_tables
  FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
  WHERE {{JOBS_FILTER}}
    AND job_type = 'QUERY'
    AND statement_type IS DISTINCT FROM 'SCRIPT'
    AND error_result IS NULL
)
SELECT
  rt.project_id, rt.dataset_id, rt.table_id,
  COUNT(*) AS jobs,
  MAX(b.creation_time) AS last_referenced,
  COUNTIF(b.n_tables = 1) AS single_table_jobs,
  AVG(IF(b.n_tables = 1, b.total_bytes_processed, NULL)) AS avg_single_table_bytes_processed,
  SUM(IF(b.n_tables = 1, b.total_bytes_billed, 0)) AS single_table_bytes_billed
FROM base b, UNNEST(b.referenced_tables) rt
GROUP BY 1, 2, 3
ORDER BY single_table_bytes_billed DESC
LIMIT 500
