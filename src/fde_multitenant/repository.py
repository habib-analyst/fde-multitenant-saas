"""One repository API over both backends.

Isolation contract, identical on both backends:
* lists only ever return the session tenant's rows;
* get/update/delete by id are tenant-scoped — another tenant's id behaves
  exactly like a nonexistent id (None / False), so existence never leaks;
* inserts always stamp the session tenant's id, whatever the caller passes.

On Postgres the database ALSO enforces this via RLS (the tenant filter
here is defense in depth); on SQLite the filter is the enforcement.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from .billing import Invoice, build_invoice


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _row_to_dict(row) -> dict:
    return dict(row)


class TenantRepository:
    def __init__(self, session) -> None:
        self._s = session

    @property
    def _ph(self) -> str:
        return self._s.placeholder

    @property
    def _tenant(self) -> str:
        return self._s.ctx.tenant_id

    def _execute(self, sql: str, params: tuple = ()):
        cur = self._s.conn.execute(sql, params)
        return cur

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._execute(sql, params)
        return [_row_to_dict(r) for r in cur.fetchall()]

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cur = self._execute(sql, params)
        row = cur.fetchone()
        return _row_to_dict(row) if row is not None else None

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def create_project(self, name: str, description: str = "", project_id: str | None = None) -> dict:
        pid = project_id or _new_id("proj")
        ph = self._ph
        self._execute(
            f"INSERT INTO projects (id, tenant_id, name, description) VALUES ({ph}, {ph}, {ph}, {ph})",
            (pid, self._tenant, name, description),
        )
        self._s.commit()
        return self.get_project(pid)  # type: ignore[return-value]

    def list_projects(self) -> list[dict]:
        ph = self._ph
        return self._fetchall(
            f"SELECT * FROM projects WHERE tenant_id = {ph} ORDER BY created_at, id",
            (self._tenant,),
        )

    def get_project(self, project_id: str) -> dict | None:
        ph = self._ph
        return self._fetchone(
            f"SELECT * FROM projects WHERE id = {ph} AND tenant_id = {ph}",
            (project_id, self._tenant),
        )

    def update_project(self, project_id: str, name: str | None = None, description: str | None = None) -> dict | None:
        current = self.get_project(project_id)
        if current is None:
            return None
        ph = self._ph
        self._execute(
            f"UPDATE projects SET name = {ph}, description = {ph} WHERE id = {ph} AND tenant_id = {ph}",
            (
                name if name is not None else current["name"],
                description if description is not None else current["description"],
                project_id,
                self._tenant,
            ),
        )
        self._s.commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        ph = self._ph
        cur = self._execute(
            f"DELETE FROM projects WHERE id = {ph} AND tenant_id = {ph}",
            (project_id, self._tenant),
        )
        self._s.commit()
        return (cur.rowcount or 0) > 0

    # ------------------------------------------------------------------
    # Usage events
    # ------------------------------------------------------------------
    def record_event(
        self,
        user_id: str,
        meter: str,
        quantity: int,
        project_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict:
        if quantity < 0:
            raise ValueError("quantity must be >= 0")
        if project_id is not None and self.get_project(project_id) is None:
            # A project id from another tenant (or nowhere) is rejected the
            # same way: it does not exist *for this tenant*.
            raise ValueError("project not found for tenant")
        ph = self._ph
        ts = occurred_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if self._s.backend == "postgres":
            row = self._fetchone(
                f"INSERT INTO usage_events (tenant_id, user_id, project_id, meter, quantity, occurred_at) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}) RETURNING *",
                (self._tenant, user_id, project_id, meter, quantity, ts),
            )
            self._s.commit()
            return row  # type: ignore[return-value]
        cur = self._execute(
            f"INSERT INTO usage_events (tenant_id, user_id, project_id, meter, quantity, occurred_at) "
            f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
            (self._tenant, user_id, project_id, meter, quantity, ts),
        )
        self._s.commit()
        return self._fetchone(  # type: ignore[return-value]
            f"SELECT * FROM usage_events WHERE id = {ph} AND tenant_id = {ph}",
            (cur.lastrowid, self._tenant),
        )

    def list_events(self, meter: str | None = None) -> list[dict]:
        ph = self._ph
        if meter is not None:
            return self._fetchall(
                f"SELECT * FROM usage_events WHERE tenant_id = {ph} AND meter = {ph} ORDER BY id",
                (self._tenant, meter),
            )
        return self._fetchall(
            f"SELECT * FROM usage_events WHERE tenant_id = {ph} ORDER BY id",
            (self._tenant,),
        )

    # ------------------------------------------------------------------
    # Analytics + billing inputs
    # ------------------------------------------------------------------
    def _window_start(self, days: int) -> str:
        start = datetime.now(timezone.utc) - timedelta(days=days)
        return start.strftime("%Y-%m-%d %H:%M:%S")

    def usage_totals_by_meter(self, days: int = 30) -> dict[str, int]:
        ph = self._ph
        rows = self._fetchall(
            f"SELECT meter, SUM(quantity) AS total FROM usage_events "
            f"WHERE tenant_id = {ph} AND occurred_at >= {ph} GROUP BY meter",
            (self._tenant, self._window_start(days)),
        )
        return {r["meter"]: int(r["total"]) for r in rows}

    def analytics_summary(self, days: int = 30) -> dict:
        ph = self._ph
        since = self._window_start(days)
        by_meter_rows = self._fetchall(
            f"SELECT meter, SUM(quantity) AS total_quantity, COUNT(*) AS event_count "
            f"FROM usage_events WHERE tenant_id = {ph} AND occurred_at >= {ph} "
            f"GROUP BY meter ORDER BY meter",
            (self._tenant, since),
        )
        by_meter = [
            {
                "meter": r["meter"],
                "total_quantity": int(r["total_quantity"]),
                "event_count": int(r["event_count"]),
            }
            for r in by_meter_rows
        ]
        totals_row = self._fetchone(
            f"SELECT COUNT(*) AS event_count, COUNT(DISTINCT user_id) AS active_users "
            f"FROM usage_events WHERE tenant_id = {ph} AND occurred_at >= {ph}",
            (self._tenant, since),
        )
        return {
            "tenant_id": self._tenant,
            "window_days": days,
            "by_meter": by_meter,
            "total_events": int(totals_row["event_count"]) if totals_row else 0,
            "active_users": int(totals_row["active_users"]) if totals_row else 0,
        }

    def invoice(self, days: int = 30) -> Invoice:
        return build_invoice(self._tenant, self.usage_totals_by_meter(days=days))
