from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4


class SupabaseRepository:
    def __init__(self, *, client, owner_id: UUID) -> None:
        self.client = client
        self.owner_id = owner_id

    @property
    def _owner(self) -> str:
        return str(self.owner_id)

    def _table(self, name: str):
        return self.client.schema("compass_storage").table(name)

    def _select(self, name: str, columns: str = "*"):
        return self._table(name).select(columns).eq("owner_id", self._owner)

    def _insert(self, name: str, row: dict) -> dict:
        owned = {**row, "owner_id": self._owner}
        rows = self._table(name).insert([owned]).execute().data
        return rows[0]

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            raw = base64.urlsafe_b64decode(cursor.encode()).decode()
            offset = int(raw)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("Invalid pagination cursor") from error
        if offset < 0:
            raise ValueError("Invalid pagination cursor")
        return offset

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        return base64.urlsafe_b64encode(str(offset).encode()).decode()

    def _page(
        self,
        table: str,
        *,
        order_by: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict], str | None]:
        offset = self._decode_cursor(cursor)
        rows = (
            self._select(table)
            .order(order_by, desc=True)
            .range(offset, offset + limit)
            .execute()
            .data
        )
        has_more = len(rows) > limit
        return rows[:limit], self._encode_cursor(offset + limit) if has_more else None

    def _journal(
        self,
        *,
        record_type: str,
        source: str,
        trading_date: str,
        payload: dict,
        decision_id: str | None = None,
        run_id: str | None = None,
        target: str | None = None,
        theme: str | None = None,
        parent_record_id: str | None = None,
    ) -> dict:
        return self._insert(
            "journal_records",
            {
                "journal_record_id": str(uuid4()),
                "record_type": record_type,
                "source": source,
                "trading_date": trading_date,
                "payload": payload,
                "decision_id": decision_id,
                "run_id": run_id,
                "target": target,
                "theme": theme,
                "parent_record_id": parent_record_id,
            },
        )

    def ping(self) -> None:
        self._select("runs", "run_id").limit(1).execute()

    def list_themes(self) -> list[dict]:
        themes = self._select("themes").execute().data
        latest = (
            self._select("theme_state_daily", "d")
            .order("d", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if not latest:
            return [{**theme, "state": None} for theme in themes]
        states = self._select("theme_state_daily").eq("d", latest[0]["d"]).execute().data
        by_slug = {state["theme_slug"]: state for state in states}
        return [{**theme, "state": by_slug.get(theme["slug"])} for theme in themes]

    def theme_detail(self, slug: str, *, days: int) -> dict | None:
        themes = self._select("themes").eq("slug", slug).limit(1).execute().data
        if not themes:
            return None
        members = self._select("theme_memberships").eq("theme_slug", slug).execute().data
        history = (
            self._select("theme_state_daily")
            .eq("theme_slug", slug)
            .order("d", desc=True)
            .limit(days)
            .execute()
            .data
        )
        return {**themes[0], "members": members, "state_history": list(reversed(history))}

    def recommendations_today(self) -> dict:
        latest = (
            self._select("decision_records", "decision_date")
            .order("decision_date", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if not latest:
            return {"d": None, "recommendations": []}
        decision_date = latest[0]["decision_date"]
        rows = (
            self._select("decision_records")
            .eq("decision_date", decision_date)
            .order("instrument")
            .execute()
            .data
        )
        return {"d": decision_date, "recommendations": rows}

    def journal(self, *, days: int) -> dict:
        since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        records = (
            self._select("journal_records")
            .gte("trading_date", since)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        overrides = (
            self._select("overrides")
            .gte("ts", since)
            .order("ts", desc=True)
            .execute()
            .data
        )
        return {"since": since, "records": records, "overrides": overrides}

    def list_rule_changes(self) -> list[dict]:
        rows = self._select("rule_changes").order("proposed_at", desc=True).execute().data
        now = datetime.now(UTC)
        for row in rows:
            effective_at = datetime.fromisoformat(row["effective_at"])
            row["active"] = bool(row["approved"]) and now >= effective_at
        return rows

    def create_override(self, *, what: str, reason: str) -> dict:
        row = self._insert("overrides", {"what": what, "reason": reason})
        self._journal(
            record_type="override",
            source="compass_api",
            trading_date=datetime.now(UTC).date().isoformat(),
            payload={"override_id": row.get("id"), "what": what, "reason": reason},
        )
        return row

    def acknowledge_decision(
        self,
        decision_id: str,
        *,
        acknowledged_at: str,
    ) -> dict | None:
        matches = (
            self._select("decision_records")
            .eq("decision_id", decision_id)
            .limit(1)
            .execute()
            .data
        )
        if not matches:
            return None
        decision = matches[0]
        if decision.get("acknowledged_at") is not None:
            return decision
        updated = (
            self._table("decision_records")
            .update({"acknowledged_at": acknowledged_at})
            .eq("owner_id", self._owner)
            .eq("decision_id", decision_id)
            .execute()
            .data
        )
        if not updated:
            return None
        decision = updated[0]
        self._journal(
            record_type="acknowledgement",
            source="compass_api",
            trading_date=decision["decision_date"],
            payload={"acknowledged_at": acknowledged_at},
            decision_id=decision_id,
            run_id=decision.get("run_id"),
            target=decision.get("instrument"),
            theme=decision.get("theme_slug"),
        )
        return decision

    def create_rule_change(self, row: dict) -> dict:
        created = self._insert("rule_changes", row)
        proposed_at = datetime.fromisoformat(created["proposed_at"])
        self._journal(
            record_type="rule_change",
            source="compass_api",
            trading_date=proposed_at.date().isoformat(),
            payload={
                "rule_change_id": created.get("id"),
                "change": created["change"],
                "effective_at": created["effective_at"],
            },
        )
        return created

    def latest_backtest(self) -> dict | None:
        rows = (
            self._select("learning_reports")
            .eq("report_type", "edge_backtest")
            .order("report_date", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def list_decisions(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict], str | None]:
        return self._page(
            "decision_records",
            order_by="decision_date",
            limit=limit,
            cursor=cursor,
        )

    def decision_detail(self, decision_id: str) -> dict | None:
        rows = (
            self._select("decision_records")
            .eq("decision_id", decision_id)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return None
        journal = (
            self._select("journal_records")
            .eq("decision_id", decision_id)
            .order("created_at")
            .execute()
            .data
        )
        return {"decision": rows[0], "journal": journal}

    def list_runs(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict], str | None]:
        return self._page("runs", order_by="started_at", limit=limit, cursor=cursor)

    def provider_health(self) -> dict:
        providers = (
            self._select("provider_snapshots")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
        errors = (
            self._select("provider_errors")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
        return {"providers": providers, "recent_errors": errors}

    def system_health(self) -> list[dict]:
        rows = (
            self._select("system_health")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
        latest: dict[str, dict] = {}
        for row in rows:
            latest.setdefault(row["component"], row)
        return list(latest.values())

    def detailed_health(self) -> dict:
        health = self.system_health()
        recent_runs = (
            self._select("runs")
            .order("started_at", desc=True)
            .limit(12)
            .execute()
            .data
        )
        blocked = any(row.get("status") == "blocked" for row in health)
        return {
            "status": "degraded" if blocked else "healthy",
            "components": health,
            "recent_runs": recent_runs,
        }
