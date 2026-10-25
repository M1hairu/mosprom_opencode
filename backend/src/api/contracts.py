"""API contract: the source of truth. web/src/contracts.ts is generated from it (make contracts).

Consumers: web/src (generated types), backend/tests. A change is a separate PR with the
contract label; the regenerated web/src/contracts.ts goes into the same PR (make lint checks it).
"""

import math
from copy import deepcopy
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_serializer,
    model_validator,
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(allow_inf_nan=False, gt=0)]
NonNegativeFloat = Annotated[float, Field(allow_inf_nan=False, ge=0)]
Id = Annotated[str, Field(min_length=1)]
Point = tuple[FiniteFloat, FiniteFloat]
Polygon = Annotated[list[Point], Field(min_length=3, max_length=256)]
AttributeValue = str | FiniteFloat | bool | None

# How far a stored outline box may miss [-0.5, 0.5] before it is refused (pochta outline.ts).
OUTLINE_SPAN_TOLERANCE = 1e-3


class Health(BaseModel):
    status: Literal["ok"]
    sha: str = Field(description="Commit of the build (GIT_SHA); unknown outside docker compose")


# --- PlanDocument v1 of pochta (src/contracts/schema.ts, commit c9991cc), the part
# POST /api/validate reads. Unknown fields are ignored; LASSARD facts without a field
# live in `attributes` and `extensions` (keys: backend/src/api/validation/README.md).


class PlanRoom(BaseModel):
    id: Id
    boundary: Polygon
    ceilingHeight_m: PositiveFloat


class PlanWall(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Id
    from_: Point = Field(alias="from")
    to: Point
    thickness_m: PositiveFloat
    height_m: PositiveFloat


class PlanOpening(BaseModel):
    id: Id
    wallId: Id
    offset_m: NonNegativeFloat = Field(description="From the wall's `from` end to the near edge")
    width_m: PositiveFloat
    kind: Literal["entrance", "door", "window"]
    sill_m: NonNegativeFloat
    height_m: PositiveFloat


class PlanLayer(BaseModel):
    id: Id
    name: str
    visible: bool
    locked: bool
    order: FiniteFloat
    typeId: Id | None = None


class PlanZone(BaseModel):
    id: Id
    typeId: Id
    name: str
    polygon: Polygon
    parentId: Id | None
    layerId: Id
    attributes: dict[str, AttributeValue]


class PlanObject(BaseModel):
    id: Id
    typeId: Id
    label: str
    position: Point = Field(description="Centre of the object")
    size_m: tuple[PositiveFloat, PositiveFloat] = Field(description="Extent before rotation")
    rotation_deg: Annotated[float, Field(allow_inf_nan=False, ge=0, lt=360)] = Field(
        description="Positive turns clockwise"
    )
    base_m: NonNegativeFloat
    height_m: PositiveFloat
    zoneId: Id | None
    layerId: Id
    attributes: dict[str, AttributeValue]
    locked: bool | None = None
    outline: Polygon | None = Field(
        default=None, description="Ring in fractions of size_m, box [-0.5, 0.5]; absent — type"
    )

    @field_validator("outline")
    @classmethod
    def outline_spans_unit_box(cls, ring: list[Point] | None) -> list[Point] | None:
        return None if ring is None else normalize_outline(ring)


class PlanAttributeDef(BaseModel):
    key: Id
    label: str
    type: Literal["string", "number", "boolean"]
    required: bool
    default: str | FiniteFloat | bool | None = None


class PlanObjectType(BaseModel):
    id: Id
    label: str
    category: str = ""
    defaultBase_m: NonNegativeFloat = 0
    physical: bool = Field(default=True, description="Takes part in collision checks")
    occupiesFloor: bool = True
    symbol: Literal["rect", "circle", "triangle"] = "rect"
    outline: Polygon | None = None
    attributes: list[PlanAttributeDef] = []

    @field_validator("outline")
    @classmethod
    def outline_spans_unit_box(cls, ring: list[Point] | None) -> list[Point] | None:
        return None if ring is None else normalize_outline(ring)


class PlanZoneType(BaseModel):
    id: Id
    label: str


class PlanCountRule(BaseModel):
    id: Id
    source: Literal["team-assumption", "organizer-material"]
    rationale: str
    kind: Literal["count"]
    zoneTypeId: Id
    objectTypeId: Id
    scope: Literal["direct", "inclusive"]
    min: Annotated[int, Field(ge=0)] | None
    max: Annotated[int, Field(ge=0)] | None


class PlanDistanceRule(BaseModel):
    id: Id
    source: Literal["team-assumption", "organizer-material"]
    rationale: str
    kind: Literal["distance-to-entrance"]
    objectTypeId: Id
    maxDistance_m: PositiveFloat
    entranceId: Id | None


class PlanCatalog(BaseModel):
    version: str
    objectTypes: Annotated[list[PlanObjectType], Field(max_length=200)]
    zoneTypes: list[PlanZoneType]
    rules: Annotated[
        list[Annotated[PlanCountRule | PlanDistanceRule, Field(discriminator="kind")]],
        Field(max_length=50),
    ] = []


# POST /api/validate is public: these caps keep one check within about 2 s (plan 219: 40
# objects, 9 walls, 9 openings, 13 zones). A larger plan gets 422.
MAX_PLAN_OBJECTS = 300
MAX_PLAN_WALLS = 200
MAX_PLAN_OPENINGS = 200
MAX_PLAN_ZONES = 100


class PlanDocument(BaseModel):
    schemaVersion: Literal[1]
    id: Id
    name: str
    room: PlanRoom
    walls: Annotated[list[PlanWall], Field(max_length=MAX_PLAN_WALLS)]
    openings: Annotated[list[PlanOpening], Field(max_length=MAX_PLAN_OPENINGS)]
    layers: Annotated[list[PlanLayer], Field(min_length=1, max_length=50)]
    zones: Annotated[list[PlanZone], Field(max_length=MAX_PLAN_ZONES)]
    objects: Annotated[list[PlanObject], Field(max_length=MAX_PLAN_OBJECTS)]
    catalog: PlanCatalog
    extensions: dict[str, object] = {}


class FindingRef(BaseModel):
    kind: Literal["room", "zone", "object", "layer", "wall", "opening"]
    id: str


class Finding(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    refs: list[FindingRef]


class ValidateResponse(BaseModel):
    findings: list[Finding]


def normalize_outline(ring: list[Point]) -> list[Point]:
    """pochta outlineFits + normalizeOutline: the box must span [-0.5, 0.5], then exactly."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    span = (lo_x, -0.5), (hi_x, 0.5), (lo_y, -0.5), (hi_y, 0.5)
    if any(abs(value - target) > OUTLINE_SPAN_TOLERANCE for value, target in span):
        raise ValueError(
            "Контур объекта задаётся в долях габарита: его рамка должна занимать ровно "
            "от −0,5 до 0,5 по обеим осям."
        )
    if (lo_x, hi_x, lo_y, hi_y) == (-0.5, 0.5, -0.5, 0.5):
        return ring

    def scale(value: float, lo: float, hi: float) -> float:
        # Six decimals rounded half up, as Math.round in pochta.
        rounded = math.floor(((value - lo) / (hi - lo) - 0.5) * 1e6 + 0.5) / 1e6
        return 0.0 if rounded == 0 else rounded

    return [(scale(x, lo_x, hi_x), scale(y, lo_y, hi_y)) for x, y in ring]


# --- Site documents (#36). Content envelopes remain exactly the content/*.json format.
# Raw JSON is stored unchanged. The typed PlanDocument is only a validation projection.


def _content_schema(name):
    def apply(schema):
        import json

        from api.content_validation import content_directory

        source = json.loads(
            (content_directory() / "schemas" / f"{name}.schema.json").read_text("utf-8")
        )
        schema.clear()
        schema.update(
            {key: value for key, value in source.items() if key not in ("$schema", "title")}
        )

    return apply


class StoredPlan(PlanDocument):
    """Validate with PlanDocument, serialize the exact input including unknown extensions."""

    _original: dict[str, Any] = PrivateAttr(default_factory=dict)

    @model_validator(mode="wrap")
    @classmethod
    def preserve_json(cls, value, handler):
        if isinstance(value, cls):
            return value
        result = handler(value)
        result._original = deepcopy(value)
        return result

    @model_serializer
    def original_json(self):
        return self._original


class SiteDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: StoredPlan
    zones: dict[str, Any] = Field(json_schema_extra=_content_schema("zones"))
    routes: dict[str, Any] = Field(json_schema_extra=_content_schema("routes"))
    facts: dict[str, Any] = Field(json_schema_extra=_content_schema("facts"))
    catalog: dict[str, Any] = Field(json_schema_extra=_content_schema("catalog"))

    @model_validator(mode="after")
    def content_shapes(self):
        from api.content_validation import document_errors

        errors = document_errors(self.model_dump(mode="json"), shapes_only=True)
        if errors:
            raise ValueError("; ".join(errors))
        PlanDocument.model_validate(self.plan)
        return self


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Annotated[int, Field(gt=0, strict=True)]


class DocumentVersion(BaseModel):
    site_id: str
    version: int
    status: Literal["draft", "published"]
    author: str
    created_at: datetime


class SiteDocumentVersion(DocumentVersion):
    body: SiteDocument
    findings: list[Finding]
