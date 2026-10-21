creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {{DAYS}} DAY)
  AND NOT EXISTS (SELECT 1 FROM UNNEST(labels) l WHERE l.key = 'tool' AND l.value = 'bq-audit')
