set pages 0 feedback off verify off heading off echo off
alter session set container=&1;
select count(*)
from gv$session
where status = 'ACTIVE'
  and username = 'SYS'
  and module = 'MONITOR_V2_DEMO_AAS_CPU';
exit
