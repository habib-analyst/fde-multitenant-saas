"""Database stores and tenant sessions.

Two backends, one repository API (see repository.py):

* Postgres — the production-shaped backend. Every session runs
  ``SELECT set_config('app.tenant_id', ..., false)`` on its connection so
  the RLS policies in migrations/001_rls.sql do the isolation in the
  database itself.
* SQLite — the portable backend used by the default test run. SQLite has
  no RLS, so the repository injects ``tenant_id = ?`` into every query;
  the wrapper object carries the tenant so no query can forget it.

A session is bound to exactly one TenantContext for its whole lifetime —
there is no API to switch tenant mid-session.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .context import TenantContext

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tenant_id, email)
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    project_id TEXT,
    meter TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects (tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_meter_time
    ON usage_events (tenant_id, meter, occurred_at);
"""


class SQLiteStore:
    """Owns one SQLite connection; hands out tenant-bound sessions."""

    backend = "sqlite"

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SQLITE_SCHEMA)
        self._conn.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @contextmanager
    def session(self, ctx: TenantContext) -> Iterator["SQLiteSession"]:
        yield SQLiteSession(self._conn, ctx)

    # -- admin/seed helpers (not tenant-scoped; used by fixtures only) ----
    def seed_tenant(self, tenant_id: str, name: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name) VALUES (?, ?)",
            (tenant_id, name),
        )
        self._conn.commit()

    def seed_user(self, user_id: str, tenant_id: str, email: str, role: str = "member") -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO users (id, tenant_id, email, role) VALUES (?, ?, ?, ?)",
            (user_id, tenant_id, email, role),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class SQLiteSession:
    def __init__(self, conn: sqlite3.Connection, ctx: TenantContext) -> None:
        self.conn = conn
        self.ctx = ctx
        self.backend = "sqlite"
        self.placeholder = "?"

    def commit(self) -> None:
        self.conn.commit()


class PostgresStore:
    """Postgres store. Sessions set app.tenant_id so RLS enforces isolation."""

    backend = "postgres"

    def __init__(self, dsn: str) -> None:
        import psycopg  # imported lazily so SQLite-only runs never need it

        self._psycopg = psycopg
        self._dsn = dsn

    @contextmanager
    def session(self, ctx: TenantContext) -> Iterator["PostgresSession"]:
        from psycopg.rows import dict_row

        conn = self._psycopg.connect(self._dsn, row_factory=dict_row)
        try:
            # The one line that arms RLS for everything this session does.
            conn.execute(
                "SELECT set_config('app.tenant_id', %s, false)", (ctx.tenant_id,)
            )
            yield PostgresSession(conn, ctx)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def seed_tenant(self, tenant_id: str, name: str) -> None:
        # Seeding runs as the migration/owner connection (RLS-exempt only if
        # the connecting role owns the tables); in the integration test the
        # same DSN is used and rows are inserted with an explicit context.
        ctx = TenantContext(tenant_id=tenant_id)
        with self.session(ctx) as s:
            s.conn.execute(
                "INSERT INTO tenants (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tenant_id, name),
            )

    def seed_user(self, user_id: str, tenant_id: str, email: str, role: str = "member") -> None:
        ctx = TenantContext(tenant_id=tenant_id)
        with self.session(ctx) as s:
            s.conn.execute(
                "INSERT INTO users (id, tenant_id, email, role) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (user_id, tenant_id, email, role),
            )


class PostgresSession:
    def __init__(self, conn, ctx: TenantContext) -> None:
        self.conn = conn
        self.ctx = ctx
        self.backend = "postgres"
        self.placeholder = "%s"

    def commit(self) -> None:
        self.conn.commit()
