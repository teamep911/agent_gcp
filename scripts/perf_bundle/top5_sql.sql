-- Monitor_v2 perf bundle: Top 5 active SQL on DB flex/FLEXING
-- Usage: sqlplus -s / as sysdba @top5_sql.sql <txt_path> <csv_path>
DEF out_txt = '&1'
DEF out_csv = '&2'

ALTER SESSION SET CONTAINER=FLEXING;
SET PAGES 500 LINES 220 TRIMSPOOL ON VERIFY OFF FEEDBACK OFF TAB OFF
COL username FORMAT A24
COL sql_id FORMAT A16
COL sql_text FORMAT A110 WORD_WRAPPED
COL active_sessions FORMAT 999999
COL inst_id FORMAT 99
COL sid_serial FORMAT A20

SPOOL &&out_txt
PROMPT Top 5 Active SQL - FLEXING
PROMPT ============================================================
PROMPT Generated at:
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS generated_at FROM dual;
PROMPT

WITH active_sql AS (
  SELECT
    s.inst_id,
    s.username,
    NVL(s.sql_id, s.prev_sql_id) AS sql_id,
    COUNT(*) AS active_sessions,
    MIN(s.sid || ',' || s.serial#) AS sid_serial
  FROM gv$session s
  WHERE s.type = 'USER'
    AND s.status = 'ACTIVE'
    AND s.username IS NOT NULL
    AND NVL(s.sql_id, s.prev_sql_id) IS NOT NULL
    AND s.module NOT LIKE 'sqlplus@%'
  GROUP BY s.inst_id, s.username, NVL(s.sql_id, s.prev_sql_id)
),
ranked AS (
  SELECT a.*, ROW_NUMBER() OVER (ORDER BY active_sessions DESC, sql_id) rn
  FROM active_sql a
)
SELECT
  r.inst_id,
  r.username,
  r.sql_id,
  r.active_sessions,
  r.sid_serial,
  SUBSTR(REPLACE(REPLACE(q.sql_text, CHR(10), ' '), CHR(13), ' '), 1, 110) AS sql_text
FROM ranked r
LEFT JOIN gv$sql q ON q.inst_id = r.inst_id AND q.sql_id = r.sql_id
WHERE r.rn <= 5
ORDER BY r.active_sessions DESC, r.sql_id;

PROMPT
PROMPT Fallback Top SQL by CPU from gv$sql if active list is empty / for context
PROMPT ============================================================
SELECT * FROM (
  SELECT
    inst_id,
    parsing_schema_name AS username,
    sql_id,
    executions,
    ROUND(cpu_time/1000000,2) cpu_seconds,
    SUBSTR(REPLACE(REPLACE(sql_text, CHR(10), ' '), CHR(13), ' '), 1, 110) sql_text
  FROM gv$sql
  WHERE parsing_schema_name IS NOT NULL
    AND parsing_schema_name NOT IN ('SYS','SYSTEM')
  ORDER BY cpu_time DESC NULLS LAST
) WHERE ROWNUM <= 5;
SPOOL OFF

SET HEADING OFF PAGES 0 FEEDBACK OFF LINES 400
SPOOL &&out_csv
PROMPT inst_id,username,sql_id,active_sessions,sid_serial,sql_text
WITH active_sql AS (
  SELECT
    s.inst_id,
    s.username,
    NVL(s.sql_id, s.prev_sql_id) AS sql_id,
    COUNT(*) AS active_sessions,
    MIN(s.sid || ',' || s.serial#) AS sid_serial
  FROM gv$session s
  WHERE s.type = 'USER'
    AND s.status = 'ACTIVE'
    AND s.username IS NOT NULL
    AND NVL(s.sql_id, s.prev_sql_id) IS NOT NULL
    AND s.module NOT LIKE 'sqlplus@%'
  GROUP BY s.inst_id, s.username, NVL(s.sql_id, s.prev_sql_id)
),
ranked AS (
  SELECT a.*, ROW_NUMBER() OVER (ORDER BY active_sessions DESC, sql_id) rn
  FROM active_sql a
)
SELECT r.inst_id || ',' || r.username || ',' || r.sql_id || ',' || r.active_sessions || ',' || r.sid_serial || ',"' ||
       REPLACE(REPLACE(REPLACE(SUBSTR(NVL(q.sql_text,'<not found in gv$sql>'),1,500), '"', '""'), CHR(10), ' '), CHR(13), ' ') || '"'
FROM ranked r
LEFT JOIN gv$sql q ON q.inst_id = r.inst_id AND q.sql_id = r.sql_id
WHERE r.rn <= 5
ORDER BY r.active_sessions DESC, r.sql_id;
SPOOL OFF
EXIT
