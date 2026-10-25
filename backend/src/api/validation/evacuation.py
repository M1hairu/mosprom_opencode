"""Evacuation of the visitor hall (#30): G16 path to an exit, G17 exits and passages.

Norms: СП 1.13130.2020, secondary copy — check against the official text
(concept/05-safety.md, 4.2). The hall is Ф2.2; a zone with `fireBarrier` is a separate
Ф5.1 compartment: its floor is cut out of the hall grid, so no hall path starts in it
or runs through it.

Paths are measured on a grid of CELL_M cells around obstacles: walls (doors and
entrances cut out) and physical objects that stand on the floor. A cell is free when its
centre is inside the room and farther than CELL_M / 2 from every obstacle. The grid path
is shortened by line of sight, so a length is an estimate within a few centimetres.

A passage narrower than the norm is a gap between two obstacles. The checks seal every
such gap and look for floor that only narrow gaps connect to an exit.
"""

import heapq
import math
from dataclasses import dataclass

from api.contracts import Finding, FindingRef, PlanDocument, PlanWall
from api.validation.geometry import (
    EPS,
    Box,
    Point,
    Polygon,
    bounding_box,
    box_gap,
    footprint,
    locate_point,
    outer_wall_ids,
    point_polygon_distance,
    polygon_area,
    polygon_gap,
    segment_length,
    signed_area,
    wall_length,
    wall_span_polygon,
)
from api.validation.pochta import (
    NBSP,
    finding,
    format_length,
    format_short,
    is_physical,
    object_type,
    ref,
)
from api.validation.safety import edge_covered, fire_barrier

CELL_M = 0.25
# 250 000 cells: a room up to about 125 × 125 m is checked, a larger one is reported.
MAX_CELLS = 250_000
# табл. 5: Ф2.2, room volume up to 5 000 m³, building class С0 — 30 m.
FAR_LIMIT_M = 30.0
VOLUME_LIMIT_M3 = 5000.0
# п. 4.2.7: two exits for 50 people and more, and for a path longer than 25 m (not Ф5).
CROWD_EXITS = 50
TWO_EXITS_PATH_M = 25.0
# п. 4.2.19, 7.1.6: exit width at least 0.8 m, for 50 people and more at least 1.2 m.
EXIT_WIDTH_M = 0.8
EXIT_WIDTH_CROWD_M = 1.2
# п. 4.3.3: path width at least 1.2 m for more than 50 evacuees, otherwise at least 1.0 m.
CROWD_PATH = 50
PATH_WIDTH_M = 1.0
PATH_WIDTH_CROWD_M = 1.2
# Floor counts as a place for people when a circle of the minimum path width fits.
OCCUPIABLE_CLEARANCE_M = PATH_WIDTH_M / 2
# How many farthest grid cells are shortened by line of sight.
SMOOTH_CANDIDATES = 20
STRIP_M = 0.05
SOURCE = "СП 1.13130.2020"
CHECK_TEXT = "проверить по официальному тексту"
_DIAGONAL = math.sqrt(2)


@dataclass
class Obstacle:
    ref: FindingRef
    name: str  # instrumental case: «между <name> и <name>»
    ring: Polygon
    box: Box
    wall_id: str | None


def capacity(plan: PlanDocument) -> float | None:
    """extensions.safety.capacity: people in the hall at one time; None when absent."""
    safety = plan.extensions.get("safety")
    value = safety.get("capacity") if isinstance(safety, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def exits_of(plan: PlanDocument) -> list:
    """Doors and entrances in the walls on the room outline."""
    outer = outer_wall_ids(plan.walls, plan.room.boundary)
    return [o for o in plan.openings if o.kind != "window" and o.wallId in outer]


def validate_evacuation(plan: PlanDocument) -> list[Finding]:
    cap = capacity(plan)
    exits = exits_of(plan)
    crowd_exits = cap is None or cap >= CROWD_EXITS
    unknown = (
        " Вместимость не указана (extensions.safety.capacity): берём порог для 50 человек и более."
        if cap is None
        else ""
    )
    found: list[Finding] = []
    if not exits:
        found.append(
            finding(
                "EXITS_TOO_FEW",
                "error",
                "В помещении нет выхода: ни двери, ни входа в наружной стене "
                f"({SOURCE}, п. 4.2.7 — {CHECK_TEXT}).",
                [ref("room", plan.room.id)],
            )
        )
    elif len(exits) == 1 and crowd_exits:
        found.append(_one_exit(plan, exits, "при 50 людях и более нужно не меньше двух", unknown))

    need = EXIT_WIDTH_CROWD_M if crowd_exits else EXIT_WIDTH_M
    for opening in exits:
        if opening.width_m >= need - EPS:
            continue
        found.append(
            finding(
                "EXIT_TOO_NARROW",
                "error",
                f"Выход шириной {format_length(opening.width_m)} уже нормы {format_length(need)} "
                f"({SOURCE}, п. 4.2.19, 7.1.6: не меньше 0,8{NBSP}м, при 50 людях и более — "
                f"не меньше 1,2{NBSP}м; {CHECK_TEXT}).{unknown}",
                [ref("opening", opening.id)],
            )
        )
    if not exits:
        return found

    grid = Grid.of(plan)
    if grid is None:
        found.append(
            finding(
                "EVACUATION_NOT_CHECKED",
                "warning",
                f"Помещение больше {format_short(MAX_CELLS * CELL_M * CELL_M, 0)}{NBSP}м² по "
                "габариту: путь до выхода и ширина проходов не проверены.",
                [ref("room", plan.room.id)],
            )
        )
        return found

    crowd_path = cap is None or cap > CROWD_PATH
    width = PATH_WIDTH_CROWD_M if crowd_path else PATH_WIDTH_M
    obstacles = _obstacles(plan)
    grid.block(obstacles)
    grid.drop_compartments(plan)
    seeds = grid.seeds(plan, exits)
    dist, pred, source = grid.paths(grid.free, seeds)
    hall = [k for k, d in enumerate(dist) if d < math.inf]

    far = grid.farthest(hall, dist, pred, seeds, FAR_LIMIT_M)
    if far is not None:
        length, cell = far
        volume = polygon_area(plan.room.boundary) * plan.room.ceilingHeight_m
        big = (
            f" Объём помещения {format_short(volume, 0)}{NBSP}м³ больше 5000{NBSP}м³: порог "
            "проверить по табл. 5."
            if volume > VOLUME_LIMIT_M3
            else ""
        )
        found.append(
            finding(
                "EXIT_TOO_FAR",
                "error",
                f"От самой удалённой точки зала до ближайшего выхода около "
                f"{format_short(length, 1)}{NBSP}м при норме не более 30{NBSP}м ({SOURCE}, "
                f"табл. 5: Ф2.2, объём до 5000{NBSP}м³, класс С0; {CHECK_TEXT}).{big}",
                [ref("room", plan.room.id), ref("opening", exits[source[cell]].id)],
            )
        )
    if len(exits) == 1 and not crowd_exits:
        far25 = grid.farthest(hall, dist, pred, seeds, TWO_EXITS_PATH_M)
        if far25 is not None:
            found.append(
                _one_exit(
                    plan,
                    exits,
                    f"путь до него около {format_short(far25[0], 1)}{NBSP}м — больше "
                    f"25{NBSP}м, нужно не меньше двух",
                    "",
                )
            )

    found += grid.narrow_passages(
        plan, obstacles, seeds, dist, width, unknown if crowd_path else ""
    )
    return found


def _one_exit(plan: PlanDocument, exits: list, reason: str, unknown: str) -> Finding:
    return finding(
        "EXITS_TOO_FEW",
        "error",
        f"В помещении один выход, а {reason} ({SOURCE}, п. 4.2.7; {CHECK_TEXT}).{unknown}",
        [ref("room", plan.room.id), ref("opening", exits[0].id)],
    )


def _walk_pieces(wall: PlanWall, plan: PlanDocument) -> list[Polygon]:
    """Solid parts of a wall for a walking person: doors and entrances are cut out."""
    length = wall_length(wall)
    if length <= EPS:
        return []
    gaps = sorted(
        (max(0.0, o.offset_m), min(length, o.offset_m + o.width_m))
        for o in plan.openings
        if o.wallId == wall.id and o.kind != "window"
    )
    parts: list[Polygon] = []
    cursor = 0.0
    for start, end in gaps:
        if end - start <= EPS:
            continue
        if start - cursor > EPS:
            parts.append(wall_span_polygon(wall, cursor, start, None, plan.walls, plan.openings))
        cursor = max(cursor, end)
    if length - cursor > EPS:
        parts.append(wall_span_polygon(wall, cursor, length, None, plan.walls, plan.openings))
    return [part for part in parts if len(part) >= 3]


def _obstacles(plan: PlanDocument) -> list[Obstacle]:
    outer = outer_wall_ids(plan.walls, plan.room.boundary)
    found: list[Obstacle] = []
    for wall in plan.walls:
        name = "наружной стеной" if wall.id in outer else "перегородкой"
        for piece in _walk_pieces(wall, plan):
            found.append(Obstacle(ref("wall", wall.id), name, piece, bounding_box(piece), wall.id))
    for obj in plan.objects:
        kind = object_type(plan, obj.typeId)
        if not is_physical(plan, obj) or (kind is not None and not kind.occupiesFloor):
            continue
        ring = footprint(obj)
        found.append(
            Obstacle(ref("object", obj.id), f"«{obj.label}»", ring, bounding_box(ring), None)
        )
    # An outline edge without a wall still stops a person: a thin strip outside it.
    ring = plan.room.boundary
    outward = 1.0 if signed_area(ring) > 0 else -1.0
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        if edge_covered(plan, start, end):
            continue
        length = segment_length(start, end)
        nx = (end[1] - start[1]) / length * STRIP_M * outward
        ny = -(end[0] - start[0]) / length * STRIP_M * outward
        strip = [start, end, (end[0] + nx, end[1] + ny), (start[0] + nx, start[1] + ny)]
        found.append(
            Obstacle(
                ref("room", plan.room.id), "границей помещения", strip, bounding_box(strip), None
            )
        )
    return found


class Grid:
    def __init__(self, x0: float, y0: float, nx: int, ny: int) -> None:
        self.x0, self.y0, self.nx, self.ny = x0, y0, nx, ny
        self.free = bytearray(nx * ny)

    @classmethod
    def of(cls, plan: PlanDocument) -> "Grid | None":
        x0, y0, x1, y1 = bounding_box(plan.room.boundary)
        nx = max(1, math.ceil((x1 - x0) / CELL_M - EPS))
        ny = max(1, math.ceil((y1 - y0) / CELL_M - EPS))
        if nx * ny > MAX_CELLS:
            return None
        grid = cls(x0, y0, nx, ny)
        grid._fill(plan.room.boundary)
        return grid

    def centre(self, k: int) -> Point:
        return self.x0 + (k % self.nx + 0.5) * CELL_M, self.y0 + (k // self.nx + 0.5) * CELL_M

    def cell_of(self, p: Point) -> int | None:
        i = math.floor((p[0] - self.x0) / CELL_M)
        j = math.floor((p[1] - self.y0) / CELL_M)
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return j * self.nx + i
        return None

    def cells_in(self, box: Box, margin: float):
        i0 = max(0, math.floor((box[0] - margin - self.x0) / CELL_M - 0.5))
        i1 = min(self.nx - 1, math.ceil((box[2] + margin - self.x0) / CELL_M - 0.5))
        j0 = max(0, math.floor((box[1] - margin - self.y0) / CELL_M - 0.5))
        j1 = min(self.ny - 1, math.ceil((box[3] + margin - self.y0) / CELL_M - 0.5))
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                yield j * self.nx + i

    def _fill(self, ring: Polygon) -> None:
        """Cells whose centre is inside the room, by scanlines."""
        for j in range(self.ny):
            y = self.y0 + (j + 0.5) * CELL_M
            xs = []
            for index, a in enumerate(ring):
                b = ring[(index + 1) % len(ring)]
                if (a[1] > y) != (b[1] > y):
                    xs.append(a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0]))
            xs.sort()
            for left, right in zip(xs[::2], xs[1::2]):
                i0 = max(0, math.ceil((left - self.x0) / CELL_M - 0.5))
                i1 = min(self.nx - 1, math.floor((right - self.x0) / CELL_M - 0.5))
                for i in range(i0, i1 + 1):
                    self.free[j * self.nx + i] = 1

    def block(self, obstacles: list[Obstacle]) -> None:
        for obstacle in obstacles:
            for k in self.cells_in(obstacle.box, CELL_M / 2):
                if (
                    self.free[k]
                    and point_polygon_distance(self.centre(k), obstacle.ring) <= CELL_M / 2
                ):
                    self.free[k] = 0

    def neighbours(self, k: int, passable: bytearray):
        """8 neighbours with their step; a diagonal does not cut a blocked corner."""
        nx = self.nx
        i, j = k % nx, k // nx
        left = i > 0 and passable[k - 1]
        right = i < nx - 1 and passable[k + 1]
        down = j > 0 and passable[k - nx]
        up = j < self.ny - 1 and passable[k + nx]
        if left:
            yield k - 1, CELL_M
        if right:
            yield k + 1, CELL_M
        if down:
            yield k - nx, CELL_M
            if left and passable[k - nx - 1]:
                yield k - nx - 1, CELL_M * _DIAGONAL
            if right and passable[k - nx + 1]:
                yield k - nx + 1, CELL_M * _DIAGONAL
        if up:
            yield k + nx, CELL_M
            if left and passable[k + nx - 1]:
                yield k + nx - 1, CELL_M * _DIAGONAL
            if right and passable[k + nx + 1]:
                yield k + nx + 1, CELL_M * _DIAGONAL

    def seeds(self, plan: PlanDocument, exits: list) -> dict[int, tuple[float, int]]:
        """Free cells just inside each exit: cell → (distance to the opening, exit index)."""
        walls = {wall.id: wall for wall in plan.walls}
        seeds: dict[int, tuple[float, int]] = {}
        for index, opening in enumerate(exits):
            wall = walls[opening.wallId]
            length = wall_length(wall)
            ux, uy = (wall.to[0] - wall.from_[0]) / length, (wall.to[1] - wall.from_[1]) / length
            reach = wall.thickness_m / 2 + 1.5 * CELL_M
            box = bounding_box(
                [
                    (wall.from_[0] + ux * along, wall.from_[1] + uy * along)
                    for along in (opening.offset_m, opening.offset_m + opening.width_m)
                ]
            )
            for k in self.cells_in(box, reach):
                if not self.free[k]:
                    continue
                cx, cy = self.centre(k)
                dx, dy = cx - wall.from_[0], cy - wall.from_[1]
                along = dx * ux + dy * uy
                across = abs(dy * ux - dx * uy)
                inside = opening.offset_m < along < opening.offset_m + opening.width_m
                if not inside or across > reach:
                    continue
                if k not in seeds or across < seeds[k][0]:
                    seeds[k] = (across, index)
        return seeds

    def paths(self, passable: bytearray, seeds: dict[int, tuple[float, int]]):
        """Multi-source Dijkstra from the exits: distance, predecessor and exit of each cell."""
        size = self.nx * self.ny
        dist = [math.inf] * size
        pred = [-1] * size
        source = [-1] * size
        heap = []
        for k, (d0, index) in seeds.items():
            if passable[k]:
                dist[k], source[k] = d0, index
                heap.append((d0, k))
        heapq.heapify(heap)
        while heap:
            d, k = heapq.heappop(heap)
            if d > dist[k]:
                continue
            for n, step in self.neighbours(k, passable):
                if d + step < dist[n]:
                    dist[n], pred[n], source[n] = d + step, k, source[k]
                    heapq.heappush(heap, (d + step, n))
        return dist, pred, source

    def drop_compartments(self, plan: PlanDocument) -> None:
        """Floor of a fire compartment (Ф5.1) is not hall floor: no path starts or runs there."""
        for zone in plan.zones:
            if not fire_barrier(zone):
                continue
            for k in self.cells_in(bounding_box(zone.polygon), 0):
                if locate_point(self.centre(k), zone.polygon) != "outside":
                    self.free[k] = 0

    def _sight(self, a: int, b: int) -> bool:
        pa, pb = self.centre(a), self.centre(b)
        steps = max(1, math.ceil(segment_length(pa, pb) / (CELL_M / 4)))
        for s in range(1, steps):
            t = s / steps
            k = self.cell_of((pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t))
            if k is None or not self.free[k]:
                return False
        return True

    def _smoothed(self, k: int, pred: list[int], seeds: dict[int, tuple[float, int]]) -> float:
        """Length of the grid path from cell k to its exit, shortened by line of sight."""
        chain = [k]
        while pred[chain[-1]] != -1:
            chain.append(pred[chain[-1]])
        total = 0.0
        i, last = 0, len(chain) - 1
        while i < last:
            # The farthest chain cell in sight of chain[i]: gallop, then bisect.
            good, step = i + 1, 1
            while good + step <= last and self._sight(chain[i], chain[good + step]):
                good += step
                step *= 2
            bad = min(good + step, last + 1)
            while bad - good > 1:
                mid = (good + bad) // 2
                if self._sight(chain[i], chain[mid]):
                    good = mid
                else:
                    bad = mid
            total += segment_length(self.centre(chain[i]), self.centre(chain[good]))
            i = good
        return total + seeds[chain[-1]][0]

    def farthest(self, cells, dist, pred, seeds, limit: float) -> tuple[float, int] | None:
        """The farthest cell beyond `limit` after shortening, or None when none is."""
        candidates = sorted((k for k in cells if dist[k] > limit), key=lambda k: -dist[k])
        best: tuple[float, int] | None = None
        for k in candidates[:SMOOTH_CANDIDATES]:
            # A shortened path is never longer than the grid path: no later cell can win.
            if best is not None and dist[k] <= best[0]:
                break
            length = self._smoothed(k, pred, seeds)
            if length > limit and (best is None or length > best[0]):
                best = (length, k)
        return best

    def _clearance_at_least(self, p: Point, obstacles: list[Obstacle], need: float) -> bool:
        box = (p[0], p[1], p[0], p[1])
        return all(
            box_gap(box, o.box) >= need or point_polygon_distance(p, o.ring) >= need
            for o in obstacles
        )

    def _components(self, passable: bytearray, start_set) -> tuple[list[int], list[list[int]]]:
        label = [-1] * (self.nx * self.ny)
        groups: list[list[int]] = []
        for k in start_set:
            if label[k] != -1:
                continue
            label[k] = len(groups)
            group, stack = [], [k]
            while stack:
                c = stack.pop()
                group.append(c)
                for n, _ in self.neighbours(c, passable):
                    if label[n] == -1:
                        label[n] = len(groups)
                        stack.append(n)
            groups.append(group)
        return label, groups

    def narrow_passages(self, plan, obstacles, seeds, dist, width: float, unknown: str):
        """PASSAGE_TOO_NARROW and EXIT_UNREACHABLE: floor cut off by gaps below `width`."""
        bands = self._bands(obstacles, width)
        sealed = bytearray(self.nx * self.ny)
        for _, _, _, cells in bands:
            for k in cells:
                sealed[k] = 1
        wide = bytearray(f and not s for f, s in zip(self.free, sealed))
        wide_dist, _, _ = self.paths(wide, seeds)
        cut = bytearray(w and d == math.inf for w, d in zip(wide, wide_dist))
        label, groups = self._components(cut, (k for k, c in enumerate(cut) if c))
        found: list[Finding] = []
        kept = set()
        for index, group in enumerate(groups):
            spot = next(
                (
                    k
                    for k in group
                    if self._clearance_at_least(self.centre(k), obstacles, OCCUPIABLE_CLEARANCE_M)
                ),
                None,
            )
            if spot is None:
                continue
            if dist[group[0]] == math.inf:
                found.append(_unreachable(plan, self.centre(spot), len(group)))
                continue
            kept.add(index)
        reported = set()
        for a, b, gap, cells in bands:
            touches = set()
            outside = set()
            for k in cells:
                for n, _ in self.neighbours(k, self.free):
                    if sealed[n]:
                        continue
                    outside.add(label[n])
                    if label[n] in kept:
                        touches.add(label[n])
            if not any(outside - {t} for t in touches) or (a.ref.id, b.ref.id) in reported:
                continue
            reported.add((a.ref.id, b.ref.id))
            found.append(
                finding(
                    "PASSAGE_TOO_NARROW",
                    "error",
                    f"Проход между {a.name} и {b.name} шириной {format_length(gap)} уже нормы "
                    f"{format_length(width)}: за ним часть зала без пути к выходу нужной ширины "
                    f"({SOURCE}, п. 4.3.3: не меньше 1,0{NBSP}м, при числе эвакуируемых больше "
                    f"50 — не меньше 1,2{NBSP}м; {CHECK_TEXT}).{unknown}",
                    [a.ref, b.ref],
                )
            )
        return found

    def _bands(self, obstacles: list[Obstacle], width: float):
        """Free cells between two obstacles closer than `width`: d_a + d_b ≤ gap + 1.5 cells."""
        order = sorted(range(len(obstacles)), key=lambda i: obstacles[i].box[0])
        bands = []
        for pos, i in enumerate(order):
            a = obstacles[i]
            for j in order[pos + 1 :]:
                b = obstacles[j]
                if b.box[0] - a.box[2] >= width:
                    break
                if a.wall_id is not None and a.wall_id == b.wall_id:
                    continue  # a doorway: checked as an exit width
                if box_gap(a.box, b.box) >= width:
                    continue
                gap = polygon_gap(a.ring, b.ring)
                if gap is None or gap[0] <= EPS or gap[0] >= width - EPS:
                    continue
                reach = gap[0] + 1.5 * CELL_M
                box = (
                    max(a.box[0], b.box[0]) - reach,
                    max(a.box[1], b.box[1]) - reach,
                    min(a.box[2], b.box[2]) + reach,
                    min(a.box[3], b.box[3]) + reach,
                )
                cells = []
                for k in self.cells_in(box, 0):
                    if not self.free[k]:
                        continue
                    p = self.centre(k)
                    da = point_polygon_distance(p, a.ring)
                    if da < reach and da + point_polygon_distance(p, b.ring) <= reach:
                        cells.append(k)
                if cells:
                    first, second = (a, b) if i < j else (b, a)
                    bands.append((first, second, gap[0], cells))
        position = {id(obstacle): index for index, obstacle in enumerate(obstacles)}
        bands.sort(key=lambda band: (position[id(band[0])], position[id(band[1])]))
        return bands


def _unreachable(plan: PlanDocument, spot: Point, cells: int) -> Finding:
    area = cells * CELL_M * CELL_M
    holders = [z for z in plan.zones if locate_point(spot, z.polygon) != "outside"]
    holders.sort(key=lambda z: polygon_area(z.polygon))
    where = ref("zone", holders[0].id) if holders else ref("room", plan.room.id)
    return finding(
        "EXIT_UNREACHABLE",
        "error",
        f"Из части помещения площадью около {format_short(area, 1)}{NBSP}м² нет пути к выходу: "
        f"её закрывают стены или объекты. Путь до выхода нужен из любой точки помещения "
        f"({SOURCE}, табл. 5: от самой удалённой точки не более 30{NBSP}м; {CHECK_TEXT}).",
        [where],
    )
