-- Size and storage billing inputs per table.
SELECT
  table_schema, table_name, table_type, creation_time, storage_last_modified_time,
  total_rows, total_partitions,
  total_logical_bytes, active_logical_bytes, long_term_logical_bytes,
  total_physical_bytes, active_physical_bytes, long_term_physical_bytes,
  time_travel_physical_bytes, fail_safe_physical_bytes
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.TABLE_STORAGE
WHERE project_id = '{{PROJECT}}'
  AND NOT deleted
ORDER BY total_logical_bytes DESC
LIMIT 2000
