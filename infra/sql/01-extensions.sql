-- runs once on first postgres startup
-- the timescale-ha image has timescaledb, postgis, pgvector pre-installed

\connect stormlead

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
-- pgvectorscale's diskann is optional; install if available in the image
-- CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;

-- separate dbs for the supporting services so we don't share schemas
CREATE DATABASE hatchet OWNER stormlead;
CREATE DATABASE litellm OWNER stormlead;
CREATE DATABASE langfuse OWNER stormlead;
