"""3D frames of hall 219 for concept/02-visual.md (tasks #27, #96).

Walls, openings, columns, zones and exhibits come from the zoned plan of #23
(content/plan-219-zoned.json, PlanDocument v1). Object types map to proxies in TYPE_KIND;
sizes are the plan sizes. The workshop behind the plan's workshop wall is an illustration
(concept/3d/workshop.json). Cameras, people and 3D-only facing: concept/3d/views.json.
A plan without zones (content/plan-219.json before #23) falls back to the draft
concept/3d/layout-draft.json.

Render all frames (Blender 5.x, CPU, Cycles):
    blender -b --python-exit-code 1 -P concept/3d/render_views.py -- [--only 01-vhod,07-obzor] [--samples 48]
Layout checks and the proxy table without Blender:
    python3 concept/3d/render_views.py --check-only [--table]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "content" / "plan-219-zoned.json"
DRAFT = ROOT / "concept" / "3d" / "layout-draft.json"
WORKSHOP = ROOT / "concept" / "3d" / "workshop.json"
VIEWS = ROOT / "concept" / "3d" / "views.json"
OUT = ROOT / "concept" / "img"

RED, DARK, GREY, LIGHT, WHITE, TEAL = "#DD191C", "#606060", "#868686", "#D9D9D9", "#FFFFFF", "#A7D1C8"
# TRAP-8: capacity is not actual annual output; geography is a historical count.
# Sources and their limits: research/notes/lassard_facts.md, section 1.
SCALE_FACTS = (("600+", "сотрудников"), ("14 400 м²", "площадей"), ("30+", "видов изделий"),
               ("до 400+", "мощность, ед./год\nТехнополис, 2023"), ("80 %", "локализация"))
SCALE_SOURCE = "Кейс, слайд 3 · Мощность: ЛАССАРД, 03.04.2023"
MAP_TITLE = "40 регионов · 2023"
MAP_SOURCE = "Поставки: TAdviser / mos.ru, 2023"
PERSON_H = 1.75
MAX_PNG_BYTES = 5 * 1024 * 1024
LIGHT_W, SKY_STRENGTH, VIEW_TRANSFORM, EXPOSURE = 450, 0.3, "Standard", -2.0

# PlanDocument typeId -> proxy kind. The proxy fills the plan size_m x height_m of the object.
TYPE_KIND = {
    "ot_vgf": "miniature", "ot_smart_base": "miniature", "ot_ls_fl9000": "miniature",
    "ot_ls_fl20000": "miniature", "ot_ndyag": "miniature", "ot_robot_cell": "miniature",
    "ot_multi_hero": "unit", "ot_cleaner_prom": "unit",
    "ot_showcase": "vitrine", "ot_wall_screen": "wall_screen", "ot_panel": "panel",
    "ot_welder_mini": "on_stand", "ot_graver_table": "on_stand",
    "ot_graver_portal": "portal", "ot_graver_3d": "engraver",
    "ot_clean_zone": "clean_zone", "ot_optical_table": "optical_table", "ot_kit_stand": "kit_stand",
    "ot_sim_desk": "desk", "ot_meeting_table": "meeting_table",
}
KIND_BY_ID = {"ex_laminar": "laminar"}  # ot_kit_stand is "МИРЭА или ламинарная станция"; the id decides
PANEL_CONTENT = {"ex_timeline": "timeline", "ex_map": "map", "ex_scale": "scale"}
# Item on a stand: (kind, w, d, h, source). The stand takes the rest of the plan height.
STAND_ITEM = {
    "ot_welder_mini": ("unit", 0.64, 0.4, 0.66, "F: 640 × 400 × 660 мм"),
    "ot_graver_table": ("open_engraver", 0.527, 0.6, 0.825,
                        "F: ширина 524–527, высота 825 мм; глубина 0,6 м — оценка"),
}
# D-001 (#152, #193): large equipment stands in the hall only as a 1:5 model on a plinth under
# glass. typeId -> (kind of the full-size proxy, full width, depth, height in m, source).
# The plan size of the object is the plinth: the model + 0.1 m on each side (team estimate).
MINI_SCALE, MINI_PLINTH_M = 0.2, 0.9
MINIATURE = {
    "ot_smart_base": ("machine", 1.75, 1.75, 2.2, "F: SMART BASE 1750 × 1750 × 2200 мм, не поле 800 × 800 (TRAP-3)"),
    "ot_vgf": ("machine", 1.5, 1.5, 2.5, "EST: габарит «Листопад» не опубликован"),
    "ot_ls_fl9000": ("unit", 0.8, 1.1, 1.2, "F: LS-FL9000 800 × 1100 × 1200 мм"),
    "ot_ls_fl20000": ("unit", 1.5, 1.2, 1.62, "F: LS-FL20000 1500 × 1200 × 1620 мм"),
    "ot_ndyag": ("unit", 0.933, 0.296, 0.149, "F: лазер Nd:YAG 933 × 296 × 149 мм"),
    "ot_robot_cell": ("robot_cell", 3.0, 3.0, 2.2, "EST: габарит ячейки не опубликован, 3 × 3 × 2,2 м"),
}
# Sign on the fence of the demo zone part: no laser, no admission rule (D-001).
DEMO_FENCE_SIGN = "ДЕМО-ЗОНА · ЛУЧА НЕТ"
EXHIBIT_BY_ZONE = {
    "crystals": {"shape": "wafers", "d": 0.1, "src": "F: подложки GaAs Ø100 мм"},
    "quantrons": {"shape": "box", "w": 0.3, "d": 0.1, "h": 0.1, "src": "EST: габарит квантрона не опубликован"},
    "diodes": {"shape": "box", "w": 0.2, "d": 0.1, "h": 0.05, "src": "EST: габарит диодного модуля не опубликован"},
    "engraving": {"shape": "plates", "src": "EST: образцы гравировки"},
}
ZONE_STYLE = {"zt_entrance": "entry", "zt_view": "glass", "zt_meeting": "talks", "zt_demo": "test",
              "zt_edu": "zone", "zt_expo": "zone"}
FACES = {"S": (0, -1), "E": (1, 0), "N": (0, 1), "W": (-1, 0)}
GLASS_KINDS = ("glass", "window")
PERIMETER = ("w_south", "w_east", "w_north", "w_west")


# ---------------------------------------------------------------- layout (no bpy)

def parse_args() -> argparse.Namespace:
    in_blender = "bpy" in sys.modules
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = [] if in_blender else sys.argv[1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default=str(PLAN), help="PlanDocument (default: content/plan-219-zoned.json)")
    ap.add_argument("--draft", default=str(DRAFT))
    ap.add_argument("--workshop", default=str(WORKSHOP))
    ap.add_argument("--views", default=str(VIEWS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", default="", help="comma-separated view ids")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--res", default="1920x1080")
    ap.add_argument("--check-only", action="store_true", help="layout checks, no render")
    ap.add_argument("--table", action="store_true", help="print the proxy table (markdown)")
    ap.add_argument("--save-blend", default="", help="also save the scene as .blend")
    return ap.parse_args(argv)


def apply_facing(o: dict, side: str) -> dict:
    """Turn the object front to side N/S/E/W without changing its plan footprint: only
    +180 deg, or +-90 deg with width and depth swapped. The plan has no front; views.json sets it."""
    fx, fy = FACES[side]
    # An angle that is not a multiple of 90 deg would change the plan footprint (axis box).
    assert o.get("rotation_deg", 0) % 90 == 0, f"{o.get('id')}: rotation_deg {o.get('rotation_deg')} is not a multiple of 90"
    best = None
    for k in range(4):
        rot = (o.get("rotation_deg", 0) + 90 * k) % 360
        a = math.radians(rot)
        dot = math.sin(a) * fx - math.cos(a) * fy  # front = local -Y, see to_world
        if best is None or dot > best[0] + 1e-9:
            best = (dot, k, rot)
    _, k, rot = best
    w, d = o["size_m"]
    return dict(o, rotation_deg=rot, size_m=[w, d] if k % 2 == 0 else [d, w])


def load_layout(plan_path: Path, draft_path: Path, workshop_path: Path = WORKSHOP,
                facing: dict | None = None) -> dict:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    columns = [o for o in plan["objects"] if o.get("typeId") == "ot_column"]
    ext = plan.get("extensions", {})
    side = ext.get("plan219", {}).get("workshop", {}).get("wallId", "")
    if not plan.get("zones"):
        draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
        walls = [w for w in plan["walls"] if w["id"] not in set(draft["removeWalls"])]
        return {"source": "draft", "room": plan["room"], "walls": walls,
                "openings": plan["openings"] + draft["openings"], "columns": columns, "glassWalls": [],
                "zones": draft["zones"], "objects": draft["objects"],
                "workshopSide": draft["workshopSide"], "workshop": draft["workshop"]}
    # After #23: zones and objects come from the plan (PlanDocument); the draft is not used.
    zoning = ext.get("zoning219", {})
    zext = zoning.get("zones", {})
    zones = []
    for z in plan["zones"]:
        pts = z.get("boundary") or z.get("polygon") or []
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        attrs = z.get("attributes", {})
        row = zext.get(z["id"], {}).get("slide3Row")
        style = attrs.get("style3d") or ZONE_STYLE.get(z.get("typeId"), "zone")
        if style == "zone" and row in (1, 2, 3, 4):
            style = "chain"  # zones 1-4 of slide 3: the component cycle
        number = attrs.get("number", row)
        zones.append({"id": z["id"], "label": z.get("label") or z.get("name", z["id"]),
                      "number": str(number) if number else "", "rect": [min(xs), min(ys), max(xs), max(ys)],
                      "style": style,
                      "badge": attrs.get("badge") or ""})
    catalog = {t["id"]: t for t in plan.get("catalog", {}).get("objectTypes", [])}
    facing = facing or {}
    objects = []
    for o in plan["objects"]:
        if o.get("typeId") == "ot_column":
            continue
        attrs = o.get("attributes", {})
        t = o.get("typeId", "")
        cat = catalog.get(t, {})
        kind = attrs.get("kind3d") or KIND_BY_ID.get(o["id"]) or TYPE_KIND.get(t, "box")
        ob = {"id": o["id"], "typeId": t, "kind": kind, "label": o.get("label") or cat.get("label", o["id"]),
              "zoneId": o.get("zoneId"), "position": o["position"], "size_m": list(o["size_m"]),
              "height_m": o.get("height_m") or cat.get("defaultHeight_m", 1.0), "base_m": o.get("base_m", 0),
              "rotation_deg": plan_rotation(o.get("rotation_deg", 0)),
              "src": attrs.get("source") or cat.get("provenance") or "план #23"}
        if kind == "vitrine":
            ob["exhibit"] = EXHIBIT_BY_ZONE.get(o.get("zoneId"), {})
        if kind == "on_stand":
            ob["item"] = STAND_ITEM[t]
        if kind == "miniature":
            ob["model"] = MINIATURE[t]
        if kind == "panel":
            ob["content"] = PANEL_CONTENT.get(o["id"], "")
        if o["id"] in facing:
            ob = apply_facing(ob, facing[o["id"]])
        objects.append(ob)
    workshop = json.loads(Path(workshop_path).read_text(encoding="utf-8"))
    if workshop.get("wallId") != side:
        print(f"[3d] цех в {Path(workshop_path).name} стоит у {workshop.get('wallId')!r}, план ставит цех у "
              f"{side!r}: цех не строю")
        workshop = dict(workshop, objects=[])
    glass_walls = [wid for wid, txt in zoning.get("walls", {}).items() if str(txt).startswith("стекло")]
    return {"source": "plan", "room": plan["room"], "walls": plan["walls"], "openings": plan["openings"],
            "columns": columns, "glassWalls": glass_walls, "zones": zones, "objects": objects,
            "workshopSide": side, "workshop": workshop}


def plan_rotation(deg: float) -> float:
    """PlanDocument turns clockwise (web/src/planner/geometry.ts); this script turns
    counter-clockwise, like layout-draft.json and Blender. Same picture, opposite sign."""
    return (-deg) % 360


def to_world(o: dict, lx: float, ly: float) -> tuple[float, float]:
    """Local offset of an object -> plan X/Y. Rotation is counter-clockwise; the front is local -Y."""
    cx, cy = o["position"]
    a = math.radians(o.get("rotation_deg", 0))
    c, s = math.cos(a), math.sin(a)
    return cx + lx * c - ly * s, cy + lx * s + ly * c


def footprint(pos, size, rot_deg) -> tuple[float, float, float, float]:
    """Axis-aligned box of a rotated rectangle: (x0, y0, x1, y1)."""
    a = math.radians(rot_deg)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    hw = (size[0] * c + size[1] * s) / 2
    hd = (size[0] * s + size[1] * c) / 2
    return (pos[0] - hw, pos[1] - hd, pos[0] + hw, pos[1] + hd)


def overlap(a, b, tol=0.01) -> bool:
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


def inside(a, b, tol=0.01) -> bool:
    return a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol and a[3] <= b[3] + tol


def wall_box(w) -> tuple[float, float, float, float]:
    (x0, y0), (x1, y1) = w["from"], w["to"]
    t = w["thickness_m"] / 2
    return (min(x0, x1) - t, min(y0, y1) - t, max(x0, x1) + t, max(y0, y1) + t)


def room_box(lay: dict) -> tuple[float, float, float, float]:
    room = lay["room"]["boundary"]
    return (min(p[0] for p in room), min(p[1] for p in room), max(p[0] for p in room), max(p[1] for p in room))


def workshop_rect(lay: dict):
    """Workshop floor (x0, y0, x1, y1) behind the workshop wall, or None if the side is not supported."""
    rx0, ry0, rx1, ry1 = room_box(lay)
    depth = lay["workshop"]["depth_m"]
    if lay["workshopSide"] == "w_north":
        return (rx0, ry1, rx1, ry1 + depth)
    if lay["workshopSide"] == "w_west":
        return (rx0 - depth, ry0, rx0, ry1)
    return None


def in_room(lay: dict, pos) -> bool:
    rx0, ry0, rx1, ry1 = room_box(lay)
    return rx0 <= pos[0] <= rx1 and ry0 <= pos[1] <= ry1


def check_layout(lay: dict, people: list) -> list[str]:
    """Footprints must not cross each other, columns or walls; stacked items stay on their base."""
    errors = []
    rx0, ry0, rx1, ry1 = room_box(lay)
    zones = {z["id"]: z for z in lay["zones"]}
    items = {}
    for o in lay["objects"]:
        items[o["id"]] = (footprint(o["position"], o["size_m"], o.get("rotation_deg", 0)), o)
    floor = []  # things standing on the floor
    for oid, (fp, o) in items.items():
        if o.get("on"):
            if o["on"] not in items or not inside(fp, items[o["on"]][0]):
                errors.append(f"{oid}: не лежит на {o.get('on')}")
            continue
        if o.get("inside"):
            if o["inside"] not in items or not inside(fp, items[o["inside"]][0]):
                errors.append(f"{oid}: выходит за {o.get('inside')}")
        floor.append((oid, fp, o.get("inside")))
        if not (fp[0] >= rx0 + 0.07 and fp[1] >= ry0 + 0.07 and fp[2] <= rx1 - 0.07 and fp[3] <= ry1 - 0.07):
            errors.append(f"{oid}: выходит за контур зала")
        z = zones.get(o.get("zoneId"))
        if z and not inside(fp, z["rect"], tol=0.05):
            errors.append(f"{oid}: выходит за зону {z['id']}")
    for p in people:
        if not in_room(lay, p["position"]):  # workshop people are checked with the workshop
            continue
        fp = footprint(p["position"], (0.5, 0.35), p.get("rotation_deg", 0))
        if p.get("inside"):
            if p["inside"] not in items or not inside(fp, items[p["inside"]][0]):
                errors.append(f"{p['id']}: выходит за {p['inside']}")
        floor.append((p["id"], fp, p.get("inside")))
    obstacles = [(c["id"], footprint(c["position"], c["size_m"], 0)) for c in lay["columns"]]
    obstacles += [(w["id"], wall_box(w)) for w in lay["walls"] if w["id"] not in PERIMETER]
    for i, (a, fa, ina) in enumerate(floor):
        for b, fb, inb in floor[i + 1:]:
            if ina == b or inb == a:
                continue
            if overlap(fa, fb):
                errors.append(f"{a} пересекает {b}")
        for b, fb in obstacles:
            if overlap(fa, fb):
                errors.append(f"{a} пересекает {b}")
    # workshop: inside its box, no crossings
    ws = lay["workshop"]
    wr = workshop_rect(lay)
    wfloor = [(o["id"], footprint(o["position"], o["size_m"], o.get("rotation_deg", 0))) for o in ws["objects"]]
    wfloor += [(p["id"], footprint(p["position"], (0.5, 0.35), p.get("rotation_deg", 0)))
               for p in people if not in_room(lay, p["position"])]
    if wfloor and wr is None:
        errors.append(f"цех у {lay['workshopSide']!r}: такую сторону скрипт не строит")
        return errors
    if wr:
        wbox = (wr[0] + 0.1, wr[1] + 0.1, wr[2] - 0.1, wr[3] - 0.1)
        for i, (a, fa) in enumerate(wfloor):
            if not inside(fa, wbox):
                errors.append(f"{a}: выходит за цех")
            for b, fb in wfloor[i + 1:]:
                if overlap(fa, fb):
                    errors.append(f"{a} пересекает {b}")
    return errors


SRC_TEXT = {"F": "research/notes/lassard_facts.md, §2-3", "C": "research/notes/costs_timelines.md",
            "EST": "оценка"}


def src_text(src: str) -> str:
    key, sep, rest = src.partition(":")
    if key.strip() not in SRC_TEXT:
        return src
    base = SRC_TEXT[key.strip()]
    return f"{base}: {rest.strip()}" if rest.strip() else base


def dims(w: float, d: float, h: float) -> str:
    return f"{w * 1000:.0f} × {d * 1000:.0f} × {h * 1000:.0f}"


def proxy_table(lay: dict) -> str:
    """One row per object type (plan) or per object (draft), then the 3D-only parts."""
    rows = ["| Объект | Зона | Ш × Г × В, мм | Источник размера |", "|---|---|---|---|"]
    groups: dict[str, list] = {}
    for o in lay["objects"]:
        if o["kind"] == "label":
            continue
        # Same type with another footprint (ex_laminar vs ex_mirea) gets its own row.
        groups.setdefault((o.get("typeId") or o["id"], tuple(sorted(o["size_m"]))), []).append(o)
    split = {k[0] for k in groups if sum(1 for j in groups if j[0] == k[0]) > 1}
    extra = []
    for objs in groups.values():
        o = objs[0]
        w, d = max(o["size_m"]), min(o["size_m"])
        label = o["label"] + (f" ({len(objs)} шт.)" if len(objs) > 1 else "")
        if (o.get("typeId") or o["id"]) in split:
            label += " [" + ", ".join(x["id"] for x in objs) + "]"
        zones = ", ".join(sorted({x.get("zoneId") or "" for x in objs}))
        rows.append(f"| {label} | {zones} | {dims(w, d, o['height_m'])} | {src_text(o.get('src', 'EST'))} |")
        if o.get("item"):
            kind, iw, idp, ih, src = o["item"]
            extra.append(f"| {o['label']}: изделие на подставке; подставка — остаток высоты | {zones} | "
                         f"{dims(iw, idp, ih)} | {src_text(src)} |")
        if o.get("model"):
            _kind, mw, md, mh, src = o["model"]
            s = MINI_SCALE
            extra.append(f"| {o['label']}: модель 1:5 на подиуме {MINI_PLINTH_M * 1000:.0f} мм | {zones} | "
                         f"{dims(mw * s, md * s, mh * s)} | {src_text(src)} |")
        ex = o.get("exhibit") or {}
        if ex.get("src"):
            extra.append(f"| Образцы в витрине | {o.get('zoneId')} | {ex.get('shape')} | {src_text(ex['src'])} |")
    for o in lay["workshop"]["objects"]:
        extra.append(f"| {o['label']} | цех | {dims(o['size_m'][0], o['size_m'][1], o['height_m'])} | "
                     f"{src_text(o.get('src', 'EST'))} |")
    rows += extra
    rows.append(f"| Фигура человека | все кадры | 500 × 350 × {PERSON_H * 1000:.0f} | оценка: рост 1,75 м |")
    return "\n".join(rows)


def model_name(label: str) -> str:
    m = re.search(r"[A-Z][A-Z0-9-]+(?: [A-Z0-9][A-Z0-9×-]*)*", label)
    return m.group(0) if m else ""


# ---------------------------------------------------------------- scene (bpy)

def build_and_render(args, lay: dict, views: dict) -> int:
    import bmesh
    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    coll = scene.collection
    H = lay["room"]["ceilingHeight_m"]
    mats: dict[str, object] = {}

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def rgb(hexstr: str) -> tuple:
        h = hexstr.lstrip("#")
        return tuple(lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)

    def mat(name, color, rough=0.5, metal=0.0, emit=None, strength=0.0):
        if name in mats:
            return mats[name]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = rgb(color)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if emit:
            bsdf.inputs["Emission Color"].default_value = rgb(emit)
            bsdf.inputs["Emission Strength"].default_value = strength
        mats[name] = m
        return m

    def glass(name, tint="#FFFFFF", gloss=0.08):
        if name in mats:
            return mats[name]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        tr.inputs["Color"].default_value = rgb(tint)
        gl = nt.nodes.new("ShaderNodeBsdfGlossy")
        gl.inputs["Roughness"].default_value = 0.03
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = gloss
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(gl.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        mats[name] = m
        return m

    M = {
        "wall": mat("wall", "#F2F2F2", 0.8),
        "floor": mat("floor", "#CDCDCD", 0.35),
        "ws_floor": mat("ws_floor", "#9C9C9C", 0.5),
        "ceiling": mat("ceiling", "#EDEDED", 0.9),
        "column": mat("column", "#BDBDBD", 0.7),
        "white": mat("white", WHITE, 0.4),
        "red": mat("red", RED, 0.45),
        "dark": mat("dark", DARK, 0.5),
        "grey": mat("grey", GREY, 0.5),
        "light": mat("light", LIGHT, 0.6),
        "teal": mat("teal", TEAL, 0.6),
        "black": mat("black", "#1A1A1A", 0.15),
        "steel": mat("steel", "#B8BCC0", 0.25, 0.9),
        "gaas": mat("gaas", "#55595E", 0.15, 0.9),
        "display": mat("display", "#1C2A38", 0.2, 0.0, "#2E4A66", 1.2),
        "lamp_off": mat("lamp_off", "#7A1214", 0.4),
        "fixture": mat("fixture", WHITE, 0.5, 0.0, WHITE, 6.0),
        "person": mat("person", "#4A5058", 0.6),
        "door": mat("door", "#8C8F92", 0.5),
        "fence": mat("fence", "#C9CCCE", 0.85),
        "glass": glass("glass", "#F4FBFA", 0.08),
        "lp_glass": glass("lp_glass", "#FFD54A", 0.1),
        "poly": glass("poly", "#F0F4F4", 0.05),
    }

    def link(ob, grp="obj", wall=""):
        ob["grp"] = grp
        ob["wall"] = wall
        coll.objects.link(ob)
        return ob

    def box(name, cx, cy, z0, w, d, h, rot_deg, material, grp="obj", wall=""):
        hw, hd = w / 2, d / 2
        verts = [(-hw, -hd, 0), (hw, -hd, 0), (hw, hd, 0), (-hw, hd, 0),
                 (-hw, -hd, h), (hw, -hd, h), (hw, hd, h), (-hw, hd, h)]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.materials.append(material)
        ob = bpy.data.objects.new(name, me)
        ob.location = (cx, cy, z0)
        ob.rotation_euler = (0, 0, math.radians(rot_deg))
        return link(ob, grp, wall)

    def cyl(name, cx, cy, z0, r, h, material, seg=24, rot=(0, 0, 0), grp="obj"):
        verts = [(r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z)
                 for z in (0, h) for i in range(seg)]
        faces = [tuple(range(seg - 1, -1, -1)), tuple(range(seg, 2 * seg))]
        faces += [(i, (i + 1) % seg, seg + (i + 1) % seg, seg + i) for i in range(seg)]
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        for p in me.polygons:
            p.use_smooth = len(p.vertices) == 4
        me.materials.append(material)
        ob = bpy.data.objects.new(name, me)
        ob.location = (cx, cy, z0)
        ob.rotation_euler = rot
        return link(ob, grp)

    def sphere(name, cx, cy, cz, r, material):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=r)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(material)
        ob = bpy.data.objects.new(name, me)
        ob.location = (cx, cy, cz)
        return link(ob)

    def tri(name, pts, material):
        me = bpy.data.meshes.new(name)
        me.from_pydata(pts, [], [(0, 1, 2)])
        me.materials.append(material)
        return link(bpy.data.objects.new(name, me))

    def text(body, x, y, z, size, rot_deg, material, upright=True, align="CENTER", name="txt"):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.size = size
        cu.align_x = align
        cu.align_y = "CENTER"
        cu.extrude = 0.002
        cu.materials.append(material)
        ob = bpy.data.objects.new(name, cu)
        ob.location = (x, y, z)
        ob.rotation_euler = (math.radians(90) if upright else 0, 0, math.radians(rot_deg))
        return link(ob)

    def frame(o):
        def at(lx, ly):
            return to_world(o, lx, ly)
        return at, o.get("rotation_deg", 0)

    def part(o, lx, ly, z0, w, d, h, material, tag="p"):
        at, rot = frame(o)
        x, y = at(lx, ly)
        return box(f"{o['id']}_{tag}", x, y, z0, w, d, h, rot, material)

    def front_text(o, body, lx, z, size, material, back=False):
        at, rot = frame(o)
        ly = (o["size_m"][1] / 2 + 0.004) * (1 if back else -1)
        x, y = at(lx, ly)
        return text(body, x, y, z, size, rot + (180 if back else 0), material, name=f"{o['id']}_t")

    # ---- object kinds: every part stays inside size_m x height_m
    def k_machine(o):
        w, d = o["size_m"]
        h, b = o["height_m"], o.get("base_m", 0)
        part(o, 0, 0, b, w, d, 0.12, M["dark"], "plinth")
        part(o, 0, 0.01, b + 0.12, w - 0.02, d - 0.02, h - 0.12, M["white"], "body")
        part(o, 0, -d / 2 + 0.005, b + h * 0.42, w * 0.6, 0.01, h * 0.3, M["black"], "window")
        part(o, 0, -d / 2 + 0.005, b + h * 0.8, w - 0.02, 0.01, 0.07, M["red"], "stripe")
        for sx in (-1, 1):
            part(o, sx * (w / 2 - 0.005), 0.01, b + h * 0.8, 0.01, d - 0.02, 0.07, M["red"], "stripe_s")
        part(o, w * 0.32, -d / 2 + 0.005, b + h * 0.42, w * 0.14, 0.01, h * 0.22, M["dark"], "panel")
        name = model_name(o["label"])
        if name:
            front_text(o, name, 0, b + h * 0.9, min(0.12, w * 0.07), M["dark"])
    def k_unit(o):
        w, d = o["size_m"]
        h, b = o["height_m"], o.get("base_m", 0)
        if h < 0.3:  # case
            part(o, 0, 0, b, w, d, h, M["dark"], "body")
            part(o, 0, -d / 2 + 0.005, b + h * 0.6, w - 0.02, 0.01, 0.025, M["red"], "stripe")
            return
        base = min(0.06, h * 0.1)
        part(o, 0, 0, b, w, d, base, M["dark"], "base")
        part(o, 0, 0.01, b + base, w - 0.02, d - 0.02, h - base, M["white"], "body")
        part(o, 0, -d / 2 + 0.005, b + h * 0.45, w * 0.7, 0.01, h * 0.4, M["light"], "panel")
        part(o, 0, -d / 2 + 0.005, b + h * 0.35, w - 0.02, 0.01, 0.04, M["red"], "stripe")
        name = model_name(o["label"])
        if name and h > 0.5:
            front_text(o, name, 0, b + h * 0.65, min(0.08, w * 0.08), M["dark"])

    def k_engraver(o):
        w, d = o["size_m"]
        h = o["height_m"]
        part(o, 0, 0, 0, w, d, 0.75, M["white"], "cab")
        part(o, 0, 0, 0.75, w, d, 0.04, M["red"], "stripe")
        part(o, 0, 0.01, 0.79, w - 0.02, d - 0.02, h - 0.79, M["white"], "head")
        part(o, 0, -d / 2 + 0.005, 0.9, w * 0.7, 0.01, 0.45, M["black"], "window")
        part(o, 0, -d / 2 + 0.005, 0.06, w - 0.1, 0.01, 0.6, M["light"], "door")
        name = model_name(o["label"])
        if name:
            front_text(o, name, 0, h - 0.12, 0.06, M["dark"])

    def k_open_engraver(o):
        w, d = o["size_m"]
        h, b = o["height_m"], o.get("base_m", 0)
        part(o, 0, 0, b, w, d, 0.04, M["dark"], "plate")
        part(o, 0, d / 2 - 0.06, b + 0.04, 0.08, 0.08, h - 0.04, M["grey"], "post")
        part(o, 0, d / 2 - 0.3, b + h - 0.25, 0.18, 0.24, 0.2, M["white"], "head")
        part(o, 0, d / 2 - 0.3, b + h - 0.27, 0.06, 0.06, 0.02, M["red"], "lens")

    def k_cabin(o):
        w, d = o["size_m"]
        h, t = o["height_m"], 0.06
        win_w, win_z0, win_z1, win_x = min(1.6, w * 0.4), 1.0, 2.0, -w * 0.15
        hx = w / 2
        # front wall (-y) with a laser-protective window
        hw_ = h - t  # walls stop under the roof
        part(o, (-hx + win_x - win_w / 2) / 2, -d / 2 + t / 2, 0, (win_x - win_w / 2) + hx, t, hw_, M["light"], "f1")
        part(o, (win_x + win_w / 2 + hx) / 2, -d / 2 + t / 2, 0, hx - (win_x + win_w / 2), t, hw_, M["light"], "f2")
        part(o, win_x, -d / 2 + t / 2, 0, win_w, t, win_z0, M["light"], "f3")
        part(o, win_x, -d / 2 + t / 2, win_z1, win_w, t, hw_ - win_z1, M["light"], "f4")
        part(o, win_x, -d / 2 + t / 2, win_z0, win_w, 0.02, win_z1 - win_z0, M["lp_glass"], "win")
        part(o, 0, d / 2 - t / 2, 0, w, t, hw_, M["light"], "back")
        part(o, -hx + t / 2, 0, 0, t, d - 2 * t, hw_, M["light"], "left")
        part(o, hx - t / 2, 0, 0, t, d - 2 * t, hw_, M["light"], "right")
        part(o, 0, 0, hw_, w, d, t, M["light"], "roof")
        part(o, hx - 0.005, -d * 0.15, 0.02, 0.01, 0.9, 2.1, M["dark"], "door")
        part(o, 0, -d / 2 + 0.005, h - 0.4, w - 0.02, 0.01, 0.08, M["red"], "stripe")
        part(o, hx - 0.25, -d / 2 + 0.15, h, 0.12, 0.12, 0.08, M["lamp_off"], "lamp")
        front_text(o, DEMO_FENCE_SIGN, win_x, win_z1 + 0.25, 0.09, M["dark"])

    def k_glass_room(o):
        """Glass demo compartment: glass walls on a frame, opaque roof, door on local +x side."""
        w, d = o["size_m"]
        h, t = o["height_m"], 0.05
        hw_ = h - 0.1
        for lx, ly, pw, pd in ((0, -d / 2 + t / 2, w, t), (0, d / 2 - t / 2, w, t)):
            part(o, lx, ly, 0.0, pw - 0.02, 0.02, hw_, M["glass"], "pane")
            part(o, lx, ly, 0.0, pw, pd, 0.08, M["dark"], "sill")
            n = max(1, round(w / 1.5))
            for i in range(n + 1):
                part(o, -w / 2 + t / 2 + (w - t) * i / n, ly, 0, t, pd, hw_, M["dark"], "post")
        part(o, -w / 2 + t / 2, 0, 0.0, 0.02, d - 2 * t, hw_, M["glass"], "pane_l")
        part(o, -w / 2 + t / 2, 0, 0.0, t, d - 2 * t, 0.08, M["dark"], "sill_l")
        door = min(1.0, d - 0.4)
        y0, y1 = -d / 2 + t, d / 2 - t - door  # glass part of the right side; the door is at local +y
        part(o, w / 2 - t / 2, (y0 + y1) / 2, 0.0, 0.02, y1 - y0, hw_, M["glass"], "pane_r")
        part(o, w / 2 - t / 2, y1, 0.0, t, t, hw_, M["dark"], "door_post")
        part(o, w / 2 - t / 2, y1 + door / 2, 0.0, 0.03, door - t, 2.1, M["lp_glass"], "door")
        part(o, w / 2 - t / 2, y1 + door / 2, 2.1, t, door, hw_ - 2.1, M["dark"], "door_top")
        part(o, 0, 0, hw_, w, d, 0.1, M["light"], "roof")
        part(o, 0, -d / 2 - 0.001, hw_ - 0.3, w * 0.5, 0.004, 0.08, M["red"], "stripe")

    def k_cell(o):
        w, d = o["size_m"]
        h = o["height_m"]
        for sx in (-1, 1):
            for sy in (-1, 1):
                part(o, sx * (w / 2 - 0.03), sy * (d / 2 - 0.03), 0, 0.06, 0.06, h, M["dark"], "post")
        part(o, 0, -d / 2 + 0.03, h - 0.06, w, 0.06, 0.06, M["red"], "rail_f")
        part(o, 0, d / 2 - 0.03, h - 0.06, w, 0.06, 0.06, M["dark"], "rail_b")
        for side, (lx, ly, pw, pd) in enumerate([(0, -d / 2 + 0.03, w - 0.12, 0.012), (0, d / 2 - 0.03, w - 0.12, 0.012),
                                                 (-w / 2 + 0.03, 0, 0.012, d - 0.12), (w / 2 - 0.03, 0, 0.012, d - 0.12)]):
            part(o, lx, ly, 0.1, pw, pd, h - 0.2, M["poly"], f"panel{side}")
            part(o, lx, ly, 0, pw, max(pd, 0.04), 0.1, M["dark"], f"kick{side}")

    def k_robot(o):
        x, y = to_world(o, 0, 0)
        cyl(f"{o['id']}_base", x, y, 0, 0.25, 0.4, M["dark"])
        part(o, 0, 0, 0.4, 0.2, 0.2, 0.75, M["white"], "arm1")
        sphere(f"{o['id']}_elbow", x, y, 1.22, 0.12, M["red"])
        part(o, 0.45, 0, 1.15, 0.9, 0.16, 0.16, M["white"], "arm2")
        part(o, 0.9, 0, 1.0, 0.1, 0.1, 0.15, M["red"], "wrist")
        part(o, 0.9, 0, 0.94, 0.08, 0.08, 0.06, M["dark"], "tool")

    def k_table(o):
        w, d = o["size_m"]
        h, b = o["height_m"], o.get("base_m", 0)
        part(o, 0, 0, b + h - 0.04, w, d, 0.04, M["white"], "top")
        for sx in (-1, 1):
            for sy in (-1, 1):
                part(o, sx * (w / 2 - 0.06), sy * (d / 2 - 0.06), b, 0.05, 0.05, h - 0.04, M["grey"], "leg")
        if o.get("samples"):
            for i in range(4):
                part(o, -w * 0.3 + i * w * 0.2, 0, b + h, 0.12, 0.12, 0.008, M["steel"], f"s{i}")

    def k_desk(o):
        d = o["size_m"][1]
        h = o["height_m"]
        k_table(dict(o, samples=False))
        part(o, 0, d / 2 - 0.12, h, 0.04, 0.04, 0.12, M["dark"], "mon_post")
        part(o, 0, d / 2 - 0.14, h + 0.1, 0.56, 0.03, 0.34, M["black"], "mon")
        part(o, 0, d / 2 - 0.157, h + 0.12, 0.52, 0.004, 0.3, M["display"], "mon_scr")
        part(o, 0, -d / 2 + 0.2, h, 0.45, 0.15, 0.02, M["dark"], "kbd")

    def k_chair(o):
        w, d = o["size_m"]
        part(o, 0, 0, 0.42, w * 0.9, d * 0.9, 0.05, M["dark"], "seat")
        part(o, 0, d / 2 - 0.03, 0.47, w * 0.9, 0.04, o["height_m"] - 0.47, M["dark"], "back")
        for sx in (-1, 1):
            for sy in (-1, 1):
                part(o, sx * (w / 2 - 0.05), sy * (d / 2 - 0.05), 0, 0.03, 0.03, 0.42, M["grey"], "leg")

    def k_screen(o):
        w, d = o["size_m"]
        h = o["height_m"]
        disp_h = min(1.0, w * 0.58)
        for sx in (-1, 1):
            part(o, sx * w * 0.3, 0, 0, 0.08, d, 0.03, M["dark"], "foot")
            part(o, sx * w * 0.3, 0, 0.03, 0.05, 0.05, h - disp_h, M["grey"], "post")
        part(o, 0, 0.01, h - disp_h, w, d - 0.02, disp_h, M["black"], "frame")
        part(o, 0, -d / 2 + 0.006, h - disp_h + 0.03, w - 0.06, 0.004, disp_h - 0.06, M["display"], "scr")
        part(o, 0, -d / 2 + 0.006, h - disp_h - 0.06, w, 0.004, 0.04, M["red"], "stripe")

    def k_vitrine(o):
        w, d = o["size_m"]
        h = o["height_m"]
        part(o, 0, 0, 0, w, d, 0.08, M["dark"], "kick")
        part(o, 0, 0, 0.08, w, d, 0.82, M["white"], "base")
        part(o, 0, -d / 2 - 0.001, 0.8, w, 0.004, 0.04, M["red"], "stripe")
        part(o, 0, 0, 0.9, w - 0.02, d - 0.02, h - 0.9, M["glass"], "hood")
        ex = o.get("exhibit", {})
        at, rot = frame(o)
        x, y = at(0, 0)
        if ex.get("shape") == "ingot":
            part(o, 0, 0, 0.9, 0.12, 0.08, 0.03, M["dark"], "cradle")
            cyl(f"{o['id']}_ingot", x, y, 0.93 + ex["d"] / 2, ex["d"] / 2, ex["l"], M["gaas"],
                rot=(0, math.radians(90), math.radians(rot)))
        elif ex.get("shape") == "wafers":
            for i in range(3):
                xi, yi = at(-0.15 + i * 0.15, 0)
                cyl(f"{o['id']}_wafer{i}", xi, yi, 0.9, ex["d"] / 2, 0.003, M["gaas"], seg=32)
        elif ex.get("shape") == "box":
            part(o, 0, 0, 0.9, ex["w"], ex["d"], ex["h"], M["steel"], "exhibit")
        elif ex.get("shape") == "plates":
            n = max(2, int(w / 0.35))
            for i in range(n):
                part(o, -w / 2 + w * (i + 0.5) / n, 0, 0.9, 0.16, 0.12, 0.006, M["steel"], f"plate{i}")

    def k_plinth(o):
        w, d = o["size_m"]
        part(o, 0, 0, 0, w, d, 0.06, M["dark"], "kick")
        part(o, 0, 0, 0.06, w, d, o["height_m"] - 0.06, M["white"], "body")

    def k_kit(o):
        w, d = o["size_m"]
        b = o.get("base_m", 0)
        part(o, 0, 0, b, w, d, 0.02, M["dark"], "plate")
        at, _ = frame(o)
        for i, lx in enumerate((-0.3, -0.1, 0.1, 0.3)):
            x, y = at(lx, 0.05 * (-1) ** i)
            cyl(f"{o['id']}_post{i}", x, y, b + 0.02, 0.012, 0.11, M["steel"], seg=12)
            part(o, lx, 0.05 * (-1) ** i, b + 0.1, 0.05, 0.03, 0.04, M["black"], f"opt{i}")

    def k_optical_table(o):
        w, d = o["size_m"]
        h = o["height_m"]
        for sx in (-1, 1):
            for sy in (-1, 1):
                part(o, sx * (w / 2 - 0.15), sy * (d / 2 - 0.2), 0, 0.2, 0.2, h - 0.2, M["dark"], "leg")
        part(o, 0, 0, h - 0.2, w, d, 0.195, M["black"], "plate")
        part(o, 0, 0, h - 0.005, w, d, 0.005, M["steel"], "top")

    def k_laminar(o):
        w, d = o["size_m"]
        h = o["height_m"]
        part(o, 0, 0, 0, w, d, 0.75, M["white"], "cab")
        part(o, 0, 0, 0.75, w, d, 0.03, M["steel"], "work")
        part(o, 0, d / 2 - 0.03, 0.78, w, 0.06, 0.85, M["white"], "back")
        for sx in (-1, 1):
            part(o, sx * (w / 2 - 0.01), 0, 0.78, 0.02, d - 0.06, 0.85, M["glass"], "side")
        part(o, 0, 0, 1.63, w, d, h - 1.63, M["white"], "hood")
        part(o, 0, -d / 2 + 0.005, 1.68, w - 0.1, 0.01, h - 1.8, M["light"], "grille")
        part(o, 0, -d / 2 + 0.005, 1.65, w - 0.02, 0.01, 0.03, M["red"], "stripe")

    def k_label(o):
        w = o["size_m"][0]
        h = o["height_m"]
        part(o, 0, 0, 0, 0.3, 0.3, 0.02, M["dark"], "foot")
        part(o, 0, 0, 0.02, 0.04, 0.04, h - 0.25, M["grey"], "post")
        part(o, 0, 0, h - 0.25, w, 0.02, 0.25, M["white"], "plate")
        part(o, -w / 2 + 0.02, -0.011, h - 0.25, 0.04, 0.002, 0.25, M["red"], "bar")
        size = min(0.05, (w - 0.08) / (0.58 * max(1, len(o["label"]))))
        at, rot = frame(o)
        for back in (False, True):
            x, y = at(0.02, 0.012 * (1 if back else -1))
            text(o["label"], x, y, h - 0.125, size, rot + (180 if back else 0), M["dark"], name=f"{o['id']}_t")

    def k_history_wall(o):
        w, d = o["size_m"]
        h = o["height_m"]
        part(o, 0, 0, 0, w, d, 0.08, M["dark"], "kick")
        part(o, 0, 0, 0.08, w, d, h - 0.08, M["white"], "wall")
        part(o, 0, d / 2 + 0.002, 2.6, w, 0.004, 0.08, M["red"], "back_stripe")
        f = -d / 2 - 0.003  # front face
        part(o, -w / 2 + 1.0, f, 2.45, 1.4, 0.006, 0.5, M["red"], "logo_place")
        # timeline 2015 -> 2023 (case, slide 4)
        part(o, -0.9, f, 2.03, 4.0, 0.006, 0.03, M["red"], "timeline")
        at, rot = frame(o)
        for lx, year, place in ((-2.8, "2015", "Калуга"), (1.0, "2023", "Технополис Москва")):
            x, y = at(lx, f - 0.01)
            cyl(f"{o['id']}_dot{year}", x, y, 2.045, 0.06, 0.012, M["red"], seg=20,
                rot=(math.radians(90), 0, math.radians(rot)))
            x, y = at(lx, f - 0.004)
            text(year, x, y, 2.3, 0.16, rot, M["dark"], name="t_year")
            text(place, x, y, 1.85, 0.08, rot, M["dark"], name="t_place")
        for i, (num, cap) in enumerate(SCALE_FACTS):
            lx = -2.9 + i * 0.95
            x, y = at(lx, f - 0.004)
            text(num, x, y, 1.35, 0.17 if len(num) < 6 else 0.12, rot, M["red"] if num == "80 %" else M["dark"], name="t_num")
            text(cap, x, y, 1.1, 0.055, rot, M["dark"], name="t_cap")
        x, y = at(-0.9, f - 0.004)
        text(SCALE_SOURCE, x, y, 0.82, 0.055, rot, M["dark"], name="t_scale_source")
        part(o, 2.45, f, 1.1, 1.7, 0.006, 1.05, M["light"], "map")
        x, y = at(2.45, f - 0.006)
        text(MAP_TITLE, x, y, 1.72, 0.085, rot, M["dark"], name="t_map")
        text(MAP_SOURCE, x, y, 1.5, 0.045, rot, M["dark"], name="t_map_source")
        text("Реестр Минпромторга РФ", x, y, 0.9, 0.07, rot, M["dark"], name="t_reg")
        # brand lines at 243 deg (rise 63 deg to the right), brandbook p. 32
        for i, (dx, mname, th) in enumerate(((0.0, "light", 0.03), (0.18, "red", 0.03), (0.3, "grey", 0.03),
                                             (0.5, "light", 0.03), (0.62, "red", 0.06))):
            lx = 1.2 + dx
            x, y = at(lx, f - 0.004)
            ln = box(f"{o['id']}_line{i}", x, y, 2.75, th, 0.004, 0.85, rot, M[mname])
            ln.rotation_euler = (0, math.radians(27), math.radians(rot))
            ln.location.z = 2.35
        # triangle pattern, brandbook p. 29
        s = 0.2
        for row in range(3):
            for col in range(16):
                k = (row * 7 + col * 3) % 5
                if k == 4 or col > 13 - row * 2:
                    continue
                m = M["red"] if k in (0, 2) else M["grey"] if k == 1 else M["light"]
                lx0 = -w / 2 + 0.25 + col * s * 0.55
                z0 = 0.2 + row * s * 0.95
                up = (col + row) % 2 == 0
                pts = [(lx0, z0 if up else z0 + s), (lx0 + s * 1.1, z0 if up else z0 + s), (lx0 + s * 0.55, z0 + s if up else z0)]
                world = []
                for lx, z in pts:
                    x, y = at(lx, f - 0.003)
                    world.append((x, y, z))
                tri(f"{o['id']}_tri", world, m)

    def k_box(o):
        w, d = o["size_m"]
        part(o, 0, 0, o.get("base_m", 0), w, d, o["height_m"], M["light"], "box")

    # ---- proxies for the plan of #23 (task #96); every part stays inside size_m x height_m
    def tucked_chairs(o, sides, n):
        """Chairs pushed under a table: seat and back stay inside the table footprint."""
        w, d = o["size_m"]
        for side in sides:  # -1: local front (-Y), +1: back
            for i in range(n):
                lx = -w / 2 + w * (i + 0.5) / n
                part(o, lx, side * (d / 2 - 0.27), 0.42, 0.42, 0.42, 0.05, M["dark"], "seat")
                part(o, lx, side * (d / 2 - 0.04), 0.47, 0.42, 0.04, 0.43, M["dark"], "chair_back")
                for sx in (-1, 1):
                    part(o, lx + sx * 0.17, side * (d / 2 - 0.27), 0, 0.03, 0.03, 0.42, M["grey"], "chair_leg")

    def k_desk_chair(o):
        k_desk(o)
        tucked_chairs(o, (-1,), 1)

    def k_meeting_table(o):
        k_table(dict(o, samples=False))
        tucked_chairs(o, (-1, 1), max(1, int(o["size_m"][0] / 0.8)))

    def k_wall_screen(o):
        """Screen on the wall: the display hangs at the back of the footprint, top at height_m."""
        w, d = o["size_m"]
        h = o["height_m"]
        disp_h = min(w * 9 / 16, h - 1.0)
        z0 = h - disp_h
        part(o, 0, d / 2 - 0.03, z0, w, 0.06, disp_h, M["black"], "frame")
        part(o, 0, d / 2 - 0.062, z0 + 0.03, w - 0.06, 0.004, disp_h - 0.06, M["display"], "scr")
        part(o, 0, d / 2 - 0.03, z0 - 0.08, w, 0.06, 0.04, M["red"], "stripe")

    def tri_pattern(o, f, lx0, cols, z_base, s=0.2, rows=3):
        """Triangle pattern, brandbook p. 29, on the face at local y = f."""
        at, _ = frame(o)
        for row in range(rows):
            for col in range(cols):
                k = (row * 7 + col * 3) % 5
                if k == 4 or col > cols - 3 - row * 2:
                    continue
                m = M["red"] if k in (0, 2) else M["grey"] if k == 1 else M["light"]
                x0 = lx0 + col * s * 0.55
                z0 = z_base + row * s * 0.95
                up = (col + row) % 2 == 0
                pts = [(x0, z0 if up else z0 + s), (x0 + s * 1.1, z0 if up else z0 + s),
                       (x0 + s * 0.55, z0 + s if up else z0)]
                world = []
                for lx, z in pts:
                    x, y = at(lx, f)
                    world.append((x, y, z))
                tri(f"{o['id']}_tri", world, m)

    def k_panel(o):
        """Free-standing panel of the entrance (01-layout: chronology, map, scale). Content on the front."""
        w, d = o["size_m"]
        h, t = o["height_m"], 0.12
        for sx in (-1, 1):
            part(o, sx * (w / 2 - 0.15), 0, 0, 0.3, d, 0.08, M["dark"], "foot")
        part(o, 0, 0, 0.08, w, t, h - 0.08, M["white"], "body")
        part(o, 0, t / 2 + 0.002, h - 0.2, w, 0.004, 0.08, M["red"], "back_stripe")
        f = -t / 2 - 0.003  # front face
        at, rot = frame(o)
        c = o.get("content")
        if c == "timeline":
            part(o, -w / 2 + 0.75, f, 2.0, 1.2, 0.006, 0.38, M["red"], "logo_place")
            part(o, 0, f, 1.5, w - 0.6, 0.006, 0.03, M["red"], "timeline")
            for lx, year, place in ((-1.3, "2015", "Калуга"), (1.3, "2023", "Технополис Москва")):
                x, y = at(lx, f - 0.01)
                cyl(f"{o['id']}_dot{year}", x, y, 1.515, 0.06, 0.012, M["red"], seg=20,
                    rot=(math.radians(90), 0, math.radians(rot)))
                x, y = at(lx, f - 0.004)
                text(year, x, y, 1.75, 0.16, rot, M["dark"], name="t_year")
                text(place, x, y, 1.3, 0.08, rot, M["dark"], name="t_place")
            for i, (dx, mname, th) in enumerate(((0.0, "light", 0.03), (0.18, "red", 0.03), (0.3, "grey", 0.03),
                                                 (0.5, "light", 0.03), (0.62, "red", 0.06))):
                x, y = at(0.6 + dx, f - 0.004)
                ln = box(f"{o['id']}_line{i}", x, y, 1.95, th, 0.004, 0.45, rot, M[mname])
                ln.rotation_euler = (0, math.radians(27), math.radians(rot))  # 243 deg, brandbook p. 32
            tri_pattern(o, f - 0.003, -w / 2 + 0.25, 12, 0.25)
        elif c == "map":
            part(o, 0, f, 0.85, 2.6, 0.006, 1.05, M["light"], "map")
            x, y = at(0, f - 0.006)
            text(MAP_TITLE, x, y, 2.15, 0.14, rot, M["dark"], name="t_map")
            text(MAP_SOURCE, x, y, 1.96, 0.075, rot, M["dark"], name="t_map_source")
            text("Реестр Минпромторга РФ", x, y, 0.6, 0.09, rot, M["dark"], name="t_reg")
            part(o, -w / 2 + 0.2, f, 0.3, 0.04, 0.006, 2.0, M["red"], "bar")
        elif c == "scale":
            items = SCALE_FACTS
            step = (w - 0.3) / len(items)
            for i, (num, cap) in enumerate(items):
                x, y = at(-w / 2 + 0.15 + step * (i + 0.5), f - 0.004)
                text(num, x, y, 1.7, 0.14 if len(num) < 6 else 0.085, rot,
                     M["red"] if num == "80 %" else M["dark"], name="t_num")
                text(cap, x, y, 1.46, 0.045, rot, M["dark"], name="t_cap")
            x, y = at(0, f - 0.004)
            text(SCALE_SOURCE, x, y, 1.15, 0.047, rot, M["dark"], name="t_scale_source")
            part(o, 0, f, 2.1, w - 0.3, 0.006, 0.03, M["red"], "bar")
            tri_pattern(o, f - 0.003, -w / 2 + 0.2, 9, 0.25)

    def k_on_stand(o):
        kind, iw, idp, ih, _ = o["item"]
        w, d = o["size_m"]
        sh = max(0.06, o["height_m"] - ih)
        part(o, 0, 0, 0, w, d, 0.06, M["dark"], "kick")
        if sh > 0.07:
            part(o, 0, 0, 0.06, w, d, sh - 0.06, M["white"], "stand")
            part(o, 0, -d / 2 - 0.001, sh - 0.06, w, 0.004, 0.03, M["red"], "stripe")
        KINDS[kind](dict(o, size_m=[iw, idp], height_m=ih, base_m=sh))

    def k_robot_cell(o):
        k_cell(o)
        x, y = to_world(o, -0.6, 0.2)
        k_robot(dict(o, position=[x, y]))
        x, y = to_world(o, 0.75, 0.2)
        k_table(dict(o, id=o["id"] + "_table", position=[x, y], size_m=[1.0, 0.8], height_m=0.9, samples=True))

    def k_portal(o):
        """Portal engraver: cabinet with a table, gantry with a head (outline estimate)."""
        w, d = o["size_m"]
        h = o["height_m"]
        part(o, 0, 0, 0, w, d, 0.08, M["dark"], "plinth")
        part(o, 0, 0.01, 0.08, w - 0.02, d - 0.02, 0.77, M["white"], "cab")
        part(o, 0, -d / 2 + 0.005, 0.7, w - 0.02, 0.01, 0.05, M["red"], "stripe")
        part(o, 0, 0, 0.85, min(0.95, w - 0.1), min(0.75, d - 0.1), 0.03, M["steel"], "table")
        for sx in (-1, 1):
            part(o, sx * (w / 2 - 0.05), 0.1, 0.85, 0.08, 0.16, h - 0.97, M["grey"], "post")
        part(o, 0, 0.1, h - 0.12, w, 0.16, 0.12, M["white"], "beam")
        part(o, 0.1, -0.02, h - 0.55, 0.16, 0.14, 0.43, M["white"], "head")
        part(o, 0.1, -0.02, h - 0.58, 0.05, 0.05, 0.03, M["red"], "lens")
        name = model_name(o["label"])
        if name:
            front_text(o, name, 0, 0.45, 0.06, M["dark"])

    def k_clean_zone(o):
        """Fenced part of the demo zone: fence without a roof, door, glass window.
        No laser and no laser cleaning (D-001): no signal lamp, no laser-protective glass."""
        w, d = o["size_m"]
        h, t = o["height_m"], 0.05
        ph = h - 0.06
        hx = w / 2
        win_w, win_z0, win_z1, win_x = min(1.0, w * 0.4), 1.0, 1.8, -w * 0.15
        for sx in (-1, 1):
            for sy in (-1, 1):
                part(o, sx * (hx - t / 2), sy * (d / 2 - t / 2), 0, t, t, h, M["dark"], "post")
        part(o, 0, -d / 2 + t / 2, h - 0.06, w, t, 0.06, M["red"], "rail_f")
        part(o, 0, d / 2 - t / 2, h - 0.06, w, t, 0.06, M["dark"], "rail_b")
        fy = -d / 2 + t / 2
        part(o, (-hx + win_x - win_w / 2) / 2, fy, 0, (win_x - win_w / 2) + hx, 0.03, ph, M["fence"], "f1")
        part(o, (win_x + win_w / 2 + hx) / 2, fy, 0, hx - (win_x + win_w / 2), 0.03, ph, M["fence"], "f2")
        part(o, win_x, fy, 0, win_w, 0.03, win_z0, M["fence"], "f3")
        part(o, win_x, fy, win_z1, win_w, 0.03, ph - win_z1, M["fence"], "f4")
        part(o, win_x, fy, win_z0, win_w, 0.02, win_z1 - win_z0, M["glass"], "win")
        part(o, 0, d / 2 - t / 2, 0, w, 0.03, ph, M["fence"], "back")
        part(o, -hx + t / 2, 0, 0, 0.03, d - 2 * t, ph, M["fence"], "left")
        # right side (local +x): jamb 0.1 m, door, then fence to the back post
        door = min(0.9, d - 0.6)
        y0 = -d / 2 + t
        part(o, hx - t / 2, y0 + 0.05, 0, 0.03, 0.1, ph, M["fence"], "door_jamb")
        part(o, hx - t / 2, y0 + 0.1 + door / 2, 0, 0.05, door, 2.1, M["dark"], "door")
        part(o, hx - t / 2, y0 + 0.1 + door / 2, 2.1, 0.03, door, ph - 2.1, M["fence"], "door_top")
        rest = d - 2 * t - 0.1 - door
        part(o, hx - t / 2, y0 + 0.1 + door + rest / 2, 0, 0.03, rest, ph, M["fence"], "right")
        front_text(o, DEMO_FENCE_SIGN, 0, win_z1 + 0.3, 0.07, M["dark"])

    def k_miniature(o):
        """D-001: 1:5 model of a large machine on a plinth under a glass hood. The model is the
        full-size proxy of MINIATURE, built at the object centre and then scaled by 1/5."""
        w, d = o["size_m"]
        h = o["height_m"]
        kind, mw, md, mh, _src = o["model"]
        if (w - d) * (mw - md) < 0:  # facing turned the plinth: turn the model with it
            mw, md = md, mw
        part(o, 0, 0, 0, w, d, 0.08, M["dark"], "kick")
        part(o, 0, 0, 0.08, w, d, MINI_PLINTH_M - 0.08, M["white"], "base")
        part(o, 0, -d / 2 - 0.001, MINI_PLINTH_M - 0.1, w, 0.004, 0.04, M["red"], "stripe")
        part(o, 0, 0, MINI_PLINTH_M, w - 0.02, d - 0.02, h - MINI_PLINTH_M, M["glass"], "hood")
        name = model_name(o["label"])
        sign = f"{name} · 1:5" if name else "1:5"
        front_text(o, sign, 0, MINI_PLINTH_M * 0.6, min(0.05, w / (0.65 * len(sign))), M["dark"])
        before = set(coll.objects)
        KINDS[kind](dict(o, size_m=[mw, md], height_m=mh, base_m=0))
        cx, cy = o["position"]
        for ob in set(coll.objects) - before:
            x, y, z = ob.location
            ob.location = (cx + (x - cx) * MINI_SCALE, cy + (y - cy) * MINI_SCALE, MINI_PLINTH_M + z * MINI_SCALE)
            ob.scale = tuple(v * MINI_SCALE for v in ob.scale)

    def k_kit_stand(o):
        """Stand with a teaching kit on the worktop and a back board (outline estimate)."""
        w, d = o["size_m"]
        h = o["height_m"]
        part(o, 0, 0, 0, w, d, 0.06, M["dark"], "kick")
        part(o, 0, 0, 0.06, w, d, 0.8, M["white"], "cab")
        part(o, 0, 0, 0.86, w, d, 0.03, M["dark"], "top")
        part(o, 0, d / 2 - 0.02, 0.89, w, 0.04, h - 0.89, M["light"], "board")
        part(o, 0, -d / 2 - 0.001, 0.75, w, 0.004, 0.04, M["red"], "stripe")
        k_kit(dict(o, size_m=[min(0.8, w - 0.1), min(0.4, d - 0.2)], base_m=0.89,
                   position=list(to_world(o, 0, -0.1))))

    KINDS = {"machine": k_machine, "unit": k_unit, "engraver": k_engraver, "open_engraver": k_open_engraver,
             "cabin": k_cabin, "glass_room": k_glass_room, "cell": k_cell, "robot": k_robot, "table": k_table,
             "chair": k_chair, "screen": k_screen, "vitrine": k_vitrine, "plinth": k_plinth, "kit": k_kit,
             "optical_table": k_optical_table, "laminar": k_laminar, "label": k_label,
             "history_wall": k_history_wall, "box": k_box,
             "desk": k_desk_chair if lay["source"] == "plan" else k_desk, "meeting_table": k_meeting_table,
             "wall_screen": k_wall_screen, "panel": k_panel, "on_stand": k_on_stand, "robot_cell": k_robot_cell,
             "portal": k_portal, "clean_zone": k_clean_zone, "kit_stand": k_kit_stand,
             "miniature": k_miniature}

    def person(p):
        o = {"id": p["id"], "position": p["position"], "size_m": [0.5, 0.35], "rotation_deg": p.get("rotation_deg", 0)}
        at, _ = frame(o)
        pm = M["person"]
        if p.get("pose") == "sit":
            for sx in (-1, 1):
                part(o, sx * 0.1, -0.2, 0.42, 0.13, 0.42, 0.14, pm, "thigh")
                part(o, sx * 0.1, -0.38, 0.0, 0.11, 0.11, 0.44, pm, "shin")
            hip = 0.5
        else:
            for sx in (-1, 1):
                x, y = at(sx * 0.1, 0)
                cyl(f"{p['id']}_leg", x, y, 0, 0.07, 0.86, pm, seg=12)
            hip = 0.86
        part(o, 0, 0, hip, 0.4, 0.22, 0.59, pm, "torso")
        for sx in (-1, 1):
            x, y = at(sx * 0.25, 0)
            cyl(f"{p['id']}_arm", x, y, hip - 0.05, 0.045, 0.6, pm, seg=10)
        x, y = at(0, 0)
        cyl(f"{p['id']}_neck", x, y, hip + 0.59, 0.05, 0.08, pm, seg=10)
        top = hip + 0.59 + 0.08 + 0.22
        sphere(f"{p['id']}_head", x, y, top - 0.11, 0.11, pm)
        if p.get("pose") != "sit" and abs(top - PERSON_H) > 0.005:
            raise SystemExit(f"{p['id']}: рост {top:.3f} м, ожидался {PERSON_H} м")

    # ---- building
    rx1 = max(pt[0] for pt in lay["room"]["boundary"])
    ry1 = max(pt[1] for pt in lay["room"]["boundary"])
    box("floor", rx1 / 2, ry1 / 2, -0.05, rx1 + 0.4, ry1 + 0.4, 0.05, 0, M["floor"])
    box("ground", rx1 / 2, -20, -0.06, 120, 40, 0.05, 0, M["grey"])
    box("ceiling", rx1 / 2, ry1 / 2, H, rx1 + 0.4, ry1 + 0.4, 0.2, 0, M["ceiling"], grp="ceiling")

    glass_spans = {}
    for op in lay["openings"]:
        if op["kind"] == "glass":
            glass_spans.setdefault(op["wallId"], []).append((op["offset_m"], op["offset_m"] + op["width_m"]))
    glass_walls = set(lay.get("glassWalls", []))
    for w in lay["walls"]:
        (x0, y0), (x1, y1) = w["from"], w["to"]
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        rot = math.degrees(math.atan2(uy, ux))
        t, wh = w["thickness_m"], w["height_m"]
        gw = w["id"] in glass_walls  # glass partition (plan extensions.zoning219.walls)
        ops = []
        for op in lay["openings"]:
            if op["wallId"] != w["id"]:
                continue
            a, b = op["offset_m"], op["offset_m"] + op["width_m"]
            if op["kind"] != "glass" and any(g0 <= a and b <= g1 for g0, g1 in glass_spans.get(w["id"], [])):
                continue  # draft: a door inside a glass span is not shown (crossed out on the case scheme)
            ops.append((a, b, op))
        ops.sort(key=lambda r: r[0])

        def seg(a, b, z0, z1, material, tag, thick=t):
            if b - a < 1e-3 or z1 - z0 < 1e-3:
                return None
            m = (a + b) / 2
            return box(f"{w['id']}_{tag}", x0 + ux * m, y0 + uy * m, z0, b - a, thick, z1 - z0, rot, material,
                       grp="wall", wall=w["id"])

        def solid(a, b, z0, z1, tag):
            if not gw:
                return seg(a, b, z0, z1, M["wall"], tag)
            seg(a, b, z0, z1, M["glass"], tag + "_g", thick=0.02)
            if z0 < 1e-3:
                seg(a, b, 0, 0.08, M["dark"], tag + "_fb", thick=t + 0.02)
            if z1 > wh - 1e-3:
                seg(a, b, wh - 0.08, wh, M["dark"], tag + "_ft", thick=t + 0.02)
            return None

        cur = -t / 2
        for a, b, op in ops:
            solid(cur, a, 0, wh, "s")
            top = op["sill_m"] + op["height_m"]
            solid(a, b, 0, op["sill_m"], "sill")
            solid(a, b, top, wh, "lintel")
            if op["kind"] in GLASS_KINDS:
                seg(a, b, op["sill_m"], top, M["glass"], "glass", thick=0.02)
                n = max(1, round((b - a) / 1.5))
                for i in range(n + 1):
                    p0 = a + (b - a) * i / n
                    seg(p0 - 0.03, p0 + 0.03, op["sill_m"], top, M["dark"], "mullion", thick=t + 0.02)
                seg(a, b, op["sill_m"], op["sill_m"] + 0.06, M["dark"], "frame_b", thick=t + 0.02)
                seg(a, b, top - 0.06, top, M["dark"], "frame_t", thick=t + 0.02)
            elif op["kind"] == "door":
                # closed door leaf in a dark frame; entrances stay open
                seg(a + 0.05, b - 0.05, 0.01, top - 0.05, M["door"], "door", thick=0.05)
                for e0, e1 in ((a, a + 0.05), (b - 0.05, b)):
                    seg(e0, e1, 0, top, M["dark"], "door_frame", thick=t + 0.02)
                seg(a, b, top - 0.05, top, M["dark"], "door_frame", thick=t + 0.02)
            cur = b
        solid(cur, L + t / 2, 0, wh, "s")
        if gw:
            # posts of the glass partition, not in the openings
            n = max(1, math.ceil(L / 1.5))
            spans = [(a, b) for a, b, _ in ops]
            for i in range(n + 1):
                p0 = L * i / n
                if any(a - 0.05 < p0 < b + 0.05 for a, b in spans):
                    continue
                seg(p0 - 0.03, p0 + 0.03, 0, wh, M["dark"], "post", thick=t + 0.02)
            for a, b in spans:
                for e in (a, b):
                    seg(e - 0.03, e + 0.03, 0, wh, M["dark"], "post", thick=t + 0.02)

    for c in lay["columns"]:
        cyl(c["id"], c["position"][0], c["position"][1], 0, c["size_m"][0] / 2, c.get("height_m", H), M["column"])

    # workshop behind the workshop wall of the plan (illustration, concept/3d/workshop.json)
    ws = lay["workshop"]
    wr = workshop_rect(lay)
    if wr:
        wx0, wy0, wx1, wy1 = wr
        if lay["workshopSide"] == "w_north":
            wy0 += 0.075
        else:
            wx1 -= 0.075
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        box("ws_floor", cx, cy, -0.05, wx1 - wx0, wy1 - wy0, 0.05, 0, M["ws_floor"])
        box("ws_ceiling", cx, cy, H, wx1 - wx0 + 0.3, wy1 - wy0 + 0.3, 0.2, 0, M["ceiling"], grp="ceiling")
        sides = {"s": ("ws_s", cx, wy0 - 0.075, wx1 - wx0 + 0.3, 0.15), "n": ("ws_n", cx, wy1 + 0.075, wx1 - wx0 + 0.3, 0.15),
                 "w": ("ws_w", wx0 - 0.075, cy, 0.15, wy1 - wy0), "e": ("ws_e", wx1 + 0.075, cy, 0.15, wy1 - wy0)}
        shared = "s" if lay["workshopSide"] == "w_north" else "e"
        for key, (name, bx, by, bw, bd) in sides.items():
            if key != shared:
                box(name, bx, by, 0, bw, bd, H, 0, M["wall"], grp="wall", wall=name)
        if lay["workshopSide"] == "w_north":
            for x in (1.5, 34.5):
                box("ws_lane", x, cy, 0.001, 0.08, wy1 - wy0 - 1, 0.002, 0, M["light"])
        else:
            for x in (wx1 - 0.8, wx1 - 6.0):
                box("ws_lane", x, cy, 0.001, 0.08, wy1 - wy0 - 1, 0.002, 0, M["light"])
        for o in ws["objects"]:
            KINDS.get(o["kind"], k_box)(o)
    else:
        print(f"[3d] цех за стеной {lay['workshopSide']!r}: цех не строю (умею w_north и w_west)")

    # zones on the floor
    for z in lay["zones"]:
        x0, y0, x1, y1 = z["rect"]
        cx, cy, zw, zd = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        st = z.get("style", "zone")
        if st == "entry":
            box(f"{z['id']}_floor", cx, cy, 0, zw, zd, 0.003, 0, M["dark"])
        elif st == "glass":
            box(f"{z['id']}_floor", cx, cy, 0, zw, zd, 0.003, 0, M["teal"])
        elif st == "talks":
            box(f"{z['id']}_floor", cx, cy, 0, zw, zd, 0.003, 0, M["light"])
        if st in ("chain", "zone"):
            # slide 2: zones 1-4 dark edge, other zones grey; nothing is "live" (D-001)
            m, th = (M["dark"], 0.08) if st == "chain" else (M["grey"], 0.04)
            box(f"{z['id']}_e1", cx, y0 + th / 2, 0, zw, th, 0.004, 0, m)
            box(f"{z['id']}_e2", cx, y1 - th / 2, 0, zw, th, 0.004, 0, m)
            box(f"{z['id']}_e3", x0 + th / 2, cy, 0, th, zd, 0.004, 0, m)
            box(f"{z['id']}_e4", x1 - th / 2, cy, 0, th, zd, 0.004, 0, m)
        if st == "test":
            for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)):
                L = math.hypot(bx - ax, by - ay)
                n = int(L / 0.65)
                for i in range(n):
                    p = (i * 0.65 + 0.2) / L
                    box(f"{z['id']}_dash", ax + (bx - ax) * p, ay + (by - ay) * p, 0, 0.4 if ay == by else 0.08,
                        0.08 if ay == by else 0.4, 0.004, 0, M["red"])
        if z.get("number"):
            nx, ny = x0 + 0.9, y1 - 0.9
            cyl(f"{z['id']}_num", nx, ny, 0, 0.42, 0.005, M["red"], seg=32)
            text(z["number"], nx, ny, 0.006, 0.5, 0, M["white"], upright=False, name=f"{z['id']}_numt")
        # hanging sign
        label = (z["number"] + "  " if z.get("number") else "") + z["label"]
        sw = max(1.6, 0.13 * len(label) + 0.5)
        sz = 4.4
        box(f"{z['id']}_sign", cx, cy, sz, sw, 0.04, 0.45, 0, M["white"], grp="sign")
        box(f"{z['id']}_sign_r", cx - sw / 2 + 0.06, cy, sz, 0.12, 0.05, 0.45, 0, M["red"], grp="sign")
        for sx in (-1, 1):
            cyl(f"{z['id']}_cable", cx + sx * sw * 0.4, cy, sz + 0.45, 0.006, H - sz - 0.45, M["grey"], seg=6, grp="sign")
        for back in (False, True):
            text(label, cx, cy + (0.024 if back else -0.024), sz + 0.225, 0.2, 180 if back else 0, M["dark"],
                 name=f"{z['id']}_signt")["grp"] = "sign"
        if z.get("badge"):
            bw = 0.16 * len(z["badge"]) + 0.4
            box(f"{z['id']}_badge", cx, cy, sz - 0.4, bw, 0.04, 0.3, 0, M["dark"], grp="sign")
            for back in (False, True):
                text(z["badge"], cx, cy + (0.024 if back else -0.024), sz - 0.25, 0.17, 180 if back else 0,
                     M["white"], name=f"{z['id']}_badget")["grp"] = "sign"

    for o in lay["objects"]:
        KINDS.get(o["kind"], k_box)(o)
    for p in views["people"]:
        person(p)

    # ---- light: ceiling fixtures (area lights) and the built-in sky
    def fixtures(xs, ys):
        for x in xs:
            for y in ys:
                ld = bpy.data.lights.new("fx", "AREA")
                ld.shape = "RECTANGLE"
                ld.size, ld.size_y = 3.0, 0.4
                ld.energy = LIGHT_W
                lo = bpy.data.objects.new("fx", ld)
                lo.location = (x, y, H - 0.35)
                link(lo, grp="light")
                box("fx_body", x, y, H - 0.34, 3.0, 0.4, 0.06, 0, M["fixture"], grp="fixture")
    fixtures([3 + 6 * i for i in range(6)], [2.2, 6.6, 11.0, 15.4])
    if lay["workshopSide"] == "w_north" and wr:
        fixtures([3 + 6 * i for i in range(6)], [ry1 + 3, ry1 + 8])
    elif lay["workshopSide"] == "w_west" and wr:
        fixtures([wr[0] + 3.0, wr[0] + 9.0], [2.2, 6.6, 11.0, 15.4])
    for ob in coll.objects:
        if ob.get("grp") == "fixture":
            ob.visible_diffuse = False
            ob.visible_glossy = False
            ob.visible_shadow = False

    world = bpy.data.worlds.new("sky")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    sky = nt.nodes.new("ShaderNodeTexSky")
    for st in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA", "PREETHAM"):
        try:
            sky.sky_type = st
            break
        except TypeError:
            continue
    try:
        sky.sun_elevation = math.radians(35)
        sky.sun_rotation = math.radians(200)
    except AttributeError:
        pass
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = SKY_STRENGTH
    scene.world = world

    # ---- render settings
    rs = scene.render
    rs.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 4
    scene.cycles.transparent_max_bounces = 12
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.cycles.sample_clamp_indirect = 5.0
    try:
        scene.view_settings.view_transform = VIEW_TRANSFORM
    except TypeError:
        pass
    rx, ry = (int(v) for v in args.res.split("x"))
    rs.resolution_x, rs.resolution_y, rs.resolution_percentage = rx, ry, 100
    rs.image_settings.file_format = "PNG"
    rs.image_settings.color_mode = "RGB"
    rs.image_settings.color_depth = "8"
    rs.image_settings.compression = 100
    rs.use_stamp = True
    for a in dir(rs):
        if a.startswith("use_stamp_") and a not in ("use_stamp_note",):
            try:
                setattr(rs, a, False)
            except (AttributeError, TypeError):
                pass
    rs.use_stamp_note = True
    rs.stamp_font_size = 28
    rs.stamp_foreground = (4.0, 4.0, 4.0, 1.0)  # compensates the scene exposure of -2 EV
    rs.stamp_background = (0.0, 0.0, 0.0, 1.0)  # opaque: the plate crosses the ceiling lights

    cam_data = bpy.data.cameras.new("cam")
    cam_data.sensor_width = 36
    cam_data.clip_start = 0.1
    cam_data.clip_end = 300
    cam = bpy.data.objects.new("cam", cam_data)
    coll.objects.link(cam)
    scene.camera = cam

    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save_blend).resolve()))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {v for v in args.only.split(",") if v}
    status = 0
    for v in views["views"]:
        if only and v["id"] not in only:
            continue
        hide = set(v.get("hide", []))
        for ob in coll.objects:
            ob.hide_render = ob.get("grp") in hide or (ob.get("wall") or "") in hide
        loc, tgt = Vector(v["location"]), Vector(v["target"])
        cam.location = loc
        cam.rotation_euler = (tgt - loc).to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = v.get("lens_mm", 20)
        scene.view_settings.exposure = v.get("exposure", EXPOSURE)
        white = 2.0 ** -scene.view_settings.exposure  # keeps the caption white at any exposure
        rs.stamp_foreground = (white, white, white, 1.0)
        rs.stamp_note_text = f"{v['title']} · {views['stamp']}"
        path = out / f"3d-{v['id']}.png"
        rs.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        size = path.stat().st_size
        flag = "" if size < MAX_PNG_BYTES else "  <- БОЛЬШЕ 5 МБ"
        print(f"[3d] {path}: {size / 1024 / 1024:.2f} МБ{flag}")
        if size >= MAX_PNG_BYTES:
            status = 1
    return status


def main() -> int:
    args = parse_args()
    views = json.loads(Path(args.views).read_text(encoding="utf-8"))
    lay = load_layout(Path(args.plan), Path(args.draft), Path(args.workshop), views.get("facing", {}))
    src = Path(args.plan).name if lay["source"] == "plan" else "черновик " + Path(args.draft).name
    print(f"[3d] зоны и объекты: {src}; цех у {lay['workshopSide']}")
    errors = check_layout(lay, views["people"])
    for e in errors:
        print(f"[3d] ОШИБКА: {e}")
    if args.table:
        print(proxy_table(lay))
    if errors:
        return 1
    print(f"[3d] проверка расстановки: {len(lay['objects'])} объектов, {len(views['people'])} фигур — пересечений нет")
    if args.check_only:
        return 0
    return build_and_render(args, lay, views)


if __name__ == "__main__":
    code = main()
    if code:
        sys.exit(code)
