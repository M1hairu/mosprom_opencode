"""Laser and fire rules of the LASSARD showroom (#30): G5, G15 and D-001 (no live beam process).

The facts come from `attributes` of objects and zones (keys: README.md in this folder).
An object attribute that is absent takes the default of its catalog type.
"""

from api.contracts import Finding, PlanDocument, PlanObject, PlanZone
from api.validation.geometry import Point, footprint, polygon_contains, segment_length
from api.validation.pochta import finding, object_type, ref

# A gap up to 1 mm between a zone edge and the walls along it still counts as closed.
WALL_COVER_TOLERANCE_M = 1e-3


def attribute(plan: PlanDocument, obj: PlanObject, key: str) -> object:
    value = obj.attributes.get(key)
    if value is not None:
        return value
    kind = object_type(plan, obj.typeId)
    if kind is None:
        return None
    return next((a.default for a in kind.attributes if a.key == key), None)


def category_of(plan: PlanDocument, obj: PlanObject) -> str:
    value = attribute(plan, obj, "category")
    if isinstance(value, str) and value.strip():
        return value.strip()
    kind = object_type(plan, obj.typeId)
    return "" if kind is None else kind.category.strip()


def is_live(plan: PlanDocument, obj: PlanObject) -> bool:
    """Power is on: `live: true` stated."""
    return attribute(plan, obj, "live") is True


def power_unknown(plan: PlanDocument, obj: PlanObject) -> bool:
    """One rule for every beam (#301): a beam item (`beam` is "open" or "closed") whose `live`
    is not specified is not proven off, so it counts as powered. An item with no `beam`
    (furniture, columns) is not a beam item: no `live` means no power for it.
    """
    beam = attribute(plan, obj, "beam")
    return attribute(plan, obj, "live") is None and beam in ("open", "closed")


def fire_barrier(zone: PlanZone) -> str:
    value = zone.attributes.get("fireBarrier")
    return value.strip() if isinstance(value, str) else ""


def validate_safety(plan: PlanDocument) -> list[Finding]:
    return [*_open_beam(plan), *_live_process(plan), *_fire_barrier(plan)]


def _interlocked_cabins(plan: PlanDocument) -> list[PlanZone]:
    return [
        zone
        for zone in plan.zones
        if zone.attributes.get("interlock") is True and _walled(plan, zone)
    ]


def _open_beam(plan: PlanDocument) -> list[Finding]:
    """G5, TRAP-4: an open class 4 beam item stands in a walled cabin with a door interlock.

    concept/05-safety.md 3.2: the cabin is a separate room (ГОСТ 31581-2012, п. 8.3.1).
    The showroom has no beam at all (D-001), so the item must also stand without power
    (`live: false`). Power not specified is not proven off: the item counts as powered.
    A powered item in a cabin gets LIVE_PROCESS_FORBIDDEN, see `_live_process`.
    A closed beam is not G5: its unknown power is reported by `_live_process` alone.
    """
    cabins = _interlocked_cabins(plan)
    found: list[Finding] = []
    for obj in plan.objects:
        if attribute(plan, obj, "beam") != "open":
            continue
        power = attribute(plan, obj, "live")
        # Concept 3.4: an open-beam product in the visitor hall stands without power.
        if power is False:
            continue
        shape = footprint(obj)
        if any(polygon_contains(zone.polygon, shape) for zone in cabins):
            continue
        unknown = " Питание не указано: считаем, что изделие включено." if power is None else ""
        found.append(
            finding(
                "OPEN_BEAM_OUTSIDE_INTERLOCK",
                "error",
                f"«{obj.label}» с открытым лучом класса 4 стоит вне замкнутой стенами зоны с "
                "блокировкой двери. В шоуруме луча нет (решение D-001): такое изделие стоит "
                "без питания (live: false), ключ снят (concept/05-safety.md, 3.4). Вне "
                "отдельного помещения с блокировкой двери открытый луч недопустим "
                f"(ГОСТ 31581-2012, п. 7.1.1, 8.3.1).{unknown}",
                [ref("object", obj.id)],
            )
        )
    return found


def _live_process(plan: PlanDocument) -> list[Finding]:
    """D-001: the showroom has no live beam process (cutting, engraving, cleaning, welding).

    Equipment stands without power. The catalog has no live non-beam category, so every
    object with `live: true` gets the finding, with or without a category.
    A beam item with power not specified (`power_unknown`) gets it too, one finding per item.
    The only exception is an open beam outside a cabin: G5 reports that item.
    """
    cabins = _interlocked_cabins(plan)
    found: list[Finding] = []
    for obj in plan.objects:
        if is_live(plan, obj):
            category = category_of(plan, obj)
            what = f"процесс «{category}»" if category else "процесс не указан"
            state = f"отмечен как работающий вживую, {what}"
        elif power_unknown(plan, obj):
            in_cabin = any(polygon_contains(zone.polygon, footprint(obj)) for zone in cabins)
            if attribute(plan, obj, "beam") == "open" and not in_cabin:
                continue
            state = "с лучом: питание не указано, считаем, что изделие включено"
        else:
            continue
        found.append(
            finding(
                "LIVE_PROCESS_FORBIDDEN",
                "error",
                f"«{obj.label}» {state}. В шоуруме нет ни одного "
                "живого процесса с лучом: оборудование стоит без питания (live: false), "
                "крупные станки показаны миниатюрами 1:5 и видео. Образец гостя режут в цехе, "
                "в закрытом корпусе (решение D-001, docs/decisions.md).",
                [ref("object", obj.id)],
            )
        )
    return found


def _fire_barrier(plan: PlanDocument) -> list[Finding]:
    """G15: a working machine stands in a compartment closed by a fire barrier.

    D-001 forbids live machines; this rule stays as a second guard if one appears anyway.
    Only `live: true` counts here. A beam item with power not specified already has its own
    finding (G5 or LIVE_PROCESS_FORBIDDEN), so it gets no second one.
    """
    compartments = [zone for zone in plan.zones if fire_barrier(zone)]
    found: list[Finding] = []
    open_compartments: dict[str, list[PlanObject]] = {}
    for obj in plan.objects:
        if not is_live(plan, obj):
            continue
        shape = footprint(obj)
        holders = [zone for zone in compartments if polygon_contains(zone.polygon, shape)]
        if not holders:
            found.append(
                finding(
                    "LASER_ZONE_NO_FIRE_BARRIER",
                    "error",
                    f"Работающий «{obj.label}» стоит вне отсека с противопожарной преградой. "
                    "По решению D-001 работающих станков в шоуруме нет: уберите питание "
                    "(live: false). Если работающий станок всё же появится, его отделяют от "
                    "зала противопожарной преградой (123-ФЗ, ст. 88, ч. 1; предел EIW 45 или "
                    "EIW 15 — 123-ФЗ, табл. 23–24).",
                    [ref("object", obj.id)],
                )
            )
            continue
        if any(_walled(plan, zone) for zone in holders):
            continue
        open_compartments.setdefault(holders[0].id, []).append(obj)
    for zone in compartments:
        inside = open_compartments.get(zone.id)
        if not inside:
            continue
        found.append(
            finding(
                "LASER_ZONE_NO_FIRE_BARRIER",
                "error",
                f"Отсек «{zone.name}» с преградой «{fire_barrier(zone)}» не замкнут стенами: "
                "часть его границы открыта в зал. Преграда отделяет отсек по всему контуру "
                "(123-ФЗ, ст. 88, ч. 1).",
                [ref("zone", zone.id), *(ref("object", obj.id) for obj in inside)],
            )
        )
    return found


def _walled(plan: PlanDocument, zone: PlanZone) -> bool:
    """Every edge of the zone lies along walls. Doors and windows in them do not count."""
    ring = zone.polygon
    return all(
        edge_covered(plan, start, ring[(index + 1) % len(ring)]) for index, start in enumerate(ring)
    )


def edge_covered(plan: PlanDocument, start: Point, end: Point) -> bool:
    """Walls parallel to the segment, its line within their half thickness, cover it end to end."""
    length = segment_length(start, end)
    if length == 0:
        return True
    ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    spans: list[tuple[float, float]] = []
    for wall in plan.walls:
        wall_len = segment_length(wall.from_, wall.to)
        if wall_len == 0:
            continue
        wx, wy = (wall.to[0] - wall.from_[0]) / wall_len, (wall.to[1] - wall.from_[1]) / wall_len
        if abs(ux * wy - uy * wx) > 1e-6:
            continue
        reach = wall.thickness_m / 2 + WALL_COVER_TOLERANCE_M
        offsets = [
            abs((p[0] - start[0]) * uy - (p[1] - start[1]) * ux) for p in (wall.from_, wall.to)
        ]
        if max(offsets) > reach:
            continue
        along = sorted(
            (p[0] - start[0]) * ux + (p[1] - start[1]) * uy for p in (wall.from_, wall.to)
        )
        spans.append((along[0], along[1]))
    cursor = 0.0
    for lo, hi in sorted(spans):
        if lo > cursor + WALL_COVER_TOLERANCE_M:
            break
        cursor = max(cursor, hi)
    return cursor >= length - WALL_COVER_TOLERANCE_M
