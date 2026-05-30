-- Monitor_v2 perf bundle: AAS by Wait Class, 20-second buckets, DB flex/FLEXING
-- Usage: sqlplus -s / as sysdba @aas_waitclass_20s.sql <csv_path> <last_min> <bucket_sec>
DEF out        = '&1'
DEF LAST_MIN   = '&2'
DEF BUCKET_SEC = '&3'

SET HEADING OFF FEEDBACK OFF PAGES 0 LINESIZE 800 TRIMSPOOL ON VERIFY OFF TERMOUT OFF
SPOOL &&out

WITH
base AS (
  SELECT
    ash.inst_id,
    SYS_EXTRACT_UTC(CAST(ash.sample_time AS TIMESTAMP WITH TIME ZONE)) AS sample_utc,
    CASE WHEN ash.session_state = 'ON CPU' THEN 'CPU'
         ELSE NVL(ash.wait_class, 'Other')
    END AS wclass
  FROM gv$active_session_history ash
  WHERE ash.sample_time >= SYSTIMESTAMP - NUMTODSINTERVAL(&&LAST_MIN, 'MINUTE')
),
buck AS (
  SELECT
    b.inst_id,
    CAST(
      TRUNC(CAST(b.sample_utc AS DATE), 'MI') +
      NUMTODSINTERVAL(FLOOR(EXTRACT(SECOND FROM b.sample_utc) / &&BUCKET_SEC) * &&BUCKET_SEC, 'SECOND')
      AS TIMESTAMP
    ) AS bucket_start_utc,
    CAST(b.sample_utc AS DATE) AS sec_utc_date,
    b.wclass
  FROM base b
),
agg AS (
  SELECT
    bu.inst_id,
    bu.bucket_start_utc,
    bu.wclass,
    COUNT(*) AS samples,
    LEAST(&&BUCKET_SEC, GREATEST(1, COUNT(DISTINCT TO_CHAR(bu.sec_utc_date, 'YYYY-MM-DD HH24:MI:SS')))) AS sec_count
  FROM buck bu
  GROUP BY bu.inst_id, bu.bucket_start_utc, bu.wclass
),
conv AS (
  SELECT
    a.inst_id,
    (FROM_TZ(a.bucket_start_utc, 'UTC') AT TIME ZONE 'Asia/Ho_Chi_Minh') AS ts_tz,
    a.wclass,
    a.samples / a.sec_count AS aas
  FROM agg a
),
named AS (
  SELECT gi.inst_id, gi.instance_name
  FROM gv$instance gi
  GROUP BY gi.inst_id, gi.instance_name
),
pivoted AS (
  SELECT
    c.inst_id,
    n.instance_name,
    TO_CHAR(c.ts_tz, 'YYYY-MM-DD HH24:MI:SS') AS ts,
    CAST(c.ts_tz AS DATE) AS ts_sort,
    NVL(SUM(CASE WHEN c.wclass = 'CPU'            THEN c.aas END), 0) AS "CPU",
    NVL(SUM(CASE WHEN c.wclass = 'User I/O'       THEN c.aas END), 0) AS "User I/O",
    NVL(SUM(CASE WHEN c.wclass = 'System I/O'     THEN c.aas END), 0) AS "System I/O",
    NVL(SUM(CASE WHEN c.wclass = 'Concurrency'    THEN c.aas END), 0) AS "Concurrency",
    NVL(SUM(CASE WHEN c.wclass = 'Application'    THEN c.aas END), 0) AS "Application",
    NVL(SUM(CASE WHEN c.wclass = 'Administrative' THEN c.aas END), 0) AS "Administrative",
    NVL(SUM(CASE WHEN c.wclass = 'Commit'         THEN c.aas END), 0) AS "Commit",
    NVL(SUM(CASE WHEN c.wclass = 'Network'        THEN c.aas END), 0) AS "Network",
    NVL(SUM(CASE WHEN c.wclass = 'Cluster'        THEN c.aas END), 0) AS "Cluster",
    NVL(SUM(CASE WHEN c.wclass = 'Other'          THEN c.aas END), 0) AS "Other"
  FROM conv c
  JOIN named n ON n.inst_id = c.inst_id
  GROUP BY c.inst_id, n.instance_name, TO_CHAR(c.ts_tz,'YYYY-MM-DD HH24:MI:SS'), CAST(c.ts_tz AS DATE)
)
SELECT line
FROM (
  SELECT 'inst_id,instance_name,timestamp,CPU,User I/O,System I/O,Concurrency,Application,Administrative,Commit,Network,Cluster,Other' AS line,
         0 AS ord, NULL AS i_sort, NULL AS tss
  FROM dual
  UNION ALL
  SELECT TO_CHAR(inst_id)||','||instance_name||','||ts||','||
         TO_CHAR("CPU")||','||TO_CHAR("User I/O")||','||TO_CHAR("System I/O")||','||
         TO_CHAR("Concurrency")||','||TO_CHAR("Application")||','||TO_CHAR("Administrative")||','||
         TO_CHAR("Commit")||','||TO_CHAR("Network")||','||TO_CHAR("Cluster")||','||TO_CHAR("Other") AS line,
         1 AS ord,
         inst_id AS i_sort,
         ts_sort
  FROM pivoted
)
ORDER BY ord, i_sort NULLS LAST, tss NULLS FIRST;

SPOOL OFF
EXIT
