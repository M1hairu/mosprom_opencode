"""Versioned site documents: public reads, validated publication and role checks (#36)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import db
from api.main import app
from api.model import Base

ROOT = Path(__file__).resolve().parents[2]
URL = "/api/sites/hall-219"


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", lambda: engine)
    for role in ("editor", "manager", "expert"):
        monkeypatch.setenv(f"{role.upper()}_PASSWORD", f"test-{role}")
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    return TestClient(app)


def credentials(role="editor"):
    return (role, f"test-{role}")


@pytest.fixture
def document():
    # The base hall has no norm findings. Content files keep their original envelopes.
    body = {
        key: json.loads((ROOT / "content" / name).read_text("utf-8"))
        for key, name in (
            ("plan", "plan-219.json"),
            ("facts", "facts.json"),
            ("catalog", "catalog.json"),
            ("zones", "zones.json"),
            ("routes", "routes.json"),
        )
    }
    zoned = json.loads((ROOT / "content/plan-219-zoned.json").read_text("utf-8"))
    body["plan"]["catalog"] = zoned["catalog"]
    return body


def save(client, document):
    response = client.put(f"{URL}/draft", json=document, auth=credentials())
    assert response.status_code == 200, response.text
    return response.json()


def publish(client, version):
    return client.post(f"{URL}/publish", json={"version": version}, auth=credentials())


def test_unpublished_document_is_not_public(client, document):
    draft = save(client, document)
    assert draft["status"] == "draft"
    assert client.get(f"{URL}/document").status_code == 404
    assert client.get(f"{URL}/draft", auth=credentials()).json() == draft


def test_publish_creates_new_immutable_version_and_preserves_extensions(client, document):
    document["plan"]["extensions"]["future"] = {"key": [1, "keep"]}
    document["plan"]["room"]["futureRoom"] = "keep me"
    document["plan"]["catalog"]["objectTypes"][0]["outline"] = [
        [-0.50001, -0.5],
        [0.5, -0.5],
        [0.5, 0.5],
        [-0.50001, 0.5],
    ]
    draft = save(client, document)
    response = publish(client, draft["version"])
    assert response.status_code == 200, response.text
    published = response.json()
    assert published["version"] > draft["version"]
    assert published["status"] == "published"
    assert published["body"] == document
    assert client.get(f"{URL}/document").json() == published
    assert client.get(f"{URL}/versions", auth=credentials("expert")).json()[1] == {
        k: v for k, v in draft.items() if k not in ("body", "findings")
    }
    changed = copy.deepcopy(document)
    changed["plan"]["name"] = "Новый черновик"
    save(client, changed)
    assert client.get(f"{URL}/document").json() == published


def test_zoned_arrangement_of_the_planner_saves_without_content_errors(client, document):
    # /planner (#277) puts the concept plan with zones and exhibits into the draft.
    document["plan"] = json.loads((ROOT / "content/plan-219-zoned.json").read_text("utf-8"))
    draft = save(client, document)
    assert [f for f in draft["findings"] if f["code"] == "CONTENT_INVALID"] == []
    stored = client.get(f"{URL}/draft", auth=credentials()).json()["body"]["plan"]
    assert stored == document["plan"]


def test_norm_errors_save_as_draft_but_block_publication(client, document):
    document["plan"]["openings"] = []
    draft = save(client, document)
    assert any(f["code"] == "EXITS_TOO_FEW" for f in draft["findings"])
    response = publish(client, draft["version"])
    assert response.status_code == 422
    assert any(f["code"] == "EXITS_TOO_FEW" for f in response.json()["detail"]["findings"])
    assert client.get(f"{URL}/document").status_code == 404


@pytest.mark.parametrize("gate", ["G1", "G2", "G3", "G14"])
def test_content_gates_block_publication(client, document, gate):
    if gate == "G1":
        document["zones"]["zones"][0]["messages"].append("Станков 42")
    elif gate == "G2":
        document["zones"]["zones"][0]["name"] = "Лассард"
    elif gate == "G3":
        document["zones"]["zones"][0]["messages"].append("Самый лучший производитель")
    else:
        document["facts"]["facts"].append(
            {
                "id": "unsafe",
                "value": 80,
                "unit": "%",
                "text": "80 %",
                "case": {"slide": 3, "value": "80 %"},
            }
        )
    draft = save(client, document)
    response = publish(client, draft["version"])
    assert response.status_code == 422
    assert any(gate in f["message"] for f in response.json()["detail"]["findings"])


def test_malformed_shape_is_rejected_instead_of_silently_dropped(client, document):
    document["facts"]["unknown"] = True
    assert client.put(f"{URL}/draft", json=document, auth=credentials()).status_code == 422
    del document["facts"]["unknown"]
    document["plan"]["objects"][0]["position"] = [True, 2]
    assert client.put(f"{URL}/draft", json=document, auth=credentials()).status_code == 422


@pytest.mark.parametrize("role", ["expert", "manager"])
@pytest.mark.parametrize("operation", ["draft", "publish", "rollback"])
def test_read_only_roles_cannot_change_documents(client, document, role, operation):
    saved = save(client, document)
    method = client.put if operation == "draft" else client.post
    payload = document if operation == "draft" else {"version": saved["version"]}
    assert method(f"{URL}/{operation}", json=payload, auth=credentials(role)).status_code == 403


def test_missing_or_bad_credentials_are_denied(client, document, monkeypatch):
    assert client.put(f"{URL}/draft", json=document).status_code == 401
    assert client.get("/api/auth/me", auth=("editor", "wrong")).status_code == 401
    monkeypatch.delenv("EDITOR_PASSWORD")
    assert client.get("/api/auth/me", auth=("editor", "")).status_code == 401
    assert client.get("/api/auth/me", auth=credentials("expert")).json() == {"role": "expert"}


def test_rollback_is_a_new_version_and_never_bypasses_validation(client, document):
    first = save(client, document)
    original = publish(client, first["version"]).json()
    changed = copy.deepcopy(document)
    changed["plan"]["name"] = "Новая версия"
    second = save(client, changed)
    publish(client, second["version"])
    rollback = client.post(
        f"{URL}/rollback", json={"version": original["version"]}, auth=credentials()
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["version"] > second["version"]
    assert rollback.json()["body"] == document
    broken = copy.deepcopy(document)
    broken["plan"]["openings"] = []
    draft = save(client, broken)
    assert (
        client.post(
            f"{URL}/rollback", json={"version": draft["version"]}, auth=credentials()
        ).status_code
        == 422
    )


def test_seed_is_idempotent_and_never_overwrites_editor_changes(client, engine, document, tmp_path):
    from api.seed import seed
    from api.site_model import SiteDocumentRow

    for key, value in document.items():
        name = "plan-219.json" if key == "plan" else f"{key}.json"
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    with Session(engine) as session:
        first, created = seed(session, tmp_path)
        assert created and first.status == "published"
        again, created = seed(session, tmp_path)
        assert not created and again.version == first.version
    edited = copy.deepcopy(document)
    edited["plan"]["name"] = "Правка редактора"
    draft = save(client, edited)
    publish(client, draft["version"])
    with Session(engine) as session:
        _, created = seed(session, tmp_path)
        assert not created
        assert len(list(session.scalars(select(SiteDocumentRow)))) == 3
    assert client.get(f"{URL}/document").json()["body"] == edited
    document["plan"]["openings"] = []
    (tmp_path / "plan-219.json").write_text(json.dumps(document["plan"]), encoding="utf-8")
    with Session(engine) as session:
        unsafe, created = seed(session, tmp_path)
        assert created and unsafe.status == "draft"
    assert client.get(f"{URL}/document").json()["body"] == edited


def test_seed_publishes_bundled_content_once(client, engine):
    # #131: catalog.json is shared by all content plans; the base hall alone lacks its types.
    from api.seed import seed

    with Session(engine) as session:
        first, created = seed(session, ROOT / "content")
        assert created and first.status == "published"
        again, created = seed(session, ROOT / "content")
        assert not created and again.version == first.version
    response = client.get(f"{URL}/document")
    assert response.status_code == 200, response.text
    assert response.json()["findings"] == []


def test_seed_publishes_valid_content_after_draft_only_history(engine, document, tmp_path):
    from api.seed import seed

    for key, value in document.items():
        name = "plan-219.json" if key == "plan" else f"{key}.json"
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    broken = copy.deepcopy(document["plan"])
    broken["openings"] = []
    (tmp_path / "plan-219.json").write_text(json.dumps(broken), encoding="utf-8")
    with Session(engine) as session:
        draft, _ = seed(session, tmp_path)
        assert draft.status == "draft"
    (tmp_path / "plan-219.json").write_text(json.dumps(document["plan"]), encoding="utf-8")
    with Session(engine) as session:
        fixed, created = seed(session, tmp_path)
        assert created and fixed.status == "published"


def test_manager_endpoints_enforce_server_role(client):
    visit = client.post("/api/visits", json={"site_id": "hall-219", "role": "buyer"}).json()
    for path in ("/api/visits?site_id=hall-219", f"{URL}/stream"):
        assert client.get(path).status_code == 401
        assert client.get(path, auth=credentials("editor")).status_code == 403
    assert client.get("/api/visits?site_id=hall-219", auth=credentials("expert")).status_code == 200
    path = f"/api/visits/{visit['visit_id']}/role"
    assert client.put(path, json={"role": "student"}, auth=credentials("expert")).status_code == 403
    assert (
        client.put(path, json={"role": "student"}, auth=credentials("manager")).status_code == 200
    )


def test_warnings_are_returned_but_do_not_block_publication(client, document):
    plan = document["plan"]
    zone_type = plan["catalog"]["zoneTypes"][0]["id"]
    plan["zones"] = [
        {
            "id": "entrance",
            "typeId": zone_type,
            "name": "Вход",
            "polygon": [[1, 1], [4, 1], [4, 4], [1, 4]],
            "parentId": None,
            "layerId": plan["layers"][0]["id"],
            "attributes": {},
        }
    ]
    plan["catalog"]["rules"] = [
        {
            "id": "stand_count",
            "source": "team-assumption",
            "rationale": "Проверка предупреждения",
            "kind": "count",
            "zoneTypeId": zone_type,
            "objectTypeId": "ot_smart_base",
            "scope": "direct",
            "min": 1,
            "max": None,
        }
    ]
    draft = save(client, document)
    response = publish(client, draft["version"])
    assert response.status_code == 200, response.text
    assert response.json()["findings"]
    assert all(f["severity"] == "warning" for f in response.json()["findings"])


def test_concurrent_write_conflict_returns_409_without_partial_version(
    client, document, monkeypatch
):
    from sqlalchemy.exc import IntegrityError

    from api import site_documents

    def conflict(*args):
        raise IntegrityError("insert", {}, RuntimeError("duplicate version"))

    monkeypatch.setattr(site_documents, "append_version", conflict)
    response = client.put(f"{URL}/draft", json=document, auth=credentials())
    assert response.status_code == 409
    assert client.get(f"{URL}/versions", auth=credentials()).json() == []


def test_version_from_another_site_is_not_published(client, document):
    draft = save(client, document)
    response = client.post(
        "/api/sites/another-site/publish", json={"version": draft["version"]}, auth=credentials()
    )
    assert response.status_code == 404
    assert client.get(f"{URL}/document").status_code == 404


def test_missing_password_never_authenticates_empty_password(client, monkeypatch):
    monkeypatch.setenv("EXPERT_PASSWORD", "")
    response = client.get("/api/auth/me", auth=("expert", ""))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


@pytest.mark.parametrize(
    "surface", ["name", "object", "zone", "layer", "object_type", "zone_type", "attribute"]
)
def test_visible_plan_texts_cannot_bypass_brand_gates(client, document, surface):
    plan = document["plan"]
    text = "Лассард — лучший производитель"
    if surface == "name":
        plan["name"] = text
    elif surface == "object":
        plan["objects"][0]["label"] = "100 % локализации"
    elif surface == "zone":
        zoned = json.loads((ROOT / "content/plan-219-zoned.json").read_text("utf-8"))
        plan["zones"] = [zoned["zones"][0]]
        plan["zones"][0]["name"] = text
    elif surface == "layer":
        plan["layers"][0]["name"] = text
    elif surface == "object_type":
        plan["catalog"]["objectTypes"][0]["label"] = text
    elif surface == "zone_type":
        plan["catalog"]["zoneTypes"][0]["label"] = text
    else:
        plan["catalog"]["objectTypes"][0]["attributes"] = [
            {
                "key": "test",
                "label": text,
                "type": "string",
                "required": False,
            }
        ]
    saved = save(client, document)
    response = publish(client, saved["version"])
    assert response.status_code == 422, response.text
    gate = "G3" if surface == "object" else "G2"
    assert any(gate in f["message"] for f in response.json()["detail"]["findings"])


def test_plan_metadata_and_identifiers_are_not_visitor_text(client, document):
    plan = document["plan"]
    plan["id"] = "Лассард — лучший производитель"
    plan["extensions"]["source"] = {
        "url": "https://example.test/Лассард",
        "provenance": "100 % из исходного документа",
    }
    saved = save(client, document)
    assert publish(client, saved["version"]).status_code == 200
