-- Dataset defaults that drive storage cost and retention.
SELECT
  s.schema_name AS dataset,
  s.location,
  MAX(IF(o.option_name = 'storage_billing_model', o.option_value, NULL)) AS storage_billing_model,
  MAX(IF(o.option_name = 'max_time_travel_hours', o.option_value, NULL)) AS max_time_travel_hours,
  MAX(IF(o.option_name = 'default_table_expiration_days', o.option_value, NULL)) AS default_table_expiration_days,
  MAX(IF(o.option_name = 'default_partition_expiration_days', o.option_value, NULL)) AS default_partition_expiration_days
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.SCHEMATA s
LEFT JOIN `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.SCHEMATA_OPTIONS o
  ON o.schema_name = s.schema_name
GROUP BY 1, 2
