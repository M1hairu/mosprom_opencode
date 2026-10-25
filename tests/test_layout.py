"""Zoning of hall 219 (#23): content/plan-219*-zoned.json and scripts/plan_zones.py.

The checks are geometric: zone ids, areas, overlaps, columns, passages, exits and
the path to an exit. Each trap has a negative test: a broken plan must fail the check.
Standard library only.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import plan_zones  # noqa: E402

CONTRACT_ZONE_IDS = {
    "entrance", "crystals", "quantrons", "diodes", "laser_sources", "robots", "engraving",
    "cutting", "handheld", "optomechanics", "edu_class", "meeting", "test_lab",
}
FAKE_PATHS = {"hall": {"length_m": 1.0, "from": [0, 0], "zone": None}, "unreachableCells": 0}


def committed(variant: str) -> dict:
    return json.loads(plan_zones.OUT[variant].read_text(encoding="utf-8"))


def obj(plan: dict, oid: str) -> dict:
    return next(o for o in plan["objects"] if o["id"] == oid)


def zone(plan: dict, zid: str) -> dict:
    return next(z for z in plan["zones"] if z["id"] == zid)


def fast_check(plan: dict) -> dict:
    """check() without the grid path search: for traps that do not touch the path."""
    with mock.patch.object(plan_zones, "longest_paths", return_value=FAKE_PATHS):
        return plan_zones.check(plan)


class ZonedPlanTest(unittest.TestCase):
    results: dict[str, dict] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.plans = {v: committed(v) for v in plan_zones.VARIANTS}
        cls.results = {v: plan_zones.check(p) for v, p in cls.plans.items()}

    def test_files_are_generated(self) -> None:
        for v, plan in self.plans.items():
            with self.subTest(variant=v):
                self.assertEqual(plan, plan_zones.build(v), "run: python3 scripts/plan_zones.py --write")

    def test_zone_ids_are_contract_ids(self) -> None:
        for v, plan in self.plans.items():
            with self.subTest(variant=v):
                self.assertEqual({z["id"] for z in plan["zones"]}, CONTRACT_ZONE_IDS)
                self.assertEqual(len(plan["zones"]), len(CONTRACT_ZONE_IDS))
                self.assertNotIn("laser_class", json.dumps(plan))

    def test_no_failures(self) -> None:
        for v, result in self.results.items():
            with self.subTest(variant=v):
                self.assertEqual(plan_zones.failures(result), [])

    def test_area_sum_fits_hall(self) -> None:
        for v, result in self.results.items():
            with self.subTest(variant=v):
                self.assertLessEqual(result["zoneAreaSum_m2"], 626)
                self.assertTrue(all(a > 0 for a in result["zoneAreas_m2"].values()))

    def test_geometry_is_clean(self) -> None:
        for v, r in self.results.items():
            with self.subTest(variant=v):
                for key in ("zonesOutsideRoom", "zoneOverlaps", "objectsOutsideZone", "columnClashes",
                            "wallClashes", "narrowPassages", "narrowExits", "blockedExitApproaches"):
                    self.assertEqual(r[key], [], key)

    def test_exits(self) -> None:
        for v, r in self.results.items():
            with self.subTest(variant=v):
                self.assertGreaterEqual(len(plan_zones.CONFIRMED_EXITS), 2)
                self.assertTrue(all(w >= 1.2 for w in r["exitWidths_m"].values()))

    def test_exit_spacing_finding_is_recorded(self) -> None:
        # The two confirmed exits are 15 m apart: less than half of the diagonal (20.09 m).
        # This is a finding for the doc, not a pass. The candidate door fixes it.
        for v, r in self.results.items():
            with self.subTest(variant=v):
                s = r["exitSpacing"]
                self.assertAlmostEqual(s["halfDiagonal_m"], 20.09, places=2)
                self.assertLess(s["confirmed_m"], s["halfDiagonal_m"])
                self.assertGreaterEqual(s["withCandidate_m"], s["halfDiagonal_m"])
                # Far edges give 19.05 m: still less than 20.09 m, so the finding does not
                # depend on the measuring method.
                self.assertAlmostEqual(s["confirmedFarEdges_m"], 19.05, places=2)
                self.assertLess(s["confirmedFarEdges_m"], s["halfDiagonal_m"])

    def test_max_path_to_exit(self) -> None:
        for v, r in self.results.items():
            with self.subTest(variant=v):
                mp = r["maxPath"]
                self.assertLessEqual(mp["confirmedExits"]["hall"]["length_m"], plan_zones.MAX_PATH_C0_M)
                self.assertEqual(mp["confirmedExits"]["unreachableCells"], 0)
                self.assertLessEqual(mp["withBothNorthDoors"], plan_zones.MAX_PATH_C1_M)

    def test_route_order(self) -> None:
        route = plan_zones.ROUTE
        self.assertEqual(route[0], "entrance")
        self.assertEqual(route[1:5], ["crystals", "quantrons", "diodes", "laser_sources"])
        self.assertEqual(set(route[5:9]), {"robots", "engraving", "cutting", "handheld"})
        self.assertEqual(route[-3:], ["cutting", "test_lab", "meeting"])
        for v, plan in self.plans.items():
            with self.subTest(variant=v):
                ext = plan["extensions"]["zoning219"]
                self.assertEqual(ext["route"], route)
                self.assertEqual(sorted(ext["route"] + ext["sideStops"]), sorted(CONTRACT_ZONE_IDS))
                self.assertTrue(self.results[v]["routeOrder"])

    def test_glass_and_demo_zone_on_workshop_wall(self) -> None:
        for v, plan in self.plans.items():
            with self.subTest(variant=v):
                wall = plan["extensions"]["zoning219"]["workshopWallId"]
                ops = {o["id"]: o for o in plan["openings"]}
                self.assertEqual(ops["op_glass_workshop"]["wallId"], wall)
                self.assertEqual(ops["op_lab_workshop"]["wallId"], wall)
                xs = [p[0] for p in zone(plan, "test_lab")["polygon"]]
                self.assertEqual(min(xs), 0)

    def test_base_plan_notes(self) -> None:
        for v, path in plan_zones.BASE.items():
            with self.subTest(variant=v):
                p219 = json.loads(path.read_text(encoding="utf-8"))["extensions"]["plan219"]
                self.assertIn("Причина неизвестна [СПРОСИТЬ]", p219["area"]["note"])
                self.assertIn("634,5", p219["area"]["note"])
                # The workshop side is the team's choice: the note names its source (#224).
                self.assertIn("эксперт ЛАССАРД, 24.10", p219["workshop"]["status"])
        mirror = json.loads(plan_zones.BASE["mirror"].read_text(encoding="utf-8"))
        self.assertIn("w_west в этом файле лежит справа, x = 36", mirror["extensions"]["plan219"]["workshop"]["status"])


class TrapTest(unittest.TestCase):
    """Negative tests: each broken plan must fail."""

    def setUp(self) -> None:
        self.plan = copy.deepcopy(committed("original"))

    def test_column_clash_is_caught(self) -> None:
        obj(self.plan, "ex_scale")["position"] = [24.0, 3.8]  # col_A3
        obj(self.plan, "ex_scale")["zoneId"] = "edu_class"
        r = fast_check(self.plan)
        self.assertIn(["ex_scale", "col_A3"], r["columnClashes"])
        self.assertTrue(plan_zones.failures(r))

    def test_zone_overlap_is_caught(self) -> None:
        zone(self.plan, "meeting")["polygon"] = plan_zones.rect_polygon([6.0, 0, 11.2, 5])
        r = fast_check(self.plan)
        self.assertTrue(any({"meeting", "test_lab"} == {a, b} for a, b, _ in r["zoneOverlaps"]))
        self.assertTrue(plan_zones.failures(r))

    def test_narrow_passage_is_caught(self) -> None:
        obj(self.plan, "ex_sim_desk_2")["position"] = [26.0, 5.6]  # 0.1 m from ex_sim_desk_1
        r = fast_check(self.plan)
        self.assertTrue(any({"ex_sim_desk_1", "ex_sim_desk_2"} == {a, b} for a, b, _ in r["narrowPassages"]))
        self.assertTrue(plan_zones.failures(r))

    def test_hall_passage_of_1_1_m_is_caught(self) -> None:
        # Evacuation path in the hall is 1.2 m (05-safety 4.2: 90 people, SP 1.13130.2020, 4.3.3).
        # PR #90 had these 1.1 m passages; 1.0 m was the old threshold.
        cases = [
            ("original", "ex_timeline", [35.7, 7.3], {"ex_timeline", "col_A4"}),
            ("mirror", "ex_scale", [22.3, 3.8], {"ex_scale", "col_A2"}),
            ("mirror", "ex_mirea", [31.33, 2.0], {"ex_mirea", "ex_laminar"}),
            ("mirror", "ex_map", [20.5, 7.0], {"ex_timeline", "ex_map"}),
        ]
        for variant, oid, pos, pair in cases:
            with self.subTest(variant=variant, object=oid):
                plan = copy.deepcopy(committed(variant))
                obj(plan, oid)["position"] = pos
                narrow = plan_zones.narrow_passages(plan)
                hit = [g for a, b, g in narrow if {a, b} == pair]
                self.assertEqual(hit, [1.1])
                self.assertTrue(plan_zones.failures(fast_check(plan)))

    def test_hall_gap_to_wall_is_caught(self) -> None:
        obj(self.plan, "ex_gaas")["position"] = [34.5, 12.5]  # 0.82 m from the east wall
        narrow = plan_zones.narrow_passages(self.plan)
        self.assertTrue(any(a == "ex_gaas" and b == "w_east" for a, b, _ in narrow))

    def test_small_room_keeps_1_0_m(self) -> None:
        # Meeting room: 6-8 seats, fewer than 50 people -> 1.0 m (SP 1.13130.2020, 4.3.3).
        table = plan_zones.object_box(obj(self.plan, "ex_meeting_table"))
        g = min(plan_zones.gap(table, w) for _i, w in plan_zones.solid_walls(self.plan))
        self.assertTrue(1.0 <= g < 1.2, g)
        self.assertFalse(any(a == "ex_meeting_table" for a, _b, _g in plan_zones.narrow_passages(self.plan)))
        obj(self.plan, "ex_meeting_table")["position"] = [8.85, 3.8]  # 0.6 m from w_meet_n
        self.assertTrue(any(a == "ex_meeting_table" for a, _b, _g in plan_zones.narrow_passages(self.plan)))

    def test_narrow_exit_is_caught(self) -> None:
        next(o for o in self.plan["openings"] if o["id"] == "op_south_2")["width_m"] = 1.0
        r = fast_check(self.plan)
        self.assertIn("op_south_2", r["narrowExits"])
        self.assertTrue(plan_zones.failures(r))

    def test_blocked_exit_is_caught(self) -> None:
        obj(self.plan, "ex_scale")["position"] = [32.4, 1.8]  # in front of op_south_2
        r = fast_check(self.plan)
        self.assertTrue(any(e == "op_south_2" for e, _ in r["blockedExitApproaches"]))
        self.assertTrue(plan_zones.failures(r))

    def test_area_over_hall_is_caught(self) -> None:
        zone(self.plan, "entrance")["polygon"] = plan_zones.rect_polygon([-100, 0, 36, 9.5])
        r = fast_check(self.plan)
        self.assertGreater(r["zoneAreaSum_m2"], 626)
        self.assertTrue(plan_zones.failures(r))

    def test_one_exit_breaks_path_limit(self) -> None:
        # With op_south_1 closed the far corner is more than 30 m from op_south_2.
        paths = plan_zones.longest_paths(self.plan, ["op_south_2"])
        self.assertGreater(paths["hall"]["length_m"], plan_zones.MAX_PATH_C0_M)

    def test_no_exit_leaves_cells_unreachable(self) -> None:
        paths = plan_zones.longest_paths(self.plan, [])
        self.assertGreater(paths["unreachableCells"], 0)



def plan_texts(value) -> list[str]:
    """Every string inside a JSON value."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in plan_texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in plan_texts(v)]
    return []


class D001PlanTest(unittest.TestCase):
    """D-001 (#152, #193): no laser works in the hall; large equipment is a 1:5 miniature."""

    # Large equipment of D-001: SMART BASE, the robot cell, LS-FL, Nd:YAG and «Листопад».
    LARGE = {"ot_smart_base", "ot_robot_cell", "ot_ls_fl9000", "ot_ls_fl20000", "ot_ndyag", "ot_vgf"}
    OLD_D001 = re.compile(r"работа[ею]т|вживую|допуск", re.IGNORECASE)

    def test_no_plan_text_says_a_laser_works_or_admission_only(self) -> None:
        for v in plan_zones.VARIANTS:
            with self.subTest(variant=v):
                plan = committed(v)
                texts = [o["label"] for o in plan["objects"]]
                texts += [t["label"] for t in plan["catalog"]["objectTypes"]]
                texts += [t["provenance"] for t in plan["catalog"]["objectTypes"]]
                texts += plan_texts(plan["extensions"]["zoning219"])
                self.assertEqual([t for t in texts if self.OLD_D001.search(t)], [])

    def test_large_equipment_stands_only_as_a_1_to_5_miniature(self) -> None:
        for v in plan_zones.VARIANTS:
            with self.subTest(variant=v):
                plan = committed(v)
                types = {t["id"]: t for t in plan["catalog"]["objectTypes"]}
                large = [o for o in plan["objects"] if o["typeId"] in self.LARGE]
                self.assertEqual({o["typeId"] for o in large}, self.LARGE)
                for o in large:
                    self.assertIn("Миниатюра", o["label"], o["id"])
                    self.assertIn("1:5", o["label"], o["id"])
                    self.assertIn("1:5", types[o["typeId"]]["provenance"], o["id"])


def segment_hits_box(a, b, box, step: float = 0.05) -> bool:
    n = max(1, int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 / step))
    for k in range(n + 1):
        t = k / n
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        if box[0] < x < box[2] and box[1] < y < box[3]:
            return True
    return False


class RouteLineTest(unittest.TestCase):
    """The route line on the PNG (scripts/plan_png.py) does not cross a stand or a wall."""

    def test_route_line_misses_objects_and_walls(self) -> None:
        for variant in plan_zones.VARIANTS:
            with self.subTest(variant=variant):
                plan = committed(variant)
                line = plan_zones.route_line(plan)
                boxes = [plan_zones.object_box(o) for o in plan["objects"]] + plan_zones.solid_wall_boxes(plan)
                hits = [(i, box) for i, (a, b) in enumerate(zip(line, line[1:]))
                        for box in boxes if segment_hits_box(a, b, box)]
                self.assertEqual(hits, [])

    def test_route_line_visits_every_stop_in_order(self) -> None:
        for variant in plan_zones.VARIANTS:
            with self.subTest(variant=variant):
                plan = committed(variant)
                stops, line = plan_zones.route_stops(plan), plan_zones.route_line(plan)
                self.assertEqual(len(stops), len(plan_zones.ROUTE))
                idx = [line.index(s) for s in stops]
                self.assertEqual(idx, sorted(idx))
                self.assertEqual((line[0], line[-1]), (stops[0], stops[-1]))

    def test_stop_marks_do_not_cover_stands(self) -> None:
        for variant in plan_zones.VARIANTS:
            with self.subTest(variant=variant):
                plan = committed(variant)
                for x, y in plan_zones.route_stops(plan):
                    for o in plan["objects"]:
                        b = plan_zones.object_box(o)
                        dx, dy = max(b[0] - x, 0, x - b[2]), max(b[1] - y, 0, y - b[3])
                        self.assertGreaterEqual((dx * dx + dy * dy) ** 0.5, 0.45, o["id"])

    def test_stop_marks_keep_clear_of_labels(self) -> None:
        # A label box over each default stop: every stop moves at least STOP_MARK_R_M away.
        plan = committed("original")
        stops = plan_zones.route_stops(plan)
        labels = [(x - 0.8, y - 0.1, x + 0.8, y + 0.1) for x, y in stops]
        moved = plan_zones.route_stops(plan, labels)
        for x, y in moved:
            for b in labels:
                dx, dy = max(b[0] - x, 0, x - b[2]), max(b[1] - y, 0, y - b[3])
                self.assertGreaterEqual((dx * dx + dy * dy) ** 0.5, plan_zones.STOP_MARK_R_M)
        line = plan_zones.route_line(plan, moved)
        self.assertEqual((line[0], line[-1]), (moved[0], moved[-1]))


if __name__ == "__main__":
    unittest.main()
