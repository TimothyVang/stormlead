-- least-privilege roles
-- the agent-runtime, when querying postgres via mcp, MUST use stormlead_ro
-- never expose the stormlead role to llm input

\connect stormlead

-- read-only role for agents and analytics
CREATE ROLE stormlead_ro LOGIN PASSWORD 'change-me-ro';
GRANT CONNECT ON DATABASE stormlead TO stormlead_ro;
GRANT USAGE ON SCHEMA public TO stormlead_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO stormlead_ro;

-- statement timeout to neutralize bad queries from agents
ALTER ROLE stormlead_ro SET statement_timeout = '30s';
ALTER ROLE stormlead_ro SET idle_in_transaction_session_timeout = '60s';

-- write role for the apps (not exposed to agents directly)
-- the existing 'stormlead' superuser stays as-is for migrations
-- in prod, create a stormlead_app with INSERT/UPDATE/DELETE only on specific tables
