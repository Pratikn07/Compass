"""API route tests against an in-memory fake of the store client."""
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from compass.api.main import app, get_client


class _Query:
    def __init__(self, rows: list[dict], table: str, db: "FakeDB"):
        self.rows = [dict(r) for r in rows]
        self.table_name = table
        self.db = db
        self._update_payload = None
        self._filters = []

    # query building
    def select(self, *_args, **_kw):
        return self

    def insert(self, rows):
        self._insert_rows = rows
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def eq(self, key, value):
        self._filters.append(lambda r: r.get(key) == value)
        return self

    def lt(self, key, value):
        self._filters.append(lambda r: r.get(key) is not None and r[key] < value)
        return self

    def gte(self, key, value):
        self._filters.append(lambda r: r.get(key) is not None and str(r[key]) >= str(value))
        return self

    def like(self, key, pattern):
        prefix = pattern.rstrip("%")
        self._filters.append(lambda r: str(r.get(key, "")).startswith(prefix))
        return self

    def order(self, key, desc=False):
        self._order = (key, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, a, b):
        self._range = (a, b)
        return self

    def execute(self):
        if hasattr(self, "_insert_rows"):
            stored = []
            for row in self._insert_rows:
                row = dict(row)
                row.setdefault("id", len(self.db.tables[self.table_name]) + 1)
                self.db.tables[self.table_name].append(row)
                stored.append(row)
            return type("R", (), {"data": stored})()
        rows = [r for r in self.db.tables[self.table_name]
                if all(f(r) for f in self._filters)]
        if self._update_payload is not None:
            for r in rows:
                r.update(self._update_payload)
            return type("R", (), {"data": [dict(r) for r in rows]})()
        if hasattr(self, "_order"):
            key, desc = self._order
            rows = sorted(rows, key=lambda r: str(r.get(key) or ""), reverse=desc)
        if hasattr(self, "_limit"):
            rows = rows[: self._limit]
        return type("R", (), {"data": [dict(r) for r in rows]})()


class FakeDB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "compass_ingest_runs": [],
            "compass_price_bars": [],
            "compass_theme_state_daily": [],
            "compass_themes": [],
            "compass_theme_memberships": [],
            "compass_recommendations": [],
            "compass_overrides": [],
            "compass_rule_changes": [],
        }

    def table(self, name):
        return _Query(self.tables[name], name, self)


def _client_with(db: FakeDB) -> TestClient:
    app.dependency_overrides[get_client] = lambda: db
    return TestClient(app)


def _seeded_db() -> FakeDB:
    db = FakeDB()
    db.tables["compass_themes"] = [
        {"slug": "ai-chips", "name": "AI chips", "etf_ticker": "SMH", "etf_is_primary": True},
    ]
    db.tables["compass_theme_state_daily"] = [
        {"d": "2026-06-11", "theme_slug": "ai-chips", "index_level": 69.07,
         "sma200": 43.3, "trend_on": True, "days_in_state": 1},
    ]
    db.tables["compass_price_bars"] = [{"ticker": "SPY", "d": "2026-06-11"}]
    db.tables["compass_recommendations"] = [
        {"id": 1, "d": "2026-06-11", "hypothesis": "none", "instrument": "-",
         "action": "none", "reasoning": {}, "base_rate": None, "acknowledged_at": None},
    ]
    return db


def test_health_reports_freshness():
    client = _client_with(_seeded_db())
    body = client.get("/v1/health").json()
    assert body["latest_price_date"] == "2026-06-11"
    assert body["latest_state_date"] == "2026-06-11"
    assert body["recent_alerts"] == []


def test_themes_join_latest_state():
    client = _client_with(_seeded_db())
    body = client.get("/v1/themes").json()
    assert body[0]["slug"] == "ai-chips"
    assert body[0]["state"]["trend_on"] is True


def test_theme_detail_404_on_unknown():
    client = _client_with(_seeded_db())
    assert client.get("/v1/themes/nope").status_code == 404


def test_recommendations_today():
    client = _client_with(_seeded_db())
    body = client.get("/v1/recommendations/today").json()
    assert body["d"] == "2026-06-11"
    assert body["recommendations"][0]["action"] == "none"


def test_override_requires_reason():
    client = _client_with(_seeded_db())
    blank = client.post("/v1/overrides", json={"what": "sold early", "reason": ""})
    assert blank.status_code == 422
    ok = client.post("/v1/overrides", json={"what": "sold early", "reason": "panicked on red day"})
    assert ok.status_code == 201
    assert ok.json()["reason"] == "panicked on red day"


def test_ack_sets_timestamp_once():
    db = _seeded_db()
    client = _client_with(db)
    first = client.post("/v1/recommendations/1/ack").json()
    assert first["acknowledged_at"] is not None
    again = client.post("/v1/recommendations/1/ack").json()
    assert again["acknowledged_at"] == db.tables["compass_recommendations"][0]["acknowledged_at"]
    assert client.post("/v1/recommendations/99/ack").status_code == 404


def test_rule_change_cooling_off_clock():
    db = _seeded_db()
    client = _client_with(db)
    res = client.post("/v1/rule-changes", json={"change": {"sma_n": 150}})
    assert res.status_code == 201
    row = res.json()
    proposed = datetime.fromisoformat(row["proposed_at"])
    effective = datetime.fromisoformat(row["effective_at"])
    assert effective - proposed >= timedelta(hours=48)
    # Not active: unapproved AND inside the cooling-off window
    listing = client.get("/v1/rule-changes").json()
    assert listing[0]["active"] is False
    # Even approved, it stays inactive until the clock elapses
    db.tables["compass_rule_changes"][0]["approved"] = True
    listing = client.get("/v1/rule-changes").json()
    assert listing[0]["active"] is False
    # Clock elapsed + approved -> active
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
    db.tables["compass_rule_changes"][0]["effective_at"] = past
    listing = client.get("/v1/rule-changes").json()
    assert listing[0]["active"] is True
