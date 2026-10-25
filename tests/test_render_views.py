"""3D frames of hall 219 (concept/3d/render_views.py, tasks #27, #96): layout loader and checks.

The loader and the checks run without Blender: the module imports bpy only inside
build_and_render. Standard library only.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "concept" / "3d" / "render_views.py"
PLAN = ROOT / "content" / "plan-219.json"
ZONED = ROOT / "content" / "plan-219-zoned.json"
WORKSHOP = ROOT / "concept" / "3d" / "workshop.json"
DRAFT = ROOT / "concept" / "3d" / "layout-draft.json"
VIEWS = ROOT / "concept" / "3d" / "views.json"

spec = importlib.util.spec_from_file_location("render_views", SCRIPT)
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)

# PlanDocument after #23 (fixture): one zone, one object turned 90 degrees clockwise.
FIXTURE_PLAN = {
    "schemaVersion": 1,
    "id": "plan_fixture",
    "room": {"id": "room", "boundary": [[0, 0], [10, 0], [10, 8], [0, 8]], "ceilingHeight_m": 7},
    "walls": [
        {"id": "w_south", "from": [0, 0], "to": [10, 0], "thickness_m": 0.15, "height_m": 7},
        {"id": "w_east", "from": [10, 0], "to": [10, 8], "thickness_m": 0.15, "height_m": 7},
        {"id": "w_north", "from": [10, 8], "to": [0, 8], "thickness_m": 0.15, "height_m": 7},
        {"id": "w_west", "from": [0, 8], "to": [0, 0], "thickness_m": 0.15, "height_m": 7},
    ],
    "openings": [],
    "zones": [{"id": "z1", "label": "Зона 1", "boundary": [[1, 1], [6, 1], [6, 6], [1, 6]],
               "attributes": {"number": 1}}],
    "objects": [
        {"id": "col_1", "typeId": "ot_column", "position": [8, 4], "size_m": [0.8, 0.8],
         "rotation_deg": 0, "height_m": 7, "zoneId": None, "attributes": {}},
        {"id": "screen_1", "typeId": "ot_screen", "label": "Экран", "position": [3, 3],
         "size_m": [2.0, 0.3], "rotation_deg": 90, "height_m": 2.0, "zoneId": "z1",
         "attributes": {"kind3d": "screen"}},
    ],
    "extensions": {"plan219": {"workshop": {"wallId": "w_west"}}},
}


def plan_without_zones() -> dict:
    """content/plan-219.json as it is before #23: geometry only, zones are empty."""
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["zones"] = []
    return plan


def load_fixture(plan: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return rv.load_layout(path, DRAFT)


def check_hall(plan: dict) -> list[str]:
    """check_layout for the fixture hall only: the draft workshop is sized for hall 219."""
    lay = load_fixture(plan)
    lay["workshop"] = dict(lay["workshop"], objects=[])
    return rv.check_layout(lay, [])


def front(o: dict) -> tuple[float, float]:
    """Unit vector of the object front in plan X/Y (local -Y)."""
    x, y = rv.to_world(o, 0, -1)
    return round(x - o["position"][0], 6), round(y - o["position"][1], 6)


def rotate_clockwise(dx: float, dy: float, deg: float) -> tuple[float, float]:
    """Copy of rotateOffset from web/src/planner/geometry.ts (PlanDocument convention)."""
    a = math.radians(deg)
    return round(dx * math.cos(a) + dy * math.sin(a), 6), round(-dx * math.sin(a) + dy * math.cos(a), 6)


class PlanAfter23(unittest.TestCase):
    def test_zones_and_objects_come_from_the_plan(self):
        lay = load_fixture(FIXTURE_PLAN)
        self.assertEqual(lay["source"], "plan")
        self.assertEqual([z["id"] for z in lay["zones"]], ["z1"])
        self.assertEqual(lay["zones"][0]["rect"], [1, 1, 6, 6])
        self.assertEqual([o["id"] for o in lay["objects"]], ["screen_1"])
        self.assertEqual([c["id"] for c in lay["columns"]], ["col_1"])
        self.assertEqual(lay["workshopSide"], "w_west")

    def test_clockwise_90_in_the_plan_faces_west(self):
        # PlanDocument: +90 is clockwise, the front (0, -1) turns to (-1, 0), to the west.
        self.assertEqual(rotate_clockwise(0, -1, 90), (-1.0, 0.0))
        o = load_fixture(FIXTURE_PLAN)["objects"][0]
        self.assertEqual(o["rotation_deg"], 270)
        self.assertEqual(front(o), (-1.0, 0.0))

    def test_every_plan_angle_keeps_the_planner_orientation(self):
        for deg in (0, 45, 90, 180, 270):
            plan = copy.deepcopy(FIXTURE_PLAN)
            plan["objects"][1]["rotation_deg"] = deg
            o = load_fixture(plan)["objects"][0]
            fx, fy = front(o)
            ex, ey = rotate_clockwise(0, -1, deg)
            self.assertAlmostEqual(fx, ex, places=5, msg=deg)
            self.assertAlmostEqual(fy, ey, places=5, msg=deg)

    def test_fixture_plan_passes_the_check(self):
        self.assertEqual(check_hall(FIXTURE_PLAN), [])

    def test_overlap_is_caught(self):
        plan = copy.deepcopy(FIXTURE_PLAN)
        twin = dict(plan["objects"][1], id="screen_2", position=[3.1, 3.2])
        plan["objects"].append(twin)
        errors = check_hall(plan)
        self.assertIn("screen_1 пересекает screen_2", errors)

    def test_object_on_a_column_is_caught(self):
        plan = copy.deepcopy(FIXTURE_PLAN)
        plan["objects"][1].update(position=[8, 4], zoneId=None)
        errors = check_hall(plan)
        self.assertIn("screen_1 пересекает col_1", errors)

    def test_object_outside_its_zone_is_caught(self):
        plan = copy.deepcopy(FIXTURE_PLAN)
        plan["objects"][1]["position"] = [6, 3]
        errors = check_hall(plan)
        self.assertIn("screen_1: выходит за зону z1", errors)


class DraftBefore23(unittest.TestCase):
    def test_draft_angles_stay_counter_clockwise(self):
        # The draft is authored counter-clockwise: the loader passes its angles unchanged.
        lay = load_fixture(plan_without_zones())
        self.assertEqual(lay["source"], "draft")
        draft = json.loads(DRAFT.read_text(encoding="utf-8"))
        self.assertEqual([o.get("rotation_deg", 0) for o in lay["objects"]],
                         [o.get("rotation_deg", 0) for o in draft["objects"]])
        o = {"position": [0, 0], "rotation_deg": 90}
        self.assertEqual(front(o), (1.0, 0.0))

    def test_draft_layout_has_no_crossings(self):
        # The people in views.json stand on the plan of #23 now; the draft is checked without them.
        self.assertEqual(rv.check_layout(load_fixture(plan_without_zones()), []), [])


def load_real() -> tuple[dict, dict]:
    views = json.loads(VIEWS.read_text(encoding="utf-8"))
    return rv.load_layout(ZONED, DRAFT, WORKSHOP, views["facing"]), views


class EntranceFacts112(unittest.TestCase):
    """TRAP-8: historical capacity and geography must not look like current output."""

    def test_capacity_is_qualified_and_dated(self):
        number, caption = next(row for row in rv.SCALE_FACTS if "400+" in row[0])
        self.assertTrue(number.startswith("до "))
        self.assertIn("мощность", caption)
        self.assertIn("2023", caption)
        self.assertIn("Технополис", caption)
        self.assertIn("ЛАССАРД, 03.04.2023", rv.SCALE_SOURCE)
        self.assertIn("Кейс, слайд 3", rv.SCALE_SOURCE)

    def test_geography_is_historical_and_sourced(self):
        self.assertIn("40 регионов", rv.MAP_TITLE)
        self.assertIn("2023", rv.MAP_TITLE)
        self.assertIn("2023", rv.MAP_SOURCE)
        self.assertIn("TAdviser / mos.ru", rv.MAP_SOURCE)


class RealPlan96(unittest.TestCase):
    """content/plan-219-zoned.json (#23/#91) and the frames of task #96."""

    def test_default_plan_is_the_zoned_plan(self):
        self.assertEqual(rv.PLAN, ZONED)
        self.assertEqual(rv.WORKSHOP, WORKSHOP)

    def test_real_plan_loads(self):
        lay, _ = load_real()
        plan = json.loads(ZONED.read_text(encoding="utf-8"))
        self.assertEqual(lay["source"], "plan")
        self.assertEqual(len(lay["zones"]), len(plan["zones"]))
        self.assertEqual(len(lay["objects"]), sum(o["typeId"] != "ot_column" for o in plan["objects"]))
        self.assertEqual(lay["workshopSide"], plan["extensions"]["plan219"]["workshop"]["wallId"])
        self.assertEqual(lay["workshopSide"], "w_west")
        self.assertTrue(lay["workshop"]["objects"], "workshop.json stands at another wall")

    def test_every_plan_type_has_a_proxy(self):
        plan = json.loads(ZONED.read_text(encoding="utf-8"))
        used = {o["typeId"] for o in plan["objects"]} - {"ot_column"}
        self.assertEqual(sorted(used - set(rv.TYPE_KIND)), [])
        for o in load_real()[0]["objects"]:
            self.assertNotEqual(o["kind"], "box", o["id"])
            self.assertTrue(o["src"], o["id"])

    def test_real_plan_and_people_have_no_crossings(self):
        lay, views = load_real()
        self.assertEqual(rv.check_layout(lay, views["people"]), [])

    def test_person_on_an_object_is_caught(self):
        lay, _ = load_real()
        people = [{"id": "p_bad", "position": [4.0, 9.0], "rotation_deg": 0},
                  {"id": "p_out", "position": [3.6, 5.2], "rotation_deg": 0, "inside": "ex_clean_zone"},
                  {"id": "p_ws", "position": [-2.6, 8.6], "rotation_deg": 0}]
        errors = rv.check_layout(lay, people)
        self.assertIn("ex_smart_base пересекает p_bad", errors)
        self.assertIn("p_out: выходит за ex_clean_zone", errors)
        self.assertIn("ws_smart_base пересекает p_ws", errors)

    def test_facing_keeps_the_plan_footprint(self):
        plan = {o["id"]: o for o in json.loads(ZONED.read_text(encoding="utf-8"))["objects"]}
        lay, views = load_real()
        self.assertTrue(views["facing"])
        for o in lay["objects"]:
            p = plan[o["id"]]
            want = rv.footprint(p["position"], p["size_m"], rv.plan_rotation(p.get("rotation_deg", 0)))
            got = rv.footprint(o["position"], o["size_m"], o["rotation_deg"])
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, places=6, msg=o["id"])
            if o["id"] in views["facing"]:
                self.assertEqual(front(o), tuple(float(v) for v in rv.FACES[views["facing"][o["id"]]]), o["id"])

    def test_apply_facing_turns_by_90_and_swaps_the_size(self):
        o = {"id": "x", "position": [5, 5], "size_m": [2.0, 0.4], "rotation_deg": 0}
        for side, rot, size in (("S", 0, [2.0, 0.4]), ("N", 180, [2.0, 0.4]),
                                ("E", 90, [0.4, 2.0]), ("W", 270, [0.4, 2.0])):
            t = rv.apply_facing(o, side)
            self.assertEqual((t["rotation_deg"], t["size_m"]), (rot, size), side)
            self.assertEqual(front(t), tuple(float(v) for v in rv.FACES[side]), side)

    def test_apply_facing_refuses_an_angle_that_is_not_a_multiple_of_90(self):
        o = {"id": "x", "position": [5, 5], "size_m": [2.0, 0.4], "rotation_deg": 45}
        with self.assertRaises(AssertionError):
            rv.apply_facing(o, "N")

    def test_proxy_table_splits_one_type_by_size(self):
        # ot_kit_stand holds ex_mirea (1200 x 800) and ex_laminar (1660 x 1140): two rows.
        rows = [r for r in rv.proxy_table(load_real()[0]).splitlines() if "Стойка: набор МИРЭА" in r]
        self.assertEqual(len(rows), 2)
        self.assertIn("[ex_mirea]", rows[0])
        self.assertIn("1200 × 800 × 1900", rows[0])
        self.assertIn("[ex_laminar]", rows[1])
        self.assertIn("1660 × 1140 × 1900", rows[1])

    def test_laminar_footprint_is_66lb_alm(self):
        # Catalog 66LB-ALM, minimal variant: 1660 x 1140 mm (research/notes/lassard_facts.md).
        for path in (ZONED, ZONED.with_name("plan-219-mirror-zoned.json")):
            plan = json.loads(path.read_text(encoding="utf-8"))
            obj = next(o for o in plan["objects"] if o["id"] == "ex_laminar")
            self.assertEqual(obj["size_m"], [1.66, 1.14], path.name)

    def test_nothing_works_live_d001(self):
        # D-001: no live laser process in the hall. No object works, no zone is marked "live".
        lay = load_real()[0]
        self.assertFalse([o["id"] for o in lay["objects"] if o.get("live")])
        self.assertTrue(lay["workshop"]["objects"])
        self.assertFalse([o["id"] for o in lay["workshop"]["objects"] if o.get("live")])
        self.assertFalse([z["id"] for z in lay["zones"] if "ВЖИВУЮ" in z["badge"].upper()])

    def test_large_equipment_is_a_1_to_5_miniature_d001(self):
        # D-001 (#152, #193): no full-size large machine in the hall, only a 1:5 model on a
        # plinth under glass. The plinth is the model plus 0.1 m on each side, rounded to 1 cm.
        large = {"ot_smart_base", "ot_robot_cell", "ot_ls_fl9000", "ot_ls_fl20000", "ot_ndyag", "ot_vgf"}
        self.assertEqual(set(rv.MINIATURE), large)
        for t in large:
            self.assertEqual(rv.TYPE_KIND[t], "miniature", t)
        for path in (ZONED, ZONED.with_name("plan-219-mirror-zoned.json")):
            lay = rv.load_layout(path, DRAFT, WORKSHOP)
            minis = [o for o in lay["objects"] if o["typeId"] in large]
            self.assertEqual({o["typeId"] for o in minis}, large, path.name)
            for o in minis:
                self.assertEqual(o["kind"], "miniature", o["id"])
                _kind, mw, md, mh, _src = o["model"]
                model = sorted(v * rv.MINI_SCALE for v in (mw, md))
                plinth = sorted(o["size_m"])
                for m, p in zip(model, plinth):
                    self.assertLess(m, p, o["id"])  # the model fits on the plinth
                    self.assertLessEqual(p, m + 0.21, o["id"])  # no full-size footprint
                self.assertGreaterEqual(o["height_m"], rv.MINI_PLINTH_M + mh * rv.MINI_SCALE, o["id"])

    def test_TRAP_3_miniature_model_has_the_machine_size_not_the_field(self):
        # TRAP-3: SMART BASE has a work field 800 x 800 mm in the catalog; the 1:5 model
        # scales the machine size 1750 x 1750 x 2200 mm. Same for every item with a catalog size.
        catalog = json.loads((ROOT / "content" / "catalog.json").read_text(encoding="utf-8"))["items"]
        sized = {i["plan_type"]: i for i in catalog if i.get("plan_type") in rv.MINIATURE and i.get("size_mm")}
        self.assertIn("ot_smart_base", sized)
        for t, item in sized.items():
            _kind, mw, md, mh, _src = rv.MINIATURE[t]
            size = item["size_mm"]
            self.assertEqual(sorted((mw, md)), sorted((size["length"] / 1000, size["width"] / 1000)), t)
            self.assertEqual(mh, size["height"] / 1000, t)
        self.assertNotIn(0.8, rv.MINIATURE["ot_smart_base"][1:4])

    def test_no_sign_says_admission_only_d001(self):
        # D-001: no laser zone in the hall, so no fence says «ВХОД ПО ДОПУСКУ» or «ЛАЗЕРНАЯ ЧИСТКА».
        source = SCRIPT.read_text(encoding="utf-8").upper()
        self.assertNotIn("ДОПУСК", source)
        self.assertNotIn("ЛАЗЕРНАЯ ЧИСТКА", source)

    def test_view_zones_exist_in_the_plan(self):
        lay, views = load_real()
        ids = {z["id"] for z in lay["zones"]}
        self.assertEqual(len(views["views"]), 7)
        for v in views["views"]:
            self.assertTrue(v["zones"], v["id"])
            self.assertLessEqual(set(v["zones"]), ids, v["id"])

    def test_captions_name_the_plan(self):
        _, views = load_real()
        self.assertEqual(views["stamp"], "3D-кадр по плану #23")
        self.assertNotIn("черновик", json.dumps(views, ensure_ascii=False))

    def test_workshop_stands_behind_the_west_wall(self):
        lay, _ = load_real()
        wr = rv.workshop_rect(lay)
        self.assertEqual(wr[2], rv.room_box(lay)[0])
        for o in lay["workshop"]["objects"]:
            box = rv.footprint(o["position"], o["size_m"], o.get("rotation_deg", 0))
            self.assertTrue(rv.inside(box, wr), o["id"])

    def test_workshop_at_another_wall_is_not_built(self):
        lay, _ = load_real()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workshop.json"
            ws = json.loads(WORKSHOP.read_text(encoding="utf-8"))
            path.write_text(json.dumps(dict(ws, wallId="w_north")), encoding="utf-8")
            moved = rv.load_layout(ZONED, DRAFT, path)
        self.assertEqual(moved["workshop"]["objects"], [])
        self.assertEqual(moved["workshopSide"], lay["workshopSide"])


if __name__ == "__main__":
    unittest.main()
