"""POST /api/validate: a plan in, findings in the shape of web/src/planner/model.ts out."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from plan_builder import hall, item

from api.contracts import MAX_PLAN_OBJECTS
from api.main import app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_plan_219_validates_without_findings():
    plan = json.loads((ROOT / "content" / "plan-219.json").read_text("utf-8"))
    response = client.post("/api/validate", json=plan)
    assert response.status_code == 200
    assert response.json() == {"findings": []}


def test_violation_comes_back_as_finding():
    plan = hall(20, 10, exits=[("south", 2, 1.2), ("north", 9, 1.2)])
    plan["objects"].append(item("hand", (5, 5), (1, 1), "ot_cleaner", beam="open"))
    findings = client.post("/api/validate", json=plan).json()["findings"]
    assert [(f["code"], f["severity"], f["refs"]) for f in findings] == [
        ("OPEN_BEAM_OUTSIDE_INTERLOCK", "error", [{"kind": "object", "id": "hand"}])
    ]


def test_plan_without_room_is_refused():
    plan = hall(20, 10)
    del plan["room"]
    assert client.post("/api/validate", json=plan).status_code == 422


def test_plan_over_object_cap_is_refused():
    plan = hall(20, 10)
    plan["objects"] = [item(f"o{i}", (1, 1), (0.1, 0.1)) for i in range(MAX_PLAN_OBJECTS + 1)]
    assert client.post("/api/validate", json=plan).status_code == 422
