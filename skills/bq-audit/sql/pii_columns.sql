-- Columns whose names suggest personal data; reviewed against access controls.
SELECT table_schema, table_name, column_name, data_type
FROM `{{PROJECT}}`.`{{REGION_Q}}`.INFORMATION_SCHEMA.COLUMNS
WHERE REGEXP_CONTAINS(LOWER(column_name),
  r'(^|_)(e_?mail|phone|mobile|ssn|passport|national_id|dob|birth|address|ip_?addr|ip|credit_?card|card_number|iban|tax_id|salary)($|_)')
LIMIT 1000
