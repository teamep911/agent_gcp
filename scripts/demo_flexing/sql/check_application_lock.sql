SET PAGES 500 LINES 400 FEEDBACK OFF VERIFY OFF TRIMSPOOL ON
DEF PDB='&1'
ALTER SESSION SET CONTAINER=&&PDB;
COL role FORMAT A8
COL owner FORMAT A30
COL username FORMAT A30
COL module FORMAT A32
COL event FORMAT A36
COL sql_id FORMAT A16
COL sql_text FORMAT A140 WORD_WRAPPED
COL sid_serial FORMAT A16
PROMPT LOCK_EVIDENCE_BEGIN
WITH demo_sessions AS (
  SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.username,
    NVL(s.sql_id, s.prev_sql_id) AS sql_id,
    s.status,
    s.module,
    s.wait_class,
    s.event,
    s.seconds_in_wait,
    CASE
      WHEN s.module = 'MONITOR_V2_DEMO_LOCK_HOLDER' THEN 'HOLDER'
      WHEN s.module = 'MONITOR_V2_DEMO_LOCK_WAITER' THEN 'WAITER'
      ELSE 'OTHER'
    END AS role
  FROM gv$session s
  WHERE s.module LIKE 'MONITOR_V2_DEMO_LOCK%'
), sql_texts AS (
  SELECT inst_id, sql_id,
         MAX(parsing_schema_name) AS owner,
         MAX(SUBSTR(REPLACE(REPLACE(sql_text, CHR(10), ' '), CHR(13), ' '), 1, 140)) AS sql_text
  FROM gv$sql
  WHERE sql_id IN (SELECT sql_id FROM demo_sessions WHERE sql_id IS NOT NULL)
  GROUP BY inst_id, sql_id
)
SELECT evidence_line
FROM (
  SELECT
    d.role || '|inst_id=' || d.inst_id ||
    '|sid_serial=' || d.sid || ',' || d.serial# ||
    '|owner=' || NVL(t.owner, d.username) ||
    '|username=' || NVL(d.username, '-') ||
    '|status=' || d.status ||
    '|module=' || d.module ||
    '|wait_class=' || NVL(d.wait_class, '-') ||
    '|event=' || NVL(d.event, '-') ||
    '|seconds_in_wait=' || NVL(TO_CHAR(d.seconds_in_wait), '0') ||
    '|sql_id=' || NVL(d.sql_id, '-') ||
    '|sql_text=' || NVL(t.sql_text, '<sql text not found in gv$sql>') AS evidence_line,
    d.role AS role_sort,
    d.inst_id AS inst_sort,
    d.sid AS sid_sort
  FROM demo_sessions d
  LEFT JOIN sql_texts t ON t.inst_id = d.inst_id AND t.sql_id = d.sql_id
)
ORDER BY role_sort, inst_sort, sid_sort;
PROMPT LOCK_EVIDENCE_END
EXIT
