#!/usr/bin/env python3
"""Generate Trino SQL for downsampling setup and CronJob.
Reads tag list from opc_reader_final.groovy → outputs SQL files.
"""
import re, os

GROOVY = os.path.join(os.path.dirname(__file__), "../tools/opc_reader_final.groovy")
OUT    = os.path.join(os.path.dirname(__file__), "../manifests/phase4/downsample")
os.makedirs(OUT, exist_ok=True)

# ── Parse tag names from Groovy ──────────────────────────────
tags = []
with open(GROOVY) as f:
    for line in f:
        m = re.match(r'\s*\["([^"]+)",\s*3,\s*\d+\]', line)
        if m:
            tags.append(m.group(1))
print(f"Found {len(tags)} tags: {tags[:3]} … {tags[-3:]}")

# ── Generate SQL parts ────────────────────────────────────────

# 1. Column defs for CREATE TABLE sensor_data_flat
col_defs = "\n".join(f'  "{t}" double,' for t in tags)

# 2. ARRAY literals for UNNEST (split into chunks to avoid line length issues)
arr_names = ", ".join(f"'{t}'" for t in tags)
arr_vals  = ", ".join(f'"{t}"' for t in tags)

# ── 1. Setup SQL (run once) ───────────────────────────────────
setup_sql = f"""-- ============================================================
-- Downsample Setup — run once
-- ============================================================

-- 1. Create MinIO buckets (via mc, not SQL — see setup-job.yaml)

-- 2. Correct flat source table (replaces nested-ROW old table)
CREATE TABLE IF NOT EXISTS minio.opc.sensor_data_flat (
  "timestamp"  varchar,
  source_id    varchar,
  device_id    varchar,
  tag_count    bigint,
  bad_count    bigint,
{col_defs}
  year         varchar,
  month        varchar,
  day          varchar
)
WITH (
  external_location = 's3://opc-raw/data/',
  format            = 'JSON',
  partitioned_by    = ARRAY['year','month','day']
);

-- 3. Aggregated 1h schema + table (tall/narrow format)
CREATE SCHEMA IF NOT EXISTS minio.opc_agg;

CREATE TABLE IF NOT EXISTS minio.opc_agg.sensor_1h (
  hour         timestamp(3),
  tag_name     varchar,
  avg_val      double,
  max_val      double,
  min_val      double,
  samples      bigint,
  year         varchar,
  month        varchar,
  day          varchar
)
WITH (
  external_location = 's3://opc-1h/data/',
  format            = 'PARQUET',
  partitioned_by    = ARRAY['year','month','day']
);

CREATE TABLE IF NOT EXISTS minio.opc_agg.sensor_1d (
  day_ts       timestamp(3),
  tag_name     varchar,
  avg_val      double,
  max_val      double,
  min_val      double,
  samples      bigint,
  year         varchar,
  month        varchar,
  day          varchar
)
WITH (
  external_location = 's3://opc-1d/data/',
  format            = 'PARQUET',
  partitioned_by    = ARRAY['year','month','day']
);
"""

# ── 2. Downsample 1h SQL (parameterised with shell vars) ──────
downsample_1h_sql = f"""-- Downsample 1h — insert previous hour aggregate
-- Shell substitutes: DYEAR DMONTH DDAY DHOUR
INSERT INTO minio.opc_agg.sensor_1h
WITH src AS (
  SELECT
    date_trunc('hour', from_iso8601_timestamp("timestamp")) AS h,
    ARRAY[{arr_names}] AS tag_names,
    ARRAY[{arr_vals}]  AS tag_vals
  FROM minio.opc.sensor_data_flat
  WHERE year  = 'DYEAR'
    AND month = 'DMONTH'
    AND day   = 'DDAY'
    AND hour(from_iso8601_timestamp("timestamp")) = DHOUR
)
SELECT
  h                                        AS hour,
  tag_name,
  avg(tag_val)                             AS avg_val,
  max(tag_val)                             AS max_val,
  min(tag_val)                             AS min_val,
  count(*)                                 AS samples,
  'DYEAR'                                  AS year,
  'DMONTH'                                 AS month,
  'DDAY'                                   AS day
FROM src
CROSS JOIN UNNEST(tag_names, tag_vals) AS t(tag_name, tag_val)
WHERE tag_val IS NOT NULL
GROUP BY h, tag_name
;
"""

# ── 3. Downsample 1d SQL ──────────────────────────────────────
downsample_1d_sql = f"""-- Downsample 1d — aggregate from 1h table (previous day)
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
"""

# ── Write files ───────────────────────────────────────────────
files = {
    "setup.sql":         setup_sql,
    "downsample-1h.sql": downsample_1h_sql,
    "downsample-1d.sql": downsample_1d_sql,
}
for name, content in files.items():
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        f.write(content)
    print(f"wrote {path}")
