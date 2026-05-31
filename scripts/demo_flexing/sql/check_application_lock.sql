SET PAGES 200 LINES 240 FEEDBACK OFF VERIFY OFF
DEF PDB='&1'
ALTER SESSION SET CONTAINER=&&PDB;
COL module FORMAT A32
COL event FORMAT A36
COL wait_class FORMAT A18
COL sid_serial FORMAT A16
SELECT inst_id, sid||','||serial# sid_serial, username, status, module, wait_class, event, seconds_in_wait
FROM gv$session
WHERE module LIKE 'MONITOR_V2_DEMO_LOCK%'
ORDER BY module, inst_id, sid;
EXIT
