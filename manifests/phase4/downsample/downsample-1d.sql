-- Downsample 1d — aggregate from 1h table (previous day)
-- Shell substitutes: DYEAR DMONTH DDAY
INSERT INTO minio.opc_agg.sensor_1d
SELECT
  date_trunc('day', hour)  AS day_ts,
  tag_name,
  avg(avg_val)             AS avg_val,
  max(max_val)             AS max_val,
  min(min_val)             AS min_val,
  sum(samples)             AS samples,
  'DYEAR'                  AS year,
  'DMONTH'                 AS month,
  'DDAY'                   AS day
FROM minio.opc_agg.sensor_1h
WHERE year  = 'DYEAR'
  AND month = 'DMONTH'
  AND day   = 'DDAY'
GROUP BY 1, 2
;
