SET PAGES 200 LINES 240 FEEDBACK OFF VERIFY OFF HEADING OFF
DEF PDB='&1'
ALTER SESSION SET CONTAINER=&&PDB;
SELECT 'CON_NAME=' || SYS_CONTEXT('USERENV','CON_NAME') FROM dual;
SELECT 'SESSION_USED_PCT=' || ROUND(current_utilization / NULLIF(TO_NUMBER(DECODE(limit_value,'UNLIMITED',NULL,limit_value)),0) * 100, 2)
FROM v$resource_limit WHERE resource_name='sessions';
SELECT 'TABLESPACE_MAX_USED_PCT=' || NVL(MAX(ROUND(used_percent,2)),0) FROM dba_tablespace_usage_metrics;
SELECT 'CPU_UTIL_PCT=' || NVL(ROUND(MAX(value),2),0) FROM v$sysmetric WHERE metric_name IN ('Host CPU Utilization (%)','CPU Usage Per Sec') AND group_id IN (2,3);
EXIT
