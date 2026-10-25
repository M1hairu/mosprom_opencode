"""Small PlanDocument v1 plans for the rule tests: a rectangular hall with walls on its outline."""

from datetime import date

from api.contracts import PlanDocument
from api.validation import validate_plan

TODAY = date(2026, 10, 24)
THICKNESS = 0.2


def _type(type_id: str, label: str, category: str, **extra) -> dict:
    return {"id": type_id, "label": label, "category": category, **extra}


CATALOG = {
    "version": "test",
    "objectTypes": [
        _type("ot_stand", "Стенд", "furniture"),
        _type("ot_cleaner", "Лазерная чистка", "cleaning"),
        _type("ot_engraver", "Гравёр", "engraving"),
        _type(
            "ot_cutter",
            "Станок резки",
            "cutting",
            attributes=[
                {
                    "key": "beam",
                    "label": "Луч",
                    "type": "string",
                    "required": False,
                    "default": "closed",
                }
            ],
        ),
    ],
    "zoneTypes": [{"id": "zt_area", "label": "Зона"}],
    "rules": [],
}


def hall(width: float, depth: float, exits=(), capacity: float | None = None) -> dict:
    """A width × depth hall. An exit is (wall, offset_m, width_m); walls: south, east, north, west."""
    corners = [(0, 0), (width, 0), (width, depth), (0, depth)]
    names = ["south", "east", "north", "west"]
    walls = [wall(f"w_{name}", corners[i], corners[(i + 1) % 4]) for i, name in enumerate(names)]
    plan = {
        "schemaVersion": 1,
        "id": "plan_test",
        "name": "Тестовый зал",
        "room": {"id": "room", "boundary": corners, "ceilingHeight_m": 4},
        "walls": walls,
        "openings": [],
        "layers": [
            {"id": "l_base", "name": "Основной", "visible": True, "locked": False, "order": 0}
        ],
        "zones": [area("z_hall", 0, 0, width, depth, parent=None)],
        "objects": [],
        "catalog": CATALOG,
        "extensions": {} if capacity is None else {"safety": {"capacity": capacity}},
    }
    for index, (side, offset, size) in enumerate(exits):
        plan["openings"].append(door(f"op_{index + 1}", f"w_{side}", offset, size))
    return plan


def wall(wall_id: str, start, end, thickness: float = THICKNESS) -> dict:
    return {"id": wall_id, "from": start, "to": end, "thickness_m": thickness, "height_m": 4}


def door(opening_id: str, wall_id: str, offset: float, size: float, kind: str = "door") -> dict:
    return {
        "id": opening_id,
        "wallId": wall_id,
        "offset_m": offset,
        "width_m": size,
        "kind": kind,
        "sill_m": 0,
        "height_m": 2.1,
    }


def item(obj_id: str, position, size, type_id: str = "ot_stand", **attributes) -> dict:
    return {
        "id": obj_id,
        "typeId": type_id,
        "label": obj_id,
        "position": position,
        "size_m": size,
        "rotation_deg": 0,
        "base_m": 0,
        "height_m": 1.5,
        "zoneId": None,
        "layerId": "l_base",
        "attributes": attributes,
    }


def area(zone_id: str, x0, y0, x1, y1, parent: str | None = "z_hall", **attributes) -> dict:
    """A rectangular zone; by default nested in the hall zone, so objects stay unambiguous."""
    return {
        "id": zone_id,
        "typeId": "zt_area",
        "name": zone_id,
        "polygon": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        "parentId": parent,
        "layerId": "l_base",
        "attributes": attributes,
    }


def findings(plan: dict) -> list:
    return validate_plan(PlanDocument.model_validate(plan), TODAY)


def codes(plan: dict) -> list[str]:
    return [f.code for f in findings(plan)]
