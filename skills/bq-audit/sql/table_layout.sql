-- Partitioning, clustering and guard options per table.
WITH opts AS (
  SELECT table_schema, table_name,
    MAX(IF(option_name = 'require_partition_filter', option_value, NULL)) AS require_partition_filter,
    MAX(IF(option_name = 'partition_expiration_days', option_value, NULL)) AS partition_expiration_days,
    MAX(IF(option_name = 'expiration_timestamp', option_value, NULL)) AS expiration_timestamp
  FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.TABLE_OPTIONS
  GROUP BY 1, 2
)
SELECT
  t.table_schema, t.table_name, t.table_type, t.creation_time,
  REGEXP_EXTRACT(t.ddl, r'(?m)^PARTITION BY (.+)$') AS partition_by,
  REGEXP_EXTRACT(t.ddl, r'(?m)^CLUSTER BY (.+)$') AS cluster_by,
  o.require_partition_filter, o.partition_expiration_days, o.expiration_timestamp
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.TABLES t
LEFT JOIN opts o USING (table_schema, table_name)
WHERE t.table_type IN ('BASE TABLE', 'MATERIALIZED VIEW')
LIMIT 5000
