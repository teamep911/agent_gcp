WHENEVER SQLERROR EXIT SQL.SQLCODE
SET SERVEROUTPUT ON FEEDBACK OFF VERIFY OFF
DEF PDB='&1'
DECLARE
  l_open_mode v$pdbs.open_mode%TYPE;
BEGIN
  SELECT open_mode INTO l_open_mode FROM v$pdbs WHERE name = UPPER('&&PDB');
  DBMS_OUTPUT.PUT_LINE('PDB_OPEN_MODE=' || l_open_mode);
  IF l_open_mode <> 'READ WRITE' THEN
    RAISE_APPLICATION_ERROR(-20001, 'PDB &&PDB must be READ WRITE for real demo; current open_mode=' || l_open_mode);
  END IF;
END;
/
EXIT
