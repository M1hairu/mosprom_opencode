"""Leads: consent, forbidden material, protocol, CSV roles and webhook (#31). No real PD."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import db
from api.main import app
from api.model import Base, Site
from api.visit_model import GuestEvent, Visit

URL = "/api/sites/hall-219"
LEAD = {
    "name": "Тест Тестов",
    "phone": "+70000000000",
    "company": "ООО Тест",
    "material": "сталь",
    "task": "резка",
    "consent_pd": True,
    "consent_version": "2026-10",
}
PROTOCOL = {
    "material": "сталь",
    "thickness_mm": 2,
    "machine": "SMART",
    "mode": "оценка",
    "time_min": 3.5,
}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Site(id="hall-219", name="hall"), Site(id="other", name="other")])
        session.commit()
    monkeypatch.setattr(db, "engine", lambda: engine)
    monkeypatch.delenv("LEADS_WEBHOOK_URL", raising=False)
    for role in ("editor", "manager", "expert"):
        monkeypatch.setenv(f"{role.upper()}_PASSWORD", f"test-{role}")
    test_client = TestClient(app)
    test_client.engine = engine
    yield test_client
    engine.dispose()


def auth(role):
    return (role, f"test-{role}")


def code(response):
    return response.json()["detail"]["code"]


@pytest.mark.parametrize("material", ["ПВХ", "лист с пвх-покрытием", "PVC film"])
def test_forbidden_material_rejected(client, material):
    response = client.post(f"{URL}/leads", json={**LEAD, "material": material})
    assert response.status_code == 422
    assert code(response) == "REJ_MATERIAL_FORBIDDEN"
    assert client.get(f"{URL}/leads", auth=auth("manager")).json() == []


def test_no_consent_rejected(client):
    response = client.post(f"{URL}/leads", json={**LEAD, "consent_pd": False})
    assert response.status_code == 422
    assert code(response) == "REJ_CONSENT_REQUIRED"
    missing = {k: v for k, v in LEAD.items() if k != "consent_pd"}
    assert client.post(f"{URL}/leads", json=missing).status_code == 422


def test_protocol_and_export_roles(client):
    lead_id = client.post(f"{URL}/leads", json=LEAD).json()["id"]
    path = f"{URL}/leads/{lead_id}/protocol"
    assert client.put(path, json=PROTOCOL).status_code == 401
    assert client.put(path, json=PROTOCOL, auth=auth("editor")).status_code == 403
    filled = client.put(path, json=PROTOCOL, auth=auth("manager"))
    assert filled.json()["protocol"]["mode"] == "оценка"

    assert client.get(f"{URL}/leads").status_code == 401
    assert client.get(f"{URL}/leads", auth=auth("expert")).status_code == 403
    assert client.get(f"{URL}/leads.csv", auth=auth("expert")).status_code == 403
    for role in ("editor", "manager"):
        assert len(client.get(f"{URL}/leads", auth=auth(role)).json()) == 1
        text = client.get(f"{URL}/leads.csv", auth=auth(role)).text
        assert "Тест Тестов" in text and "SMART" in text
        assert "2026-10" in text and "+70000000000" in text and "'+7" not in text


@pytest.mark.parametrize("phone", ["=1+1", "abc", "+7 (000) 000-00-00 x", "-----", "+(  )"])
def test_bad_phone_rejected(client, phone):
    assert client.post(f"{URL}/leads", json={**LEAD, "phone": phone}).status_code == 422


def test_consent_version_required(client):
    body = {k: v for k, v in LEAD.items() if k != "consent_version"}
    assert client.post(f"{URL}/leads", json=body).status_code == 422


def test_unknown_site_404_no_site_row(client):
    assert client.post("/api/sites/nowhere/leads", json=LEAD).status_code == 404
    with Session(client.engine) as session:
        assert session.get(Site, "nowhere") is None


def test_protocol_forbidden_material_rejected(client):
    lead_id = client.post(f"{URL}/leads", json=LEAD).json()["id"]
    response = client.put(
        f"{URL}/leads/{lead_id}/protocol",
        json={**PROTOCOL, "material": "ПВХ"},
        auth=auth("manager"),
    )
    assert code(response) == "REJ_MATERIAL_FORBIDDEN"


def test_other_site_is_404(client):
    lead_id = client.post(f"{URL}/leads", json=LEAD).json()["id"]
    path = f"/api/sites/other/leads/{lead_id}"
    assert client.put(f"{path}/protocol", json=PROTOCOL, auth=auth("manager")).status_code == 404
    assert client.get(f"{path}/report", auth=auth("manager")).status_code == 404
    assert client.get("/api/sites/other/leads", auth=auth("manager")).json() == []


def test_visit_id_writes_lead_event(client):
    with Session(client.engine) as session:
        session.add(Visit(id="v1", token="t1", site_id="hall-219", role="other"))
        session.commit()
    client.post(f"{URL}/leads", json={**LEAD, "visit_id": "v1"})
    client.post(f"{URL}/leads", json={**LEAD, "visit_id": "unknown"})
    with Session(client.engine) as session:
        events = session.query(GuestEvent).all()
    assert [(e.visit_id, e.kind) for e in events] == [("v1", "lead")]


def test_report_html(client):
    lead_id = client.post(f"{URL}/leads", json=LEAD).json()["id"]
    path = f"{URL}/leads/{lead_id}/report"
    assert client.get(path).status_code == 401
    assert client.get(path, auth=auth("editor")).status_code == 403
    assert client.get(path, auth=auth("manager")).status_code == 409
    client.put(f"{path[:-7]}/protocol", json=PROTOCOL, auth=auth("manager"))
    response = client.get(path, auth=auth("manager"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert "@media print" in page and "size: A4" in page and "#DD191C" in page
    assert "ЛАССАРД" in page and "SMART" in page and "3,5" in page and "100 %" not in page


def test_csv_blocks_formula(client):
    client.post(f"{URL}/leads", json={**LEAD, "task": "=1+1"})
    text = client.get(f"{URL}/leads.csv", auth=auth("manager")).text
    assert "'=1+1" in text
    client.post(f"{URL}/leads", json={**LEAD, "task": "	cmd"})
    assert "'\tcmd" in client.get(f"{URL}/leads.csv", auth=auth("manager")).text


def test_webhook_received(client, monkeypatch):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LEADS_WEBHOOK_URL", f"http://127.0.0.1:{server.server_port}/hook")
    try:
        lead_id = client.post(f"{URL}/leads", json=LEAD).json()["id"]
    finally:
        server.shutdown()
    assert received == [{"event": "lead", "site_id": "hall-219", "lead_id": lead_id}]


def test_webhook_failure_keeps_lead(client, monkeypatch, caplog):
    monkeypatch.setenv("LEADS_WEBHOOK_URL", "http://127.0.0.1:9/hook")
    with caplog.at_level(logging.ERROR, logger="leads"):
        response = client.post(f"{URL}/leads", json=LEAD)
    assert response.status_code == 201
    assert "Webhook заявки не доставлен" in caplog.text
    assert len(client.get(f"{URL}/leads", auth=auth("manager")).json()) == 1


def test_report_escapes_html_and_formats_numbers(client):
    lead_id = client.post(f"{URL}/leads", json={**LEAD, "company": "<script>x</script>"}).json()[
        "id"
    ]
    path = f"{URL}/leads/{lead_id}"
    client.put(f"{path}/protocol", json={**PROTOCOL, "thickness_mm": 2.5}, auth=auth("manager"))
    response = client.get(f"{path}/report", auth=auth("manager"))
    assert "<script>" not in response.text and "&lt;script&gt;" in response.text
    assert "<td>2,5</td>" in response.text
    assert response.headers["cache-control"] == "no-store"
    client.put(f"{path}/protocol", json=PROTOCOL, auth=auth("manager"))
    assert "<td>2</td>" in client.get(f"{path}/report", auth=auth("manager")).text


def test_csv_blocks_tab_and_cr(client):
    for task in ("\tcmd", "\rcmd"):
        client.post(f"{URL}/leads", json={**LEAD, "task": task})
    text = client.get(f"{URL}/leads.csv", auth=auth("manager")).text
    assert "'\tcmd" in text
    assert "'\rcmd" in text
