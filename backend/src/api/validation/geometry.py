"""Polygon and wall geometry, ported from pochta (src/domain/geometry, commit c9991cc).

Model: metres, X to the right, Y up, a positive rotation turns clockwise. Touching
without positive overlap area is not a collision. Comparisons use EPS, never a bare ==.
"""

import math

from api.contracts import PlanObject, PlanOpening, PlanWall

Point = tuple[float, float]
Polygon = list[Point]
Box = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y

EPS = 1e-6  # TOLERANCE.coordinate_m
AREA_EPS = 1e-8  # TOLERANCE.area_m2

UNIT_SQUARE: Polygon = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
CIRCLE_OUTLINE_VERTICES = 24
TRIANGLE: Polygon = [(0.0, 0.5), (-0.5, -0.5), (0.5, -0.5)]


def _round6(value: float) -> float:
    # Math.round(value * 1e6) / 1e6 in JS rounds half up, not half to even.
    rounded = math.floor(value * 1e6 + 0.5) / 1e6
    return 0.0 if rounded == 0 else rounded


CIRCLE: Polygon = [
    (
        _round6(math.cos(2 * math.pi * step / CIRCLE_OUTLINE_VERTICES) / 2),
        _round6(math.sin(2 * math.pi * step / CIRCLE_OUTLINE_VERTICES) / 2),
    )
    for step in range(CIRCLE_OUTLINE_VERTICES)
]


def symbol_outline(symbol: str) -> Polygon | None:
    if symbol == "circle":
        return CIRCLE
    if symbol == "triangle":
        return TRIANGLE
    return None


# --- polygons.ts ---


def signed_area(polygon: Polygon) -> float:
    total = 0.0
    for i, current in enumerate(polygon):
        nxt = polygon[(i + 1) % len(polygon)]
        total += current[0] * nxt[1] - nxt[0] * current[1]
    return total / 2


def polygon_area(polygon: Polygon) -> float:
    return abs(signed_area(polygon))


def bounding_box(polygon: Polygon) -> Box:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def boxes_overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] - EPS and b[0] < a[2] - EPS and a[1] < b[3] - EPS and b[1] < a[3] - EPS


def box_gap(a: Box, b: Box) -> float:
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def on_segment(point: Point, start: Point, end: Point) -> bool:
    if abs(_cross(start, end, point)) > EPS:
        return False
    within_x = min(start[0], end[0]) - EPS <= point[0] <= max(start[0], end[0]) + EPS
    within_y = min(start[1], end[1]) - EPS <= point[1] <= max(start[1], end[1]) + EPS
    return within_x and within_y


def segments_properly_cross(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """True only when the segments cross at an interior point of both."""
    d1 = _cross(a1, a2, b1)
    d2 = _cross(a1, a2, b2)
    d3 = _cross(b1, b2, a1)
    d4 = _cross(b1, b2, a2)
    if abs(d1) <= EPS or abs(d2) <= EPS or abs(d3) <= EPS or abs(d4) <= EPS:
        return False
    return d1 * d2 < 0 and d3 * d4 < 0


def locate_point(point: Point, polygon: Polygon) -> str:
    """'inside', 'boundary' or 'outside': ray casting, the boundary reported separately."""
    count = len(polygon)
    for i in range(count):
        if on_segment(point, polygon[i], polygon[(i + 1) % count]):
            return "boundary"
    px, py = point
    inside = False
    for i in range(count):
        start = polygon[i]
        end = polygon[(i + 1) % count]
        if (start[1] > py) == (end[1] > py):
            continue
        t = (py - start[1]) / (end[1] - start[1])
        if px < start[0] + t * (end[0] - start[0]):
            inside = not inside
    return "inside" if inside else "outside"


def _any_proper_crossing(a: Polygon, b: Polygon) -> bool:
    for i in range(len(a)):
        a1, a2 = a[i], a[(i + 1) % len(a)]
        for j in range(len(b)):
            if segments_properly_cross(a1, a2, b[j], b[(j + 1) % len(b)]):
                return True
    return False


def _intersection_params(a1: Point, a2: Point, b1: Point, b2: Point) -> list[float]:
    rx, ry = a2[0] - a1[0], a2[1] - a1[1]
    sx, sy = b2[0] - b1[0], b2[1] - b1[1]
    denom = rx * sy - ry * sx
    qpx, qpy = b1[0] - a1[0], b1[1] - a1[1]
    if abs(denom) <= EPS:
        if abs(qpx * ry - qpy * rx) > EPS:
            return []
        len2 = rx * rx + ry * ry
        if len2 <= EPS:
            return []
        t0 = (qpx * rx + qpy * ry) / len2
        t1 = ((b2[0] - a1[0]) * rx + (b2[1] - a1[1]) * ry) / len2
        return [t for t in (t0, t1) if -EPS <= t <= 1 + EPS]
    t = (qpx * sy - qpy * sx) / denom
    u = (qpx * ry - qpy * rx) / denom
    if t < -EPS or t > 1 + EPS or u < -EPS or u > 1 + EPS:
        return []
    return [t]


def _edge_passes_through(a: Polygon, b: Polygon, position: str) -> bool:
    """Some part of an edge of `a` runs through the interior (or exterior) of `b`."""
    for i in range(len(a)):
        a1, a2 = a[i], a[(i + 1) % len(a)]
        params = [0.0, 1.0]
        for j in range(len(b)):
            params.extend(_intersection_params(a1, a2, b[j], b[(j + 1) % len(b)]))
        ordered = sorted(t for t in params if 0 <= t <= 1)
        for k in range(1, len(ordered)):
            lo, hi = ordered[k - 1], ordered[k]
            if hi - lo <= EPS:
                continue
            mid = (lo + hi) / 2
            point = (a1[0] + (a2[0] - a1[0]) * mid, a1[1] + (a2[1] - a1[1]) * mid)
            if locate_point(point, b) == position:
                return True
    return False


def polygon_contains(container: Polygon, shape: Polygon) -> bool:
    """Whole-footprint containment: every vertex inside or on the border, no edge out."""
    for vertex in shape:
        if locate_point(vertex, container) == "outside":
            return False
    if _any_proper_crossing(container, shape):
        return False
    return not _edge_passes_through(shape, container, "outside")


def polygons_overlap(a: Polygon, b: Polygon) -> bool:
    """Positive overlap area. Sharing an edge or a corner is not an overlap."""
    if not boxes_overlap(bounding_box(a), bounding_box(b)):
        return False
    if _any_proper_crossing(a, b):
        return True
    if any(locate_point(v, b) == "inside" for v in a):
        return True
    if any(locate_point(v, a) == "inside" for v in b):
        return True
    if _edge_passes_through(a, b, "inside") or _edge_passes_through(b, a, "inside"):
        return True
    if polygon_contains(a, b) and polygon_area(b) > AREA_EPS:
        return True
    return polygon_contains(b, a) and polygon_area(a) > AREA_EPS


def is_simple_polygon(polygon: Polygon) -> bool:
    """At least three vertices, positive area and no self-intersection."""
    count = len(polygon)
    if count < 3 or polygon_area(polygon) <= AREA_EPS:
        return False
    for i in range(count):
        a1, a2 = polygon[i], polygon[(i + 1) % count]
        if math.hypot(a2[0] - a1[0], a2[1] - a1[1]) <= EPS:
            return False
        for j in range(i + 1, count):
            b1, b2 = polygon[j], polygon[(j + 1) % count]
            if j == i + 1:
                if on_segment(b2, a1, a2) or on_segment(a1, b1, b2):
                    return False
                continue
            if i == 0 and j == count - 1:
                if on_segment(b1, a1, a2) or on_segment(a2, b1, b2):
                    return False
                continue
            if segments_properly_cross(a1, a2, b1, b2):
                return False
            if (
                on_segment(a1, b1, b2)
                or on_segment(a2, b1, b2)
                or on_segment(b1, a1, a2)
                or on_segment(b2, a1, a2)
            ):
                return False
    return True


def segment_length(start: Point, end: Point) -> float:
    return math.hypot(end[0] - start[0], end[1] - start[1])


def project_on_segment(point: Point, start: Point, end: Point) -> tuple[float, Point, float]:
    """Clamped position t along the segment, the closest point and the distance to it."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= EPS * EPS:
        return 0.0, start, segment_length(start, point)
    along = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    t = min(1.0, max(0.0, along))
    foot = (start[0] + t * dx, start[1] + t * dy)
    return t, foot, segment_length(foot, point)


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    return project_on_segment(point, start, end)[2]


def polygon_gap(a: Polygon, b: Polygon) -> tuple[float, Point, Point] | None:
    """Closest approach of two rings: distance, the point on `a`, the point on `b`."""
    if len(a) < 3 or len(b) < 3:
        return None
    best: tuple[float, Point, Point] = (math.inf, a[0], b[0])
    for point in a:
        for i in range(len(b)):
            _, foot, distance = project_on_segment(point, b[i], b[(i + 1) % len(b)])
            if distance < best[0]:
                best = (distance, point, foot)
    for point in b:
        for i in range(len(a)):
            _, foot, distance = project_on_segment(point, a[i], a[(i + 1) % len(a)])
            if distance < best[0]:
                best = (distance, foot, point)
    if best[0] > EPS and polygons_overlap(a, b):
        return 0.0, best[1], best[2]
    return best


def point_polygon_distance(point: Point, polygon: Polygon) -> float:
    """Zero inside or on the ring, otherwise the distance to its nearest edge."""
    if locate_point(point, polygon) != "outside":
        return 0.0
    count = len(polygon)
    return min(
        point_segment_distance(point, polygon[i], polygon[(i + 1) % count]) for i in range(count)
    )


# --- coordinates.ts, outline.ts ---


def rotate_offset(offset: Point, degrees: float) -> Point:
    """Rotates a local offset clockwise by `degrees`."""
    wrapped = math.fmod(degrees, 360)
    angle = math.radians(wrapped + 360 if wrapped < 0 else wrapped)
    cos, sin = math.cos(angle), math.sin(angle)
    dx, dy = offset
    return dx * cos + dy * sin, -dx * sin + dy * cos


def to_world(centre: Point, offset: Point, degrees: float) -> Point:
    rx, ry = rotate_offset(offset, degrees)
    return centre[0] + rx, centre[1] + ry


def footprint(obj: PlanObject) -> Polygon:
    """Floor projection of a rotated object: its outline scaled by size_m, turned and placed."""
    width, depth = obj.size_m
    outline = obj.outline if obj.outline is not None else UNIT_SQUARE
    return [to_world(obj.position, (u * width, v * depth), obj.rotation_deg) for u, v in outline]


def intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Positive overlap of two height intervals (base, top)."""
    return min(a[1], b[1]) - max(a[0], b[0]) > EPS


def object_interval(obj: PlanObject) -> tuple[float, float]:
    return obj.base_m, obj.base_m + obj.height_m


# --- walls: index.ts, wall-joints.ts ---


def wall_length(wall: PlanWall) -> float:
    return segment_length(wall.from_, wall.to)


def _vcross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _near(a: Point, b: Point) -> bool:
    return segment_length(a, b) <= EPS


def _perpendicular_t_trim(
    point: Point,
    u: Point,
    wall: PlanWall,
    incident: list[PlanWall],
    openings: list[PlanOpening],
) -> float:
    """Only an unambiguous perpendicular T; angled or multi-way junctions keep their caps."""
    if not 1 <= len(incident) <= 2:
        return 0.0
    through = incident[0]
    if any(
        abs(other.height_m - wall.height_m) > EPS
        or abs(other.thickness_m - through.thickness_m) > EPS
        for other in incident
    ):
        return 0.0
    if len(incident) == 1:
        from_distance = segment_length(point, through.from_)
        to_distance = segment_length(point, through.to)
        if min(from_distance, to_distance) <= EPS:
            return 0.0
        length = segment_length(through.from_, through.to)
        v = (
            (through.to[0] - through.from_[0]) / length,
            (through.to[1] - through.from_[1]) / length,
        )
        reach = min(from_distance, to_distance)
    else:
        rays: list[Point] = []
        for other in incident:
            if _near(point, other.from_):
                end = other.to
            elif _near(point, other.to):
                end = other.from_
            else:
                return 0.0
            ray = (end[0] - point[0], end[1] - point[1])
            if math.hypot(*ray) <= EPS:
                return 0.0
            rays.append(ray)
        a, b = rays
        a_length, b_length = math.hypot(*a), math.hypot(*b)
        v = (a[0] / a_length, a[1] / a_length)
        if math.hypot(v[0] + b[0] / b_length, v[1] + b[1] / b_length) > EPS:
            return 0.0
        reach = min(a_length, b_length)
    if abs(u[0] * v[0] + u[1] * v[1]) > EPS:
        return 0.0
    for other in incident:
        length = segment_length(other.from_, other.to)
        along = (
            (point[0] - other.from_[0]) * (other.to[0] - other.from_[0])
            + (point[1] - other.from_[1]) * (other.to[1] - other.from_[1])
        ) / length
        for opening in openings:
            if (
                opening.wallId == other.id
                and opening.offset_m < along + wall.thickness_m / 2 + EPS
                and opening.offset_m + opening.width_m > along - wall.thickness_m / 2 - EPS
            ):
                return 0.0
    trim = through.thickness_m / 2
    ok = EPS < trim < wall_length(wall) * 0.45 and wall.thickness_m / 2 < reach * 0.45
    return trim if ok else 0.0


def _joined_wall_span(
    wall: PlanWall,
    polygon: Polygon,
    start: float,
    end: float,
    walls: list[PlanWall],
    openings: list[PlanOpening],
) -> Polygon:
    """Mitred endpoint joins: two walls share the same face intersection."""
    length = wall_length(wall)
    if length <= EPS or len(polygon) != 4:
        return polygon
    u = ((wall.to[0] - wall.from_[0]) / length, (wall.to[1] - wall.from_[1]) / length)
    if not walls or start < -EPS or end > length + EPS:
        return polygon
    normal = (-u[1] * wall.thickness_m / 2, u[0] * wall.thickness_m / 2)
    fx, fy = wall.from_
    tx, ty = wall.to
    base: Polygon = [
        (fx + normal[0], fy + normal[1]),
        (tx + normal[0], ty + normal[1]),
        (tx - normal[0], ty - normal[1]),
        (fx - normal[0], fy - normal[1]),
    ]
    result = list(base)
    for at_start in (True, False):
        point = wall.from_ if at_start else wall.to
        incident = [
            other
            for other in walls
            if other.id != wall.id and point_segment_distance(point, other.from_, other.to) <= EPS
        ]
        indices = (0, 3) if at_start else (1, 2)
        sign = 1 if at_start else -1
        trim = _perpendicular_t_trim(point, u, wall, incident, openings)
        if trim > 0:
            for index in indices:
                bx, by = base[index]
                result[index] = (bx + u[0] * trim * sign, by + u[1] * trim * sign)
            continue
        if len(incident) != 1:
            continue
        other = incident[0]
        if _near(point, other.from_):
            other_end = other.to
        elif _near(point, other.to):
            other_end = other.from_
        else:
            continue
        if abs(other.height_m - wall.height_m) > EPS:
            continue
        other_length = segment_length(point, other_end)
        if other_length <= EPS:
            continue
        v = ((other_end[0] - point[0]) / other_length, (other_end[1] - point[1]) / other_length)
        denominator = _vcross(u, v)
        if abs(denominator) < 0.25:
            continue
        joined: Polygon = []
        safe = True
        for side_index, index in enumerate(indices):
            own_side = 1 if side_index == 0 else -1
            other_side = -own_side * sign
            half = other.thickness_m / 2 * other_side
            q = (point[0] - v[1] * half, point[1] + v[0] * half)
            a = base[index]
            delta = (q[0] - a[0], q[1] - a[1])
            offset = _vcross(delta, v) / denominator
            limit_other = min(other_length * 0.45, 2 * max(wall.thickness_m, other.thickness_m))
            if abs(_vcross(delta, u) / denominator) > limit_other:
                safe = False
            joined.append((a[0] + u[0] * offset, a[1] + u[1] * offset))
        limit = min(length * 0.45, 2 * max(wall.thickness_m, other.thickness_m))
        if not safe or any(
            segment_length(p, base[indices[i]]) > limit for i, p in enumerate(joined)
        ):
            continue
        for i, index in enumerate(indices):
            result[index] = joined[i]

    def along(p: Point) -> float:
        return (p[0] - fx) * u[0] + (p[1] - fy) * u[1]

    def clip(ring: Polygon, offset: float, keep_after: bool) -> Polygon:
        def inside(p: Point) -> bool:
            return along(p) >= offset - EPS if keep_after else along(p) <= offset + EPS

        output: Polygon = []
        for index, a in enumerate(ring):
            b = ring[(index + 1) % len(ring)]
            if inside(a):
                output.append(a)
            if inside(a) != inside(b):
                t = (offset - along(a)) / (along(b) - along(a))
                output.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        unique = [p for i, p in enumerate(output) if not _near(p, output[i - 1])]
        return [] if len(unique) < 3 else unique

    if start > EPS:
        result = clip(result, start, True)
    if end < length - EPS:
        result = clip(result, end, False)
    return result


def wall_span_polygon(
    wall: PlanWall,
    start: float,
    end: float,
    thickness_m: float | None = None,
    walls: list[PlanWall] | None = None,
    openings: list[PlanOpening] | None = None,
) -> Polygon:
    """Wall footprint between two offsets from wall.from; neighbours mitre full endpoints."""
    thickness = wall.thickness_m if thickness_m is None else thickness_m
    fx, fy = wall.from_
    length = wall_length(wall)
    ux, uy = (wall.to[0] - fx) / length, (wall.to[1] - fy) / length
    half = thickness / 2
    nx, ny = -uy * half, ux * half
    ring: Polygon = [
        (fx + ux * start + nx, fy + uy * start + ny),
        (fx + ux * end + nx, fy + uy * end + ny),
        (fx + ux * end - nx, fy + uy * end - ny),
        (fx + ux * start - nx, fy + uy * start - ny),
    ]
    if thickness != wall.thickness_m:
        return ring
    return _joined_wall_span(wall, ring, start, end, walls or [], openings or [])


def wall_obstacles(
    wall: PlanWall,
    openings: list[PlanOpening],
    interval: tuple[float, float],
    walls: list[PlanWall],
) -> list[Polygon]:
    """Solid parts of a wall for a height band: an opening clears only a band it covers."""
    base = max(0.0, interval[0])
    top = min(wall.height_m, interval[1])
    if not intervals_overlap((0.0, wall.height_m), interval):
        return []
    length = wall_length(wall)
    if length <= EPS:
        return []
    gaps = sorted(
        (
            (max(0.0, o.offset_m), min(length, o.offset_m + o.width_m))
            for o in openings
            if o.wallId == wall.id and o.sill_m <= base + EPS and o.sill_m + o.height_m >= top - EPS
        ),
        key=lambda gap: gap[0],
    )
    parts: list[Polygon] = []
    cursor = 0.0
    for start, end in gaps:
        if end - start <= EPS:
            continue
        if start - cursor > EPS:
            parts.append(wall_span_polygon(wall, cursor, start, None, walls, openings))
        cursor = max(cursor, end)
    if length - cursor > EPS:
        parts.append(wall_span_polygon(wall, cursor, length, None, walls, openings))
    return [part for part in parts if len(part) >= 3]


def opening_clearance(opening: PlanOpening, wall: PlanWall, depth_m: float) -> Polygon:
    """Floor in front of an opening: its span, depth_m out on both sides of the wall."""
    if wall_length(wall) <= EPS:
        return []
    end = opening.offset_m + opening.width_m
    return wall_span_polygon(wall, opening.offset_m, end, wall.thickness_m + 2 * depth_m)


def opening_centre(opening: PlanOpening, wall: PlanWall) -> Point:
    length = wall_length(wall)
    if length == 0:
        return wall.from_
    along = opening.offset_m + opening.width_m / 2
    return (
        wall.from_[0] + (wall.to[0] - wall.from_[0]) / length * along,
        wall.from_[1] + (wall.to[1] - wall.from_[1]) / length * along,
    )


def _collinear(a: Point, b: Point, c: Point) -> bool:
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return abs(cross) <= 1e-6 * max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]))


def _edge_index_of(wall: PlanWall, boundary: Polygon) -> int | None:
    count = len(boundary)
    for index in range(count):
        a, b = boundary[index], boundary[(index + 1) % count]
        if on_segment(wall.from_, a, b) and on_segment(wall.to, a, b):
            return index
    for start in range(count):
        first = (boundary[start], boundary[(start + 1) % count])
        if not on_segment(wall.from_, first[0], first[1]):
            continue
        for step in range(1, count):
            nxt = (boundary[(start + step) % count], boundary[(start + step + 1) % count])
            if not _collinear(first[0], first[1], nxt[1]):
                break
            if on_segment(wall.to, nxt[0], nxt[1]):
                return start
    return None


def outer_wall_ids(walls: list[PlanWall], boundary: Polygon) -> set[str]:
    """Walls that lie on an edge (or a straight run of edges) of the room outline."""
    return {wall.id for wall in walls if _edge_index_of(wall, boundary) is not None}
