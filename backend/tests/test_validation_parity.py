"""validate_pochta repeats pochta validatePlan (commit c9991cc) finding for finding.

expected.json is pochta's own output on the plans of fixtures/parity, today = 2026-10-24.
Regenerate: README.md of src/api/validation, section «Совпадение с pochta».
"""

import json
from datetime import date
from pathlib import Path

import pytest

from api.contracts import PlanDocument
from api.validation import with_type_outlines
from api.validation.pochta import validate_pochta

PARITY = Path(__file__).parent / "fixtures" / "parity"
EXPECTED = json.loads((PARITY / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_findings_match_pochta(name):
    plan = PlanDocument.model_validate_json((PARITY / name).read_text(encoding="utf-8"))
    found = validate_pochta(with_type_outlines(plan), date(2026, 10, 24))
    assert [f.model_dump() for f in found] == EXPECTED[name]
