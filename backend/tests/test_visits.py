"""Visits, guest events, SSE and analytics (#55). SQLite in memory stands for PostgreSQL."""

import asyncio
import base64
import io
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import db
from api.main import app
from api.model import Base
from api.visit_model import GuestEvent

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
SITE = "lassard-219"
T0 = datetime.now(UTC) - timedelta(hours=1)  # the server clamps times after "now"


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("MANAGER_PASSWORD", "test-manager")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", lambda: engine)
    return engine


@pytest.fixture
def client(engine):
    return TestClient(app, headers={"Authorization": "Basic bWFuYWdlcjp0ZXN0LW1hbmFnZXI="})


def new_visit(client, role="buyer") -> dict:
    response = client.post("/api/visits", json={"site_id": SITE, "role": role})
    assert response.status_code == 200
    return response.json()


def event(visit, zone="laser_sources", kind="arrive", src="qr", cid="e1", at=T0, **extra) -> dict:
    return {
        "visit_token": visit["token"],
        "kind": kind,
        "zone_id": zone,
        "src": src,
        "client_event_id": cid,
        "occurred_at": at.isoformat(),
        **extra,
    }


def count_events(engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(GuestEvent))


def test_duplicate_client_event_id_is_not_written_twice(client, engine):
    visit = new_visit(client)
    first = client.post("/api/events", json=event(visit))
    again = client.post("/api/events", json=event(visit))
    assert first.json()["duplicate"] is False
    assert again.json() == {"event_id": first.json()["event_id"], "duplicate": True}
    assert count_events(engine) == 1


def test_client_event_id_is_unique_per_visit_only(client, engine):
    a, b = new_visit(client), new_visit(client)
    assert client.post("/api/events", json=event(a)).json()["duplicate"] is False
    assert client.post("/api/events", json=event(b)).json()["duplicate"] is False
    assert count_events(engine) == 2


def test_event_with_unknown_token_is_refused(client):
    visit = {"token": "nope"}
    assert client.post("/api/events", json=event(visit)).status_code == 404


def test_arrive_needs_a_zone_and_lead_does_not(client):
    visit = new_visit(client)
    assert client.post("/api/events", json=event(visit, zone=None)).status_code == 422
    assert client.post("/api/events", json=event(visit, zone=None, kind="lead")).status_code == 200


# --- SSE. TestClient buffers a whole response, so the stream is read from the ASGI app directly.


class Stream:
    def __init__(self, path: str, login: str = "manager:test-manager"):
        self.path = path
        self.basic = base64.b64encode(login.encode())
        self.chunks: asyncio.Queue = asyncio.Queue()
        self.stop = asyncio.Event()

    async def __aenter__(self):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self.path,
            "raw_path": self.path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"authorization", b"Basic " + self.basic)],
            "server": ("test", 80),
            "client": ("test", 1),
        }

        async def receive():
            await self.stop.wait()
            return {"type": "http.disconnect"}

        self.task = asyncio.create_task(app(scope, receive, self.chunks.put))
        return self

    async def __aexit__(self, *exc):
        self.stop.set()
        await asyncio.wait_for(self.task, 5)

    async def message(self, timeout=1.0) -> dict:
        """The next `data:` line as JSON; fails after `timeout` seconds."""
        async with asyncio.timeout(timeout):
            while True:
                chunk = await self.chunks.get()
                body = chunk.get("body", b"").decode()
                for line in body.splitlines():
                    if line.startswith("data: "):
                        return json.loads(line[6:])


async def post(client, path, **kwargs):
    return await asyncio.to_thread(client.post, path, **kwargs)


def test_event_reaches_the_tablet_stream_within_a_second(client):
    visit = new_visit(client)

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/stream") as tablet:
            await asyncio.sleep(0.1)  # let the stream subscribe
            started = time.monotonic()
            await post(client, "/api/events", json=event(visit))
            seen = await tablet.message(1.0)
            return seen, time.monotonic() - started

    seen, seconds = asyncio.run(scenario())
    assert seen["type"] == "event"
    assert (seen["zone_id"], seen["kind"], seen["src"], seen["role"]) == (
        "laser_sources",
        "arrive",
        "qr",
        "buyer",
    )
    assert seconds <= 1.0


def test_scan_reaches_the_zone_screen_and_the_latest_scan_wins(client):
    first, second = new_visit(client, "buyer"), new_visit(client, "student")

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/zones/laser_sources/stream") as screen:
            start = await screen.message()
            await post(client, "/api/events", json=event(first, cid="a", at=T0))
            by_first = await screen.message()
            await post(
                client,
                "/api/events",
                json=event(second, cid="b", src="nfc", at=T0 + timedelta(seconds=30)),
            )
            by_second = await screen.message()
            # The first guest's queue resends a scan made earlier than the second scan.
            await post(
                client,
                "/api/events",
                json=event(first, cid="c", at=T0 + timedelta(seconds=10)),
            )
            with pytest.raises(TimeoutError):
                await screen.message(0.3)
            return start, by_first, by_second

    start, by_first, by_second = asyncio.run(scenario())
    assert start["visit_id"] is None
    assert (by_first["visit_id"], by_first["role"]) == (first["visit_id"], "buyer")
    assert (by_second["visit_id"], by_second["role"]) == (second["visit_id"], "student")


def test_tablet_role_change_reaches_the_screen_of_that_guest(client):
    visit = new_visit(client, "buyer")
    client.post("/api/events", json=event(visit))

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/zones/laser_sources/stream") as screen:
            assert (await screen.message())["role"] == "buyer"
            response = await asyncio.to_thread(
                client.put, f"/api/visits/{visit['visit_id']}/role", json={"role": "student"}
            )
            return response.json(), await screen.message()

    changed, seen = asyncio.run(scenario())
    assert changed == {"role": "student"}
    assert (seen["visit_id"], seen["role"]) == (visit["visit_id"], "student")


def test_visit_list_shows_role_and_last_zone(client):
    visit = new_visit(client)
    client.post("/api/events", json=event(visit, zone="robots", cid="a", at=T0))
    client.post(
        "/api/events", json=event(visit, zone="diodes", cid="b", at=T0 + timedelta(seconds=5))
    )
    (listed,) = client.get("/api/visits", params={"site_id": SITE}).json()
    assert (listed["visit_id"], listed["role"], listed["last_zone_id"]) == (
        visit["visit_id"],
        "buyer",
        "diodes",
    )


# --- Analytics


def test_analytics_time_in_zones_and_funnel(client):
    buyer, student, passer = new_visit(client), new_visit(client), new_visit(client)
    steps = [
        (buyer, "robots", "arrive", 0),
        (buyer, "diodes", "arrive", 60),
        (buyer, "diodes", "leave", 90),
        (buyer, None, "lead", 100),
        (student, "robots", "arrive", 0),
        (student, "robots", "leave", 30),
        (passer, "robots", "arrive", 5),  # no end: not a stay
    ]
    for number, (visit, zone, kind, second) in enumerate(steps):
        at = T0 + timedelta(seconds=second)
        body = event(visit, zone=zone, kind=kind, cid=f"e{number}", at=at)
        assert client.post("/api/events", json=body).status_code == 200

    result = client.get("/api/analytics", params={"site_id": SITE}).json()
    assert result["zones"] == [
        {"zone_id": "robots", "visits": 2, "seconds_total": 90, "seconds_avg": 45},
        {"zone_id": "diodes", "visits": 1, "seconds_total": 30, "seconds_avg": 30},
    ]
    assert result["funnel"] == [
        {"step": "visit", "visits": 3},
        {"step": "zone", "visits": 3},
        {"step": "lead", "visits": 1},
    ]


def test_analytics_of_an_empty_site(client):
    result = client.get("/api/analytics", params={"site_id": "nothing"}).json()
    assert result["zones"] == []
    assert [step["visits"] for step in result["funnel"]] == [0, 0, 0]


def test_migrations_create_the_visit_tables(monkeypatch):
    out = io.StringIO()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    command.upgrade(Config(toml_file=PYPROJECT, output_buffer=out), "head", sql=True)
    for table in ("visits", "guest_events", "zone_screens"):
        assert f"CREATE TABLE {table}" in out.getvalue()


def test_scan_from_the_future_does_not_lock_the_screen(client):
    liar, guest = new_visit(client), new_visit(client)
    far = datetime(2099, 1, 1, tzinfo=UTC)
    client.post("/api/events", json=event(liar, cid="a", at=far))
    client.post("/api/events", json=event(guest, cid="b", at=datetime.now(UTC)))

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/zones/laser_sources/stream") as screen:
            return await screen.message()

    assert asyncio.run(scenario())["visit_id"] == guest["visit_id"]


# --- The tablet leads a guest (#132): POST /api/visits/{visit_id}/events, manager role, src manual.


def manual(zone="laser_sources", kind="arrive", cid="m1", at=None) -> dict:
    return {
        "kind": kind,
        "zone_id": zone,
        "src": "manual",
        "client_event_id": cid,
        "occurred_at": (at or datetime.now(UTC)).isoformat(),
    }


def test_tablet_moves_a_guest_and_the_zone_screen_changes(client, engine):
    guest = new_visit(client, "student")

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/zones/laser_sources/stream") as screen:
            assert (await screen.message())["visit_id"] is None
            started = time.monotonic()
            response = await post(client, f"/api/visits/{guest['visit_id']}/events", json=manual())
            return response, await screen.message(1.0), time.monotonic() - started

    response, seen, seconds = asyncio.run(scenario())
    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    assert (seen["visit_id"], seen["role"]) == (guest["visit_id"], "student")
    assert seconds <= 1.0
    with Session(engine) as session:
        (row,) = session.scalars(select(GuestEvent)).all()
    assert (row.visit_id, row.zone_id, row.kind, row.src) == (
        guest["visit_id"],
        "laser_sources",
        "arrive",
        "manual",
    )


def test_tablet_event_reaches_the_tablet_stream(client):
    guest = new_visit(client)

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/stream") as tablet:
            await asyncio.sleep(0.1)  # let the stream subscribe
            await post(client, f"/api/visits/{guest['visit_id']}/events", json=manual())
            return await tablet.message(1.0)

    seen = asyncio.run(scenario())
    assert (seen["type"], seen["visit_id"], seen["src"], seen["kind"]) == (
        "event",
        guest["visit_id"],
        "manual",
        "arrive",
    )


def test_tablet_repeat_of_one_client_event_id_is_not_written_twice(client, engine):
    guest = new_visit(client)
    path = f"/api/visits/{guest['visit_id']}/events"
    first = client.post(path, json=manual())
    again = client.post(path, json=manual())
    assert again.json() == {"event_id": first.json()["event_id"], "duplicate": True}
    assert count_events(engine) == 1


def test_tablet_event_needs_the_manager(engine):
    anonymous = TestClient(app)
    guest = new_visit(anonymous)
    path = f"/api/visits/{guest['visit_id']}/events"
    assert anonymous.post(path, json=manual()).status_code == 401
    wrong = TestClient(app, headers={"Authorization": "Basic bWFuYWdlcjpub3Bl"})  # manager:nope
    assert wrong.post(path, json=manual()).status_code == 401
    assert count_events(engine) == 0


def test_tablet_event_is_refused_to_the_editor_and_the_expert(engine, monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", "test-editor")
    monkeypatch.setenv("EXPERT_PASSWORD", "test-expert")
    guest = new_visit(TestClient(app))
    path = f"/api/visits/{guest['visit_id']}/events"
    for login in ("editor", "expert"):
        basic = base64.b64encode(f"{login}:test-{login}".encode()).decode()
        other = TestClient(app, headers={"Authorization": f"Basic {basic}"})
        assert other.post(path, json=manual(cid=login)).status_code == 403
    assert count_events(engine) == 0


# --- The expert reads the visit list and the site stream, writes nothing (#132, lead decision 6).


def staff(login: str) -> TestClient:
    basic = base64.b64encode(f"{login}:test-{login}".encode()).decode()
    return TestClient(app, headers={"Authorization": f"Basic {basic}"})


@pytest.fixture
def staff_env(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", "test-editor")
    monkeypatch.setenv("EXPERT_PASSWORD", "test-expert")


def test_expert_reads_the_visit_list_and_the_editor_does_not(client, staff_env):
    visit = new_visit(client)
    seen = staff("expert").get("/api/visits", params={"site_id": SITE})
    assert seen.status_code == 200
    assert [row["visit_id"] for row in seen.json()] == [visit["visit_id"]]
    assert client.get("/api/visits", params={"site_id": SITE}).status_code == 200
    editor = staff("editor").get("/api/visits", params={"site_id": SITE})
    assert editor.status_code == 403
    assert TestClient(app).get("/api/visits", params={"site_id": SITE}).status_code == 401


def test_expert_reads_the_site_stream_and_the_editor_does_not(client, staff_env):
    visit = new_visit(client)

    async def scenario():
        async with Stream(f"/api/sites/{SITE}/stream", "expert:test-expert") as expert:
            await asyncio.sleep(0.1)
            await post(client, "/api/events", json=event(visit))
            return await expert.message(1.0)

    assert asyncio.run(scenario())["type"] == "event"
    assert staff("editor").get(f"/api/sites/{SITE}/stream").status_code == 403
    assert TestClient(app).get(f"/api/sites/{SITE}/stream").status_code == 401


def test_expert_cannot_write_visits(client, engine, staff_env):
    guest = new_visit(client)
    expert = staff("expert")
    role = expert.put(f"/api/visits/{guest['visit_id']}/role", json={"role": "student"})
    assert role.status_code == 403
    manual_path = f"/api/visits/{guest['visit_id']}/events"
    assert expert.post(manual_path, json=manual()).status_code == 403
    assert count_events(engine) == 0
    (listed,) = client.get("/api/visits", params={"site_id": SITE}).json()
    assert listed["role"] == "buyer"


def test_tablet_event_for_an_unknown_visit_is_404(client):
    assert client.post("/api/visits/nope/events", json=manual()).status_code == 404


def test_tablet_event_accepts_only_src_manual_and_needs_a_zone(client):
    guest = new_visit(client)
    path = f"/api/visits/{guest['visit_id']}/events"
    assert client.post(path, json={**manual(), "src": "qr"}).status_code == 422
    assert client.post(path, json=manual(zone=None)).status_code == 422
