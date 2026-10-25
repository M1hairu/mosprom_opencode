"""Scenario checks for make eval / make eval-final (scripts/eval_harness.py).

check_<scenario id>(case) -> bool | (bool, note). A scenario without a check is "not automated".
metric(split) -> {"name", "system", "baseline"} or None.
"""

import copy
import json
from datetime import date
from pathlib import Path

from api.contracts import PlanDocument
from api.validation import validate_plan

ROOT = Path(__file__).resolve().parents[3]
NORM_CASES = ROOT / "eval" / "cases-norms.json"
# The date only moves maintenance warnings; the norm cases have no maintenance dates.
TODAY = date(2026, 10, 24)
OBJECT_DEFAULTS = {
    "rotation_deg": 0,
    "base_m": 0,
    "height_m": 1.5,
    "zoneId": None,
    "layerId": "l_exhibits",
    "attributes": {},
}


def norm_plan(suite: dict, case: dict) -> PlanDocument:
    """Base plan + common layer of the suite + the case: remove by id, then add."""
    plan = json.loads((ROOT / suite["base"]).read_text(encoding="utf-8"))
    common = suite["common"]
    plan["layers"] += common["layers"]
    plan["catalog"]["objectTypes"] += common["objectTypes"]
    plan["catalog"]["zoneTypes"] += common["zoneTypes"]
    for key in ("walls", "openings", "zones"):
        plan[key] += copy.deepcopy(common[key])
    removed = set(case.get("remove", []))
    for key in ("walls", "openings", "zones", "objects"):
        plan[key] = [item for item in plan[key] if item["id"] not in removed]
    added = case.get("add", {})
    plan["walls"] += added.get("walls", [])
    plan["openings"] += added.get("openings", [])
    plan["objects"] += [
        {**OBJECT_DEFAULTS, "label": obj["id"], **obj} for obj in added.get("objects", [])
    ]
    plan["extensions"].update(case.get("extensions", {}))
    return PlanDocument.model_validate(plan)


def norm_results() -> list[tuple[dict, list[str]]]:
    suite = json.loads(NORM_CASES.read_text(encoding="utf-8"))
    return [
        (case, [f.code for f in validate_plan(norm_plan(suite, case), TODAY)])
        for case in suite["cases"]
    ]


def norm_rates() -> tuple[float, float]:
    """eval (a), D-012: % of violating plans caught, % of clean plans with a finding."""
    results = norm_results()
    violating = [(case, codes) for case, codes in results if case["expect"]]
    clean = [codes for case, codes in results if not case["expect"]]
    caught = sum(set(case["expect"]) <= set(codes) for case, codes in violating)
    false = sum(bool(codes) for codes in clean)
    return 100 * caught / len(violating), 100 * false / len(clean)


def metric(split: str) -> dict | None:
    # The holdout is not passed to metric(): eval (a) runs on the visible cases only.
    # TODO(#37): eval (b) substituted numbers.
    if split != "visible":
        return None
    caught, false = norm_rates()
    return {
        "name": f"(а) пойманные планы с нарушениями норм, % (ложные на чистых планах: {false:.0f} %), кейсы автора правил",
        "system": round(caught),
        "baseline": 0,
    }
