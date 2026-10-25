#!/usr/bin/env python3
"""Наложение плана зала 219 (PlanDocument, метры) на схему слайда 6.

    python3 scripts/plan_overlay.py content/plan-219.json content/img/plan-219-overlay.png
    python3 scripts/plan_overlay.py content/plan-219-mirror.json \
        content/img/plan-219-mirror-overlay.png --mirror

Скрипт находит 8 колонн на task/img/floor-plan.png, совмещает с ними колонны плана
(один масштаб на обе оси, без поворота) и рисует план поверх схемы. С ключом --mirror
схема сначала отражается по горизонтали. Печатает шаг колонн, невязку совмещения и
совпадение стен с линиями схемы. Код выхода 1 — проверка не прошла (ловушка T2).

Цвета: синий — наружные стены, оранжевый пунктир — убираемые перегородки, красный —
перечёркнутые проёмы, зелёный — проёмы-входы, фиолетовый — колонны, голубой пунктир —
сетка плана 6 × 6 м. Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import zlib
from collections import deque
from pathlib import Path

COLUMN_PITCH_M = 12.0  # slide 6: 2 grid squares of 6 m (task/case.md)
PITCH_TOLERANCE_M = 0.5  # gate G7 / scenario S6.3
GRID_M = 6.0
MAX_RESIDUAL_M = 0.25
DEFAULT_IMAGE = "task/img/floor-plan.png"
UPSCALE = 2

Image = tuple[int, int, list[bytearray]]  # width, height, RGB rows

COLOR_OUTER = (20, 70, 220)
COLOR_REMOVABLE = (245, 130, 0)
COLOR_CROSSED = (220, 0, 0)
COLOR_ENTRANCE = (0, 160, 60)
COLOR_COLUMN = (150, 0, 200)
COLOR_GRID = (90, 170, 230)


# --- PNG codec (8-bit RGB / RGBA, not interlaced) -------------------------------------

def read_png(path: Path) -> Image:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat = 8, b""
    width = height = channels = 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or color not in (2, 6) or interlace != 0:
                raise ValueError(f"{path}: only 8-bit RGB/RGBA non-interlaced PNG is supported")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = width * channels
    rows: list[bytearray] = []
    prev = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        ftype = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        prev = line
        if channels == 4:
            line = bytearray(v for i, v in enumerate(line) if i % 4 != 3)
        rows.append(line)
    return width, height, rows


def write_png(path: Path, image: Image) -> None:
    width, height, rows = image
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    )


def pixel(image: Image, x: int, y: int) -> tuple[int, int, int]:
    row = image[2][y]
    return row[3 * x], row[3 * x + 1], row[3 * x + 2]


def mirrored(image: Image) -> Image:
    width, height, rows = image
    out = []
    for row in rows:
        triples = [row[3 * x:3 * x + 3] for x in range(width)]
        out.append(bytearray(b"".join(reversed(triples))))
    return width, height, out


def upscaled(image: Image, factor: int) -> Image:
    width, height, rows = image
    out = []
    for row in rows:
        wide = bytearray(b"".join(bytes(row[3 * x:3 * x + 3]) * factor for x in range(width)))
        out.extend(bytearray(wide) for _ in range(factor))
    return width * factor, height * factor, out


# --- what the slide shows ------------------------------------------------------------

def is_column_gray(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return abs(r - g) < 12 and abs(g - b) < 12 and 60 < r < 170


def is_line(rgb: tuple[int, int, int]) -> bool:
    """Wall ink on the slide: green outline and partitions, black top wall, gray columns."""
    r, g, b = rgb
    green = g - r > 40 and g - b > 20 and g < 200
    return green or r + g + b < 200 or is_column_gray(rgb)


def detect_columns(image: Image) -> list[tuple[float, float]]:
    """Centres (px) of gray round column signs: compact blobs about 20 px across."""
    width, height, _ = image
    seen = [bytearray(width) for _ in range(height)]
    found = []
    for y0 in range(height):
        for x0 in range(width):
            if seen[y0][x0] or not is_column_gray(pixel(image, x0, y0)):
                continue
            seen[y0][x0] = 1
            queue, xs, ys = deque([(x0, y0)]), [], []
            while queue:
                x, y = queue.popleft()
                xs.append(x)
                ys.append(y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < width and 0 <= ny < height and not seen[ny][nx] and is_column_gray(pixel(image, nx, ny)):
                        seen[ny][nx] = 1
                        queue.append((nx, ny))
            w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            if 14 <= w <= 28 and 14 <= h <= 28 and len(xs) >= 100:
                found.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    return found


def is_grid(rgb: tuple[int, int, int]) -> bool:
    """Faint dashed grid line of the slide: slightly darker than the pale green floor."""
    r, g, b = rgb
    return 640 <= r + g + b <= 715 and g > r + 10


def grid_square_px(image: Image, box: tuple[int, int, int, int]) -> float | None:
    """Side of one grid square (px), from the dashed grid lines inside `box` (x0, y0, x1, y1).

    Lines are pixel rows and columns where the grid colour covers > 20 % of the box.
    The lattice step is the most frequent distance between two lines in 100–200 px;
    partition edges and column axes give other distances and lose the vote.
    """
    x0, y0, x1, y1 = box
    rows = [y for y in range(y0, y1) if sum(is_grid(pixel(image, x, y)) for x in range(x0, x1)) > 0.2 * (x1 - x0)]
    cols = [x for x in range(x0, x1) if sum(is_grid(pixel(image, x, y)) for y in range(y0, y1)) > 0.2 * (y1 - y0)]

    def lines(values: list[int]) -> list[float]:
        groups: list[list[int]] = []
        for v in values:
            if groups and v - groups[-1][-1] <= 2:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [sum(g) / len(g) for g in groups]

    diffs = [
        b - a
        for found in (lines(rows), lines(cols))
        for i, a in enumerate(found)
        for b in found[i + 1:]
        if 100 <= b - a <= 200
    ]
    if not diffs:
        return None
    votes: dict[int, int] = {}
    for d in diffs:
        votes[round(d)] = votes.get(round(d), 0) + 1
    mode = max(votes, key=lambda k: (votes[k], -k))
    near = [d for d in diffs if abs(d - mode) <= 3]
    return sum(near) / len(near)


# --- plan geometry -------------------------------------------------------------------

def plan_columns(plan: dict) -> list[tuple[float, float]]:
    return [tuple(o["position"]) for o in plan["objects"] if o["typeId"] == "ot_column"]


def column_pitches(points: list[tuple[float, float]]) -> tuple[list[float], list[float]]:
    """Distances between neighbours inside a row (X) and inside a file of columns (Y)."""
    def groups(key: int) -> dict[float, list[float]]:
        out: dict[float, list[float]] = {}
        for p in points:
            out.setdefault(round(p[key], 1), []).append(p[1 - key])
        return out

    along_x = [b - a for vals in groups(1).values() for a, b in zip(sorted(vals), sorted(vals)[1:])]
    along_y = [b - a for vals in groups(0).values() for a, b in zip(sorted(vals), sorted(vals)[1:])]
    return along_x, along_y


def slide_pitches(pairs) -> tuple[list[float], list[float]]:
    """Pixel distances between neighbouring slide columns, grouped by the matched plan row and file."""
    rows: dict[float, list[float]] = {}
    files: dict[float, list[float]] = {}
    for (x, y), (u, v) in pairs:
        rows.setdefault(y, []).append(u)
        files.setdefault(x, []).append(v)
    along_x = [b - a for us in rows.values() for a, b in zip(sorted(us), sorted(us)[1:])]
    along_y = [b - a for vs in files.values() for a, b in zip(sorted(vs), sorted(vs)[1:])]
    return along_x, along_y


def pair_up(world: list[tuple[float, float]], image_px: list[tuple[float, float]]):
    """Match plan columns to slide columns: top row first, left to right (image Y grows down)."""
    w = sorted(world, key=lambda p: (-p[1], p[0]))
    i = sorted(image_px, key=lambda p: (round(p[1] / 40), p[0]))
    return list(zip(w, i))


def fit(pairs) -> tuple[float, float, float]:
    """Least squares u = ox + s*x, v = oy - s*y (one scale, Y flipped). Returns s, ox, oy."""
    n = len(pairs)
    mx = sum(p[0][0] for p in pairs) / n
    my = sum(p[0][1] for p in pairs) / n
    mu = sum(p[1][0] for p in pairs) / n
    mv = sum(p[1][1] for p in pairs) / n
    num = sum((x - mx) * (u - mu) - (y - my) * (v - mv) for (x, y), (u, v) in pairs)
    den = sum((x - mx) ** 2 + (y - my) ** 2 for (x, y), _ in pairs)
    s = num / den
    return s, mu - s * mx, mv + s * my


def wall_point(wall: dict, along: float) -> tuple[float, float]:
    (x1, y1), (x2, y2) = wall["from"], wall["to"]
    length = math.hypot(x2 - x1, y2 - y1)
    return x1 + (x2 - x1) * along / length, y1 + (y2 - y1) * along / length


def wall_length(wall: dict) -> float:
    (x1, y1), (x2, y2) = wall["from"], wall["to"]
    return math.hypot(x2 - x1, y2 - y1)


# --- drawing -------------------------------------------------------------------------

def put(image: Image, x: float, y: float, color, radius: int = 0) -> None:
    width, height, rows = image
    cx, cy = int(round(x)), int(round(y))
    for yy in range(cy - radius, cy + radius + 1):
        for xx in range(cx - radius, cx + radius + 1):
            if 0 <= xx < width and 0 <= yy < height:
                rows[yy][3 * xx:3 * xx + 3] = bytes(color)


def segment(image: Image, a, b, color, radius: int = 0, dash: int = 0) -> None:
    steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1])))
    for k in range(steps + 1):
        if dash and (k // dash) % 2:
            continue
        t = k / steps
        put(image, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, color, radius)


def circle(image: Image, centre, r: float, color) -> None:
    steps = max(16, int(2 * math.pi * r))
    for k in range(steps):
        t = 2 * math.pi * k / steps
        put(image, centre[0] + r * math.cos(t), centre[1] + r * math.sin(t), color, 1)


# --- main ----------------------------------------------------------------------------

def line_share(slide: Image, points: list[tuple[float, float]], reach: int = 3) -> float:
    width, height, _ = slide
    hits = 0
    for u, v in points:
        cu, cv = int(round(u)), int(round(v))
        if any(
            0 <= cu + dx < width and 0 <= cv + dy < height and is_line(pixel(slide, cu + dx, cv + dy))
            for dx in range(-reach, reach + 1)
            for dy in range(-reach, reach + 1)
        ):
            hits += 1
    return hits / max(1, len(points))


def run(plan_path: Path, out_path: Path, image_path: Path, mirror: bool) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    slide = read_png(image_path)
    if mirror:
        slide = mirrored(slide)
    failures: list[str] = []

    world = plan_columns(plan)
    found = detect_columns(slide)
    print(f"план: {plan_path}; схема: {image_path}{' (отражена по горизонтали)' if mirror else ''}")
    print(f"колонны: в плане {len(world)}, на схеме найдено {len(found)}")
    if len(world) != 8 or len(found) != 8:
        print("ОШИБКА: нужно 2 ряда по 4 колонны", file=sys.stderr)
        return 1

    pairs = pair_up(world, found)
    s, ox, oy = fit(pairs)
    to_px = lambda p: (ox + s * p[0], oy - s * p[1])  # noqa: E731

    img_x, img_y = slide_pitches(pairs)
    mean_x, mean_y = sum(img_x) / len(img_x), sum(img_y) / len(img_y)
    print(f"схема: шаг колонн по X {mean_x:.1f} px, по Y {mean_y:.1f} px")

    # Independent of the plan: the slide legend says 1 grid square = 6 m.
    xs = [p[0] for p in plan["room"]["boundary"]]
    ys = [p[1] for p in plan["room"]["boundary"]]
    u0, v1 = to_px((min(xs) + 0.5, min(ys) + 0.5))
    u1, v0 = to_px((max(xs) - 0.5, max(ys) - 0.5))
    square = grid_square_px(slide, (int(u0), int(v0), int(u1), int(v1)))
    if square is None:
        failures.append("сетка схемы не найдена")
        slide_x = slide_y = 0.0
    else:
        slide_x, slide_y = mean_x / square * GRID_M, mean_y / square * GRID_M
        print(
            f"сетка схемы: квадрат {square:.1f} px = {GRID_M:g} м ({square / GRID_M:.2f} px/м); "
            f"замер шага колонн по сетке: X {slide_x:.2f} м, Y {slide_y:.2f} м"
        )

    plan_x, plan_y = column_pitches(world)
    pitches = plan_x + plan_y
    print(
        f"план: шаг колонн по X {min(plan_x):.2f}–{max(plan_x):.2f} м, по Y {min(plan_y):.2f}–{max(plan_y):.2f} м "
        f"(норма {COLUMN_PITCH_M:g} ± {PITCH_TOLERANCE_M:g} м)"
    )
    for value in pitches + [slide_x, slide_y]:
        if abs(value - COLUMN_PITCH_M) > PITCH_TOLERANCE_M:
            failures.append(f"шаг колонн {value:.2f} м вне 12 ± 0,5 м")

    residuals = [math.dist(to_px(w), i) / s for w, i in pairs]
    print(f"совмещение по колоннам: {s:.2f} px/м; невязка колонн макс. {max(residuals):.3f} м")
    if max(residuals) > MAX_RESIDUAL_M:
        failures.append(f"невязка колонн {max(residuals):.3f} м > {MAX_RESIDUAL_M} м")

    width_m, depth_m = max(xs) - min(xs), max(ys) - min(ys)
    area = plan.get("extensions", {}).get("plan219", {}).get("area", {})
    print(
        f"зал по осям стен: {width_m:.2f} × {depth_m:.2f} м = {width_m * depth_m:.1f} м²; "
        f"площадь кейса {area.get('case_m2')} м² ({area.get('status')})"
    )
    if abs(width_m - 36) > 0.5 or abs(depth_m - 18) > 0.5:
        failures.append(f"зал {width_m:.2f} × {depth_m:.2f} м, ожидали ≈ 36 × 18 м")

    removable = set(plan.get("extensions", {}).get("plan219", {}).get("walls", {}).get("removableIds", []))
    gaps: dict[str, list[tuple[float, float]]] = {}
    for o in plan["openings"]:
        gaps.setdefault(o["wallId"], []).append((o["offset_m"], o["offset_m"] + o["width_m"]))
    column_px = [to_px(w) for w in world]
    for wall in plan["walls"]:
        length = wall_length(wall)
        samples = []
        for k in range(int(length / 0.1) + 1):
            along = k * 0.1
            if any(a - 0.2 <= along <= b + 0.2 for a, b in gaps.get(wall["id"], [])):
                continue
            u, v = to_px(wall_point(wall, along))
            if any(math.dist((u, v), c) < 0.6 * s for c in column_px):
                continue
            samples.append((u, v))
        share = line_share(slide, samples)
        kind = "перегородка, убираемая" if wall["id"] in removable else "контур"
        print(f"  стена {wall['id']:<10} {length:5.2f} м  {kind:<23} совпадает с линией схемы на {share:.0%}")
        if share < 0.9:
            failures.append(f"стена {wall['id']} совпадает с линией схемы на {share:.0%}")
    walls = {w["id"]: w for w in plan["walls"]}
    for o in plan["openings"]:
        wall = walls[o["wallId"]]
        inner = [
            to_px(wall_point(wall, o["offset_m"] + o["width_m"] * t / 10)) for t in range(3, 8)
        ]
        share = line_share(slide, inner, reach=0)
        print(f"  проём {o['id']:<11} {o['kind']:<8} {o['width_m']:.2f} м; линия стены в середине проёма: {share:.0%}")
        if share > 0.2:
            failures.append(f"проём {o['id']} не попал в разрыв стены на схеме")

    canvas = upscaled(slide, UPSCALE)
    up = lambda p: (to_px(p)[0] * UPSCALE, to_px(p)[1] * UPSCALE)  # noqa: E731
    for gx in range(0, int(width_m // GRID_M) + 1):
        segment(canvas, up((min(xs) + gx * GRID_M, min(ys))), up((min(xs) + gx * GRID_M, max(ys))), COLOR_GRID, 0, 6)
    for gy in range(0, int(depth_m // GRID_M) + 1):
        segment(canvas, up((min(xs), min(ys) + gy * GRID_M)), up((max(xs), min(ys) + gy * GRID_M)), COLOR_GRID, 0, 6)
    for wall in plan["walls"]:
        removable_wall = wall["id"] in removable
        segment(
            canvas, up(wall["from"]), up(wall["to"]),
            COLOR_REMOVABLE if removable_wall else COLOR_OUTER, 1, 8 if removable_wall else 0,
        )
    openings_meta = plan.get("extensions", {}).get("plan219", {}).get("openings", {})
    for o in plan["openings"]:
        wall = walls[o["wallId"]]
        crossed = openings_meta.get(o["id"], {}).get("crossedOutRed", False)
        segment(
            canvas, up(wall_point(wall, o["offset_m"])), up(wall_point(wall, o["offset_m"] + o["width_m"])),
            COLOR_CROSSED if crossed else COLOR_ENTRANCE, 3,
        )
    for o in plan["objects"]:
        if o["typeId"] == "ot_column":
            circle(canvas, up(o["position"]), o["size_m"][0] / 2 * s * UPSCALE, COLOR_COLUMN)
            put(canvas, *up(o["position"]), COLOR_COLUMN, 1)
    write_png(out_path, canvas)
    print(f"наложение: {out_path} ({out_path.stat().st_size // 1024} КБ)")

    if failures:
        for f in failures:
            print(f"ОШИБКА: {f}", file=sys.stderr)
        return 1
    print("итог: проверки T2 пройдены")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type=Path, help="PlanDocument JSON")
    parser.add_argument("out", type=Path, help="PNG с наложением")
    parser.add_argument("--image", type=Path, default=Path(DEFAULT_IMAGE), help="схема слайда 6")
    parser.add_argument("--mirror", action="store_true", help="отразить схему по горизонтали (для plan-219-mirror)")
    args = parser.parse_args()
    return run(args.plan, args.out, args.image, args.mirror)


if __name__ == "__main__":
    sys.exit(main())
