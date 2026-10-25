"""Plan checks for POST /api/validate (#30). Rules, keys and deviations: README.md here."""

from datetime import date

from api.contracts import Finding, PlanDocument
from api.validation.evacuation import validate_evacuation
from api.validation.geometry import symbol_outline
from api.validation.pochta import object_type, validate_pochta
from api.validation.safety import validate_safety


def with_type_outlines(plan: PlanDocument) -> PlanDocument:
    """pochta withTypeOutline on load: an object without an outline takes its type's shape."""
    objects = []
    for obj in plan.objects:
        kind = object_type(plan, obj.typeId)
        outline = None if kind is None else kind.outline or symbol_outline(kind.symbol)
        if obj.outline is None and outline is not None:
            obj = obj.model_copy(update={"outline": outline})
        objects.append(obj)
    return plan.model_copy(update={"objects": objects})


def validate_plan(plan: PlanDocument, today: date | None = None) -> list[Finding]:
    plan = with_type_outlines(plan)
    findings = validate_pochta(plan, today or date.today())
    if any(f.code == "POLYGON_UNUSABLE" for f in findings):
        return findings
    return [*findings, *validate_safety(plan), *validate_evacuation(plan)]
