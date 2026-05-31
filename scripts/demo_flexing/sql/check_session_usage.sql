SET PAGES 200 LINES 240 FEEDBACK OFF VERIFY OFF HEADING OFF
DEF PDB='&1'
ALTER SESSION SET CONTAINER=&&PDB;
SELECT 'CON_NAME=' || SYS_CONTEXT('USERENV','CON_NAME') FROM dual;
SELECT 'DEMO_SESSION_COUNT=' || COUNT(*) FROM gv$session WHERE module='MONITOR_V2_DEMO_SESSION';
SELECT 'SESSION_CURRENT=' || current_utilization FROM v$resource_limit WHERE resource_name='sessions';
SELECT 'SESSION_LIMIT=' || limit_value FROM v$resource_limit WHERE resource_name='sessions';
SELECT 'SESSION_USED_PCT=' || ROUND(current_utilization / NULLIF(TO_NUMBER(DECODE(limit_value,'UNLIMITED',NULL,limit_value)),0) * 100, 2)
FROM v$resource_limit WHERE resource_name='sessions';
EXIT
