"""The D-001 rule (#301) on the real plans of hall 219 (#321): beam on types, live: false on items."""

import json
from collections import Counter
from pathlib import Path

from plan_builder import TODAY

from api.contracts import PlanDocument
from api.validation import validate_plan

CONTENT = Path(__file__).resolve().parents[2] / "content"
PLANS = ["plan-219", "plan-219-mirror", "plan-219-zoned", "plan-219-mirror-zoned"]
# Findings of the plans as they were before #321: only narrow passages.
EXPECTED = {
    "plan-219": {},
    "plan-219-mirror": {},
    "plan-219-zoned": {"PASSAGE_TOO_NARROW": 3},
    "plan-219-mirror-zoned": {"PASSAGE_TOO_NARROW": 4},
}
GRAVERS = ["ex_graver_compact", "ex_graver_portal", "ex_demo_graver"]


def load(name: str) -> dict:
    return json.loads((CONTENT / f"{name}.json").read_text("utf-8"))


def codes(plan: dict) -> Counter:
    found = validate_plan(PlanDocument.model_validate(plan), TODAY)
    return Counter(f.code for f in found)


def test_plan_findings_stay_the_same():
    for name in PLANS:
        assert dict(codes(load(name))) == EXPECTED[name], name


def test_graver_types_have_a_beam_and_items_stand_without_power():
    for name in ("plan-219-zoned", "plan-219-mirror-zoned"):
        plan = load(name)
        types = {t["id"]: t for t in plan["catalog"]["objectTypes"]}
        for obj in plan["objects"]:
            if obj["id"] in GRAVERS:
                assert any(a["key"] == "beam" for a in types[obj["typeId"]]["attributes"]), obj[
                    "id"
                ]
                assert obj["attributes"].get("live") is False, obj["id"]


def test_rule_sees_graver_without_live_on_real_plan():
    """Power not specified is not proven off: one finding per graver.

    A closed beam (portal, 3D) gets LIVE_PROCESS_FORBIDDEN. An open beam outside a cabin
    (compact) gets OPEN_BEAM_OUTSIDE_INTERLOCK: G5 reports that item (safety.py, `_live_process`).
    """
    wanted = {
        "ex_graver_compact": "OPEN_BEAM_OUTSIDE_INTERLOCK",
        "ex_graver_portal": "LIVE_PROCESS_FORBIDDEN",
        "ex_demo_graver": "LIVE_PROCESS_FORBIDDEN",
    }
    for name in ("plan-219-zoned", "plan-219-mirror-zoned"):
        plan = load(name)
        for obj in plan["objects"]:
            if obj["id"] in GRAVERS:
                obj["attributes"].pop("live", None)
        found = validate_plan(PlanDocument.model_validate(plan), TODAY)
        got = {r.id: f.code for f in found if f.code != "PASSAGE_TOO_NARROW" for r in f.refs}
        assert got == wanted, name
