-- PostgreSQL setup for agent-monitor
-- Run as: sudo -u postgres psql -f infra/setup_db.sql
-- Edit the password before running!

-- 1. Create user (update password below)
CREATE USER monitor_user WITH PASSWORD 'REPLACE_ME_PASSWORD';

-- 2. Create database
CREATE DATABASE monitor_v2 OWNER monitor_user;

-- 3. Connect to the new database and create tables
\c monitor_v2

-- incidents: one row per OEM alert received
CREATE TABLE IF NOT EXISTS incidents (
    id           SERIAL PRIMARY KEY,
    target_name  TEXT NOT NULL,
    target_type  TEXT,
    severity     TEXT,
    category     TEXT,
    metric_name  TEXT,
    metric_value TEXT,
    message      TEXT,
    rule_name    TEXT,
    raw_payload  TEXT,
    rca_result   TEXT,
    notified     BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- audit_log: immutable record of all events and commands
CREATE TABLE IF NOT EXISTS audit_log (
    id            SERIAL PRIMARY KEY,
    user_id       TEXT,
    user_name     TEXT,
    command       TEXT,
    params        TEXT,
    target_name   TEXT,
    status        TEXT,
    approved_by   TEXT,
    error_message TEXT,
    executed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT ALL ON ALL TABLES IN SCHEMA public TO monitor_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO monitor_user;
