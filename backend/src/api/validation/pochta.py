"""Plan checks ported from pochta validatePlan (src/domain/validation, commit c9991cc).

Same codes, severities, messages and refs, in the same order. One deviation (#30, D-014):
an object on the layer BUILDING_LAYER_ID is a building element (a column of the hall). It
stays an obstacle and collides with movable objects, but it is not placed by the user, so
the placement, wall, opening, ceiling and zone-relation checks skip it. `locked` means
only "cannot move" (pochta, web/src/planner/edit.ts) and does not mark the building.
"""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from api.contracts import (
    Finding,
    FindingRef,
    PlanCountRule,
    PlanDistanceRule,
    PlanDocument,
    PlanObject,
    PlanObjectType,
    PlanOpening,
    PlanZone,
)
from api.validation.geometry import (
    EPS,
    Polygon,
    bounding_box,
    boxes_overlap,
    footprint,
    intervals_overlap,
    is_simple_polygon,
    object_interval,
    opening_centre,
    opening_clearance,
    outer_wall_ids,
    polygon_contains,
    polygons_overlap,
    segment_length,
    wall_obstacles,
)

NBSP = " "

# Team rule of pochta: floor this deep in front of a door or the entrance stays free.
OPENING_CLEARANCE_M = 0.9
# Height of the work surface: desk equipment stands on a table at 0.75 m.
WORK_SURFACE_M = 0.75
MAINTENANCE_DATE_KEY = "nextMaintenanceDate"
# Team rule of pochta, not a norm: warn this many days before the date.
MAINTENANCE_WARNING_DAYS = 14
INVENTORY_NUMBER_KEY = "inventoryNumber"
# The layer of the hall as built in content/plan-219*.json: columns (D-014).
BUILDING_LAYER_ID = "l_building"


def ref(kind: str, ref_id: str) -> FindingRef:
    return FindingRef(kind=kind, id=ref_id)


def finding(code: str, severity: str, message: str, refs: list[FindingRef]) -> Finding:
    return Finding(code=code, severity=severity, message=message, refs=refs)


# --- number-format.ts: ru-RU, decimal comma, NBSP before the unit ---


def format_number(value: float, min_digits: int, max_digits: int) -> str:
    exact = Decimal(value).quantize(Decimal(1).scaleb(-max_digits), rounding=ROUND_HALF_UP)
    text = f"{abs(exact):f}"
    whole, _, fraction = text.partition(".")
    fraction = fraction.rstrip("0").ljust(min_digits, "0")
    if len(whole) >= 5:  # ru-RU groups only from 10 000
        whole = f"{int(whole):,}".replace(",", NBSP)
    sign = "-" if exact < 0 else ""
    return f"{sign}{whole},{fraction}" if fraction else f"{sign}{whole}"


def format_length(value: float) -> str:
    return f"{format_number(value, 2, 2)}{NBSP}м"


def format_short(value: float, max_digits: int = 1) -> str:
    return format_number(value, 0, max_digits)


# --- catalog lookups ---


def object_type(plan: PlanDocument, type_id: str) -> PlanObjectType | None:
    return next((t for t in plan.catalog.objectTypes if t.id == type_id), None)


def is_physical(plan: PlanDocument, obj: PlanObject) -> bool:
    # An unknown type is solid: a silent "not physical" would hide a collision.
    found = object_type(plan, obj.typeId)
    return True if found is None else found.physical


def is_building(plan: PlanDocument, obj: PlanObject) -> bool:
    """A building element: an object on the building layer (D-014, columns of hall 219)."""
    return obj.layerId == BUILDING_LAYER_ID


def type_name(plan: PlanDocument, type_id: str) -> str:
    found = object_type(plan, type_id)
    return type_id if found is None else found.label


def opening_name(opening: PlanOpening) -> str:
    if opening.kind == "entrance":
        return "главного входа"
    if opening.kind == "door":
        return "двери"
    return "окна"


# --- validatePlan ---


def validate_pochta(plan: PlanDocument, today: date) -> list[Finding]:
    unusable = _unusable_geometry(plan)
    # Containment, collisions and areas are meaningless on a self-intersecting polygon.
    if unusable:
        return unusable
    placement = _placement(plan)
    findings = [*_zone_issues(plan), *placement, *_collisions(plan), *_wall_issues(plan)]
    for obj in plan.objects:
        findings += _opening_issues(plan, obj)
    for obj in plan.objects:
        findings += _support_issues(plan, obj)
    findings += _ceiling_issues(plan)
    findings += _duplicate_inventory(plan)
    findings += _missing_inventory(plan)
    findings += _maintenance(plan, today)
    findings += _rule_issues(plan)
    outside_own_zone = {f.refs[0].id for f in placement if f.code == "OBJECT_OUTSIDE_ZONE"}
    findings += [
        f
        for f in _relation_issues(plan)
        if f.code != "ZONE_UNASSIGNED" or f.refs[0].id not in outside_own_zone
    ]
    return findings


def _unusable_geometry(plan: PlanDocument) -> list[Finding]:
    found: list[Finding] = []
    if not is_simple_polygon(plan.room.boundary):
        found.append(
            finding(
                "POLYGON_UNUSABLE",
                "error",
                "Контур помещения пересекает сам себя: расчёты по нему невозможны.",
                [ref("room", plan.room.id)],
            )
        )
    for zone in plan.zones:
        if not is_simple_polygon(zone.polygon):
            found.append(
                finding(
                    "POLYGON_UNUSABLE",
                    "error",
                    f"Контур зоны «{zone.name}» пересекает сам себя: расчёты по нему невозможны.",
                    [ref("zone", zone.id)],
                )
            )
    for obj in plan.objects:
        if obj.outline is None or is_simple_polygon(footprint(obj)):
            continue
        found.append(
            finding(
                "POLYGON_UNUSABLE",
                "error",
                f"Контур объекта «{obj.label}» пересекает сам себя: расчёты по нему невозможны.",
                [ref("object", obj.id)],
            )
        )
    return found


def _zone_issues(plan: PlanDocument) -> list[Finding]:
    by_id = {zone.id: zone for zone in plan.zones}
    found: list[Finding] = []
    for zone in plan.zones:
        if not polygon_contains(plan.room.boundary, zone.polygon):
            found.append(
                finding(
                    "ZONE_OUTSIDE_ROOM",
                    "error",
                    f"Зона «{zone.name}» выходит за границы помещения.",
                    [ref("zone", zone.id), ref("room", plan.room.id)],
                )
            )
        if zone.parentId is None:
            continue
        parent = by_id.get(zone.parentId)
        if parent is None or polygon_contains(parent.polygon, zone.polygon):
            continue
        found.append(
            finding(
                "ZONE_OUTSIDE_PARENT",
                "error",
                f"Зона «{zone.name}» не лежит целиком в родительской зоне «{parent.name}».",
                [ref("zone", zone.id), ref("zone", parent.id)],
            )
        )
    usable = [zone for zone in plan.zones if is_simple_polygon(zone.polygon)]
    for i, first in enumerate(usable):
        for second in usable[i + 1 :]:
            if not polygons_overlap(first.polygon, second.polygon):
                continue
            first_inside = polygon_contains(second.polygon, first.polygon)
            second_inside = polygon_contains(first.polygon, second.polygon)
            # Exactly one nesting is a zone hierarchy, not a finding.
            if first_inside != second_inside:
                continue
            found.append(
                finding(
                    "ZONE_OVERLAPS_ZONE",
                    "warning",
                    f"Зоны «{first.name}» и «{second.name}» пересекаются, не вкладываясь одна "
                    "в другую: объекты в общей части не могут определить свою зону. Вложите "
                    "одну в другую или разведите границы.",
                    [ref("zone", first.id), ref("zone", second.id)],
                )
            )
    return found


def _placement(plan: PlanDocument) -> list[Finding]:
    by_id = {zone.id: zone for zone in plan.zones}
    found: list[Finding] = []
    for obj in plan.objects:
        if is_building(plan, obj):
            continue
        shape = footprint(obj)
        if not polygon_contains(plan.room.boundary, shape):
            found.append(
                finding(
                    "OBJECT_OUTSIDE_ROOM",
                    "error",
                    f"Объект «{obj.label}» выходит за границы помещения.",
                    [ref("object", obj.id), ref("room", plan.room.id)],
                )
            )
        zone = by_id.get(obj.zoneId) if obj.zoneId is not None else None
        if zone is None or polygon_contains(zone.polygon, shape):
            continue
        found.append(
            finding(
                "OBJECT_OUTSIDE_ZONE",
                "error",
                f"Объект «{obj.label}» отнесён к зоне «{zone.name}», но не лежит в ней целиком.",
                [ref("object", obj.id), ref("zone", zone.id)],
            )
        )
    return found


def _collisions(plan: PlanDocument) -> list[Finding]:
    solid = []
    for obj in plan.objects:
        if not is_physical(plan, obj):
            continue
        shape = footprint(obj)
        solid.append(
            (obj, shape, bounding_box(shape), object_interval(obj), is_building(plan, obj))
        )
    found: list[Finding] = []
    for i, (a, a_shape, a_box, a_interval, a_building) in enumerate(solid):
        for b, b_shape, b_box, b_interval, b_building in solid[i + 1 :]:
            # Two building elements are the hall as built, not a placement.
            if a_building and b_building:
                continue
            if not boxes_overlap(a_box, b_box) or not intervals_overlap(a_interval, b_interval):
                continue
            if not polygons_overlap(a_shape, b_shape):
                continue
            found.append(
                finding(
                    "OBJECT_COLLISION",
                    "error",
                    f"Объекты «{a.label}» и «{b.label}» занимают одно место.",
                    [ref("object", a.id), ref("object", b.id)],
                )
            )
    return found


def _wall_issues(plan: PlanDocument) -> list[Finding]:
    outer = outer_wall_ids(plan.walls, plan.room.boundary)
    # Any part of a wall lies inside the whole wall without openings: its box is a cheap filter.
    whole = {}
    for wall in plan.walls:
        parts = wall_obstacles(wall, [], (0.0, wall.height_m), plan.walls)
        whole[wall.id] = bounding_box([p for part in parts for p in part]) if parts else None
    found: list[Finding] = []
    for obj in plan.objects:
        if not is_physical(plan, obj) or is_building(plan, obj):
            continue
        shape = footprint(obj)
        box = bounding_box(shape)
        interval = object_interval(obj)
        for wall in plan.walls:
            if whole[wall.id] is None or not boxes_overlap(box, whole[wall.id]):
                continue
            parts = wall_obstacles(wall, plan.openings, interval, plan.walls)
            if not any(
                boxes_overlap(box, bounding_box(part)) and polygons_overlap(shape, part)
                for part in parts
            ):
                continue
            what = "наружную стену" if wall.id in outer else "перегородку"
            found.append(
                finding(
                    "OBJECT_HITS_WALL",
                    "error",
                    f"Объект «{obj.label}» пересекает {what}.",
                    [ref("object", obj.id), ref("wall", wall.id)],
                )
            )
    return found


def _opening_issues(plan: PlanDocument, obj: PlanObject) -> list[Finding]:
    if not is_physical(plan, obj) or is_building(plan, obj):
        return []
    shape = footprint(obj)
    interval = object_interval(obj)
    found: list[Finding] = []
    for opening in plan.openings:
        if opening.kind == "window":
            continue
        if not intervals_overlap(interval, (opening.sill_m, opening.sill_m + opening.height_m)):
            continue
        wall = next((w for w in plan.walls if w.id == opening.wallId), None)
        if wall is None:
            continue
        clearance = opening_clearance(opening, wall, OPENING_CLEARANCE_M)
        if not clearance or not polygons_overlap(shape, clearance):
            continue
        found.append(
            finding(
                "OBJECT_BLOCKS_OPENING",
                "error",
                f"Объект «{obj.label}» загораживает проём {opening_name(opening)}: с обеих "
                f"сторон нужно {format_length(OPENING_CLEARANCE_M)} свободного пола.",
                [ref("object", obj.id), ref("opening", opening.id)],
            )
        )
    return found


def _is_desk_equipment(plan: PlanDocument, obj: PlanObject) -> bool:
    found = object_type(plan, obj.typeId)
    if found is None or found.occupiesFloor:
        return False
    return abs(found.defaultBase_m - WORK_SURFACE_M) <= EPS


def _support_issues(plan: PlanDocument, obj: PlanObject) -> list[Finding]:
    if not _is_desk_equipment(plan, obj) or obj.base_m <= EPS:
        return []
    shape = footprint(obj)
    for other in plan.objects:
        if other.id == obj.id or not is_physical(plan, other):
            continue
        if abs(other.base_m + other.height_m - obj.base_m) > EPS:
            continue
        if polygon_contains(footprint(other), shape):
            return []
    return [
        finding(
            "OBJECT_UNSUPPORTED",
            "error",
            f"Объект «{obj.label}» висит на высоте {format_length(obj.base_m)}: под ним нет "
            "стола, на котором он целиком помещается. Поставьте на стол.",
            [ref("object", obj.id)],
        )
    ]


def _ceiling_issues(plan: PlanDocument) -> list[Finding]:
    ceiling = plan.room.ceilingHeight_m
    found: list[Finding] = []
    for obj in plan.objects:
        top = obj.base_m + obj.height_m
        if top <= ceiling + EPS or is_building(plan, obj):
            continue
        found.append(
            finding(
                "OBJECT_ABOVE_CEILING",
                "error",
                f"Объект «{obj.label}» поднимается до {format_length(top)} — выше потолка "
                f"{format_length(ceiling)}.",
                [ref("object", obj.id), ref("room", plan.room.id)],
            )
        )
    return found


def _inventory_number(obj: PlanObject) -> str | None:
    value = obj.attributes.get(INVENTORY_NUMBER_KEY)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return _js_number(value)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _js_number(value: float) -> str:
    """String(value) of JavaScript for a finite number."""
    if value == int(value) and abs(value) < 1e21:
        return str(int(value))
    return repr(float(value))


def _duplicate_inventory(plan: PlanDocument) -> list[Finding]:
    first_holder: dict[str, PlanObject] = {}
    found: list[Finding] = []
    for obj in plan.objects:
        number = _inventory_number(obj)
        if number is None:
            continue
        first = first_holder.setdefault(number, obj)
        if first is obj:
            continue
        found.append(
            finding(
                "OBJECT_DUPLICATE_INVENTORY_NUMBER",
                "warning",
                f"Инвентарный номер «{number}» у объекта «{obj.label}» уже присвоен объекту "
                f"«{first.label}»: у каждого предмета свой номер.",
                [ref("object", obj.id), ref("object", first.id)],
            )
        )
    return found


def _missing_inventory(plan: PlanDocument) -> list[Finding]:
    # A plan where no object has a number keeps no register: it stays silent.
    if all(_inventory_number(obj) is None for obj in plan.objects):
        return []
    found: list[Finding] = []
    for obj in plan.objects:
        kind = object_type(plan, obj.typeId)
        if kind is None or not kind.physical:
            continue
        if not any(attribute.key == INVENTORY_NUMBER_KEY for attribute in kind.attributes):
            continue
        if _inventory_number(obj) is not None:
            continue
        found.append(
            finding(
                "OBJECT_MISSING_INVENTORY_NUMBER",
                "warning",
                f"У объекта «{obj.label}» нет инвентарного номера: впишите номер с ярлыка "
                "предмета в карточке.",
                [ref("object", obj.id)],
            )
        )
    return found


_ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RU_DAY = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


def _parse_day(text: str) -> date | None:
    """«2026-10-18» or «18.10.2026»; a day that does not exist is not a date."""
    trimmed = text.strip()
    iso = _ISO_DAY.match(trimmed)
    ru = _RU_DAY.match(trimmed)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
    elif ru:
        day, month, year = (int(part) for part in ru.groups())
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _maintenance(plan: PlanDocument, today: date) -> list[Finding]:
    note = (
        f"Правило команды: предупреждение за {MAINTENANCE_WARNING_DAYS}{NBSP}дн. до даты "
        "«Следующее ТО»."
    )
    found: list[Finding] = []
    for obj in plan.objects:
        value = obj.attributes.get(MAINTENANCE_DATE_KEY)
        if not isinstance(value, str) or not value.strip():
            continue
        due = _parse_day(value)
        if due is None:
            code = "MAINTENANCE_DATE_INVALID"
            message = (
                f"У объекта «{obj.label}» в поле «Следующее ТО» не дата: «{value.strip()}». "
                "Впишите дату как 2026-10-18 или 18.10.2026."
            )
        else:
            days = (due - today).days
            shown = due.strftime("%d.%m.%Y")
            if days < 0:
                code = "MAINTENANCE_OVERDUE"
                message = (
                    f"ТО объекта «{obj.label}» просрочено: срок {shown}, прошло "
                    f"{-days}{NBSP}дн. {note}"
                )
            elif days <= MAINTENANCE_WARNING_DAYS:
                code = "MAINTENANCE_DUE_SOON"
                when = "сегодня" if days == 0 else f"через {days}{NBSP}дн."
                message = f"ТО объекта «{obj.label}» {when}: срок {shown}. {note}"
            else:
                continue
        found.append(finding(code, "warning", message, [ref("object", obj.id)]))
    return found


def _severity_of(rule: PlanCountRule | PlanDistanceRule) -> str:
    """A team rule is a warning, an organizers' rule is an error."""
    return "error" if rule.source == "organizer-material" else "warning"


def _rule_note(rule: PlanCountRule | PlanDistanceRule) -> str:
    if rule.source == "organizer-material":
        return "Источник правила: материалы организаторов."
    return "Источник правила: справочник проекта."


def _rule_issues(plan: PlanDocument) -> list[Finding]:
    found: list[Finding] = []
    for rule in plan.catalog.rules:
        if isinstance(rule, PlanCountRule):
            found += _count_rule(plan, rule)
        else:
            found += _distance_rule(plan, rule)
    return found


def _zone_chain(zone_id: str, parents: dict[str, str | None]) -> list[str]:
    """The zone and every ancestor, each once: a cycle does not hang the check."""
    chain: list[str] = []
    current: str | None = zone_id
    while current is not None and current in parents and current not in chain:
        chain.append(current)
        current = parents[current]
    return chain


def _nested_in_same_type(plan: PlanDocument, zone: PlanZone) -> bool:
    parent_id = zone.parentId
    for _ in range(len(plan.zones)):
        if parent_id is None:
            return False
        parent = next((z for z in plan.zones if z.id == parent_id), None)
        if parent is None:
            return False
        if parent.typeId == zone.typeId:
            return True
        parent_id = parent.parentId
    return False


def _count_rule(plan: PlanDocument, rule: PlanCountRule) -> list[Finding]:
    parents = {zone.id: zone.parentId for zone in plan.zones}
    where = "без вложенных зон" if rule.scope == "direct" else "вместе с вложенными зонами"
    name = type_name(plan, rule.objectTypeId)
    found: list[Finding] = []
    for zone in plan.zones:
        if zone.typeId != rule.zoneTypeId:
            continue
        count = 0
        for obj in plan.objects:
            if obj.typeId != rule.objectTypeId or obj.zoneId is None:
                continue
            if rule.scope == "direct":
                count += obj.zoneId == zone.id
            else:
                count += zone.id in _zone_chain(obj.zoneId, parents)
        min_applies = rule.scope != "inclusive" or not _nested_in_same_type(plan, zone)
        if rule.min is not None and count < rule.min and min_applies:
            found.append(
                finding(
                    "RULE_COUNT_BELOW_MIN",
                    _severity_of(rule),
                    f"В зоне «{zone.name}» {count} шт. «{name}» при минимуме {rule.min} "
                    f"({where}). {_rule_note(rule)}",
                    [ref("zone", zone.id)],
                )
            )
        if rule.max is not None and count > rule.max:
            found.append(
                finding(
                    "RULE_COUNT_ABOVE_MAX",
                    _severity_of(rule),
                    f"В зоне «{zone.name}» {count} шт. «{name}» при максимуме {rule.max} "
                    f"({where}). {_rule_note(rule)}",
                    [ref("zone", zone.id)],
                )
            )
    return found


def _distance_rule(plan: PlanDocument, rule: PlanDistanceRule) -> list[Finding]:
    targets = [obj for obj in plan.objects if obj.typeId == rule.objectTypeId]
    if not targets:
        return []
    walls = {wall.id: wall for wall in plan.walls}
    entrances = [
        (opening, opening_centre(opening, walls[opening.wallId]))
        for opening in plan.openings
        if opening.wallId in walls
        and (
            opening.kind == "entrance" if rule.entranceId is None else opening.id == rule.entranceId
        )
    ]
    name = type_name(plan, rule.objectTypeId)
    if not entrances:
        return [
            finding(
                "RULE_ENTRANCE_MISSING",
                _severity_of(rule),
                f"Для «{name}» требуется проверить расстояние до входа, но входов в плане нет. "
                f"{_rule_note(rule)}",
                [],
            )
        ]
    found: list[Finding] = []
    for obj in targets:
        nearest, best = entrances[0], segment_length(obj.position, entrances[0][1])
        for entrance in entrances:
            measured = segment_length(obj.position, entrance[1])
            if measured < best:
                nearest, best = entrance, measured
        if best <= rule.maxDistance_m:
            continue
        found.append(
            finding(
                "RULE_TOO_FAR_FROM_ENTRANCE",
                _severity_of(rule),
                f"Объект «{obj.label}» в {format_length(best)} от {opening_name(nearest[0])} при "
                f"норме не более {format_short(rule.maxDistance_m, 2)}{NBSP}м. {_rule_note(rule)}",
                [ref("object", obj.id), ref("opening", nearest[0].id)],
            )
        )
    return found


def _zone_depth(zone_id: str, parents: dict[str, str | None]) -> int | None:
    """Nesting depth, 0 for a root; None when the parent chain does not end."""
    seen: set[str] = set()
    current: str | None = zone_id
    depth = 0
    while current is not None:
        if current in seen:
            return None
        seen.add(current)
        parent = parents.get(current)
        if parent is None:
            return depth
        current = parent
        depth += 1
    return depth


def _relation_issues(plan: PlanDocument) -> list[Finding]:
    """ZONE_UNASSIGNED and ZONE_AMBIGUOUS: an object belongs to the deepest containing zone."""
    parents = {zone.id: zone.parentId for zone in plan.zones}
    prepared: list[tuple[PlanZone, Polygon, tuple, int]] = []
    for zone in plan.zones:
        depth = _zone_depth(zone.id, parents)
        prepared.append(
            (zone, zone.polygon, bounding_box(zone.polygon), -1 if depth is None else depth)
        )
    found: list[Finding] = []
    for obj in plan.objects:
        if is_building(plan, obj):
            continue
        shape = footprint(obj)
        box = bounding_box(shape)
        containing = [
            entry
            for entry in prepared
            if boxes_overlap(entry[2], box) and polygon_contains(entry[1], shape)
        ]
        if not containing:
            found.append(
                finding(
                    "ZONE_UNASSIGNED",
                    "warning",
                    f"Объект «{obj.label}» не лежит целиком ни в одной зоне.",
                    [ref("object", obj.id)],
                )
            )
            continue
        deepest_depth = max(entry[3] for entry in containing)
        deepest = [entry[0] for entry in containing if entry[3] == deepest_depth]
        if len(deepest) > 1:
            names = ", ".join(f"«{zone.name}»" for zone in deepest)
            found.append(
                finding(
                    "ZONE_AMBIGUOUS",
                    "warning",
                    f"Объект «{obj.label}» одинаково глубоко лежит в зонах: {names}.",
                    [ref("object", obj.id), *(ref("zone", zone.id) for zone in deepest)],
                )
            )
    return found
