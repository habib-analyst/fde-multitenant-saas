-- 001_rls.sql — Multi-tenant schema with Postgres Row-Level Security.
--
-- Isolation model: every tenant-owned table carries tenant_id. RLS policies
-- compare that column against the per-connection setting app.tenant_id, which
-- the application sets on checkout of every connection:
--
--     SELECT set_config('app.tenant_id', '<tenant-uuid-or-slug>', false);
--
-- The application connects as a NON-superuser role WITHOUT BYPASSRLS
-- (see the role section at the bottom). A superuser or a BYPASSRLS role
-- silently defeats every policy below, so the app role must never have
-- either attribute.

BEGIN;

CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_events (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id  TEXT REFERENCES projects(id) ON DELETE SET NULL,
    meter       TEXT NOT NULL,
    quantity    BIGINT NOT NULL CHECK (quantity >= 0),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects (tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_meter_time
    ON usage_events (tenant_id, meter, occurred_at);

-- ---------------------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------------------
-- current_setting('app.tenant_id', true): the second argument (missing_ok)
-- returns NULL instead of raising when the setting is absent, so an unset
-- context matches no rows at all (fail closed, never fail open).

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenants_isolation ON tenants;
CREATE POLICY tenants_isolation ON tenants
    USING (id = current_setting('app.tenant_id', true))
    WITH CHECK (id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS users_isolation ON users;
CREATE POLICY users_isolation ON users
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS projects_isolation ON projects;
CREATE POLICY projects_isolation ON projects
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS usage_events_isolation ON usage_events;
CREATE POLICY usage_events_isolation ON usage_events
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ---------------------------------------------------------------------------
-- Application role (non-superuser, no BYPASSRLS)
-- ---------------------------------------------------------------------------
-- Run once by a DBA/superuser. The password is supplied out of band by the
-- deployment environment; it is intentionally NOT part of this migration.
--
--   CREATE ROLE fde_app LOGIN PASSWORD :'app_password'
--       NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
--
-- Grants are safe to run from the migration itself:

GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, projects, usage_events TO fde_app;
GRANT USAGE, SELECT ON SEQUENCE usage_events_id_seq TO fde_app;

COMMIT;
