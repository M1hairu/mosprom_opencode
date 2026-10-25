"""Plan of hall 219 (content/plan-219*.json): scale, contour, partitions, mirror.

Trap T2 (plan scale): the plan is calibrated by the 12 m column pitch, not by the
outline. Gate G7, scenario S6.3. Standard library only.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import plan_overlay  # noqa: E402

ORIGINAL = ROOT / "content" / "plan-219.json"
MIRROR = ROOT / "content" / "plan-219-mirror.json"
SLIDE = ROOT / "task" / "img" / "floor-plan.png"
PLAN_KEYS = {"schemaVersion", "id", "name", "room", "walls", "openings", "layers", "zones", "objects", "catalog", "extensions"}
WALL_KEYS = {"id", "from", "to", "thickness_m", "height_m"}
OPENING_KEYS = {"id", "wallId", "offset_m", "width_m", "kind", "sill_m", "height_m"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def overlay(plan: dict, mirror: bool) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = Path(tmp) / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return plan_overlay.run(plan_path, Path(tmp) / "out.png", SLIDE, mirror)


class PlanFormat(unittest.TestCase):
    def test_pochta_plan_document_fields(self):
        for path in (ORIGINAL, MIRROR):
            plan = load(path)
            self.assertEqual(set(plan), PLAN_KEYS, path.name)
            self.assertEqual(plan["schemaVersion"], 1)
            for wall in plan["walls"]:
                self.assertEqual(set(wall), WALL_KEYS, wall["id"])
            for opening in plan["openings"]:
                self.assertEqual(set(opening), OPENING_KEYS, opening["id"])
                self.assertIn(opening["kind"], {"entrance", "door", "window"})


class ColumnScaleT2(unittest.TestCase):
    """TRAP T2: scale from the column pitch 12 m, 2 rows of 4 columns."""

    def test_T2_two_rows_of_four_columns_12m_apart(self):
        for path in (ORIGINAL, MIRROR):
            columns = plan_overlay.plan_columns(load(path))
            self.assertEqual(len(columns), 8, path.name)
            self.assertEqual(len({round(y, 2) for _, y in columns}), 2)
            self.assertEqual(len({round(x, 2) for x, _ in columns}), 4)
            along_x, along_y = plan_overlay.column_pitches(columns)
            self.assertEqual(len(along_x), 6)
            self.assertEqual(len(along_y), 4)
            for pitch in along_x + along_y:
                self.assertAlmostEqual(pitch, 12.0, delta=0.5)

    def test_T2_hall_about_36_by_18_and_case_area_is_marked(self):
        plan = load(ORIGINAL)
        xs = [p[0] for p in plan["room"]["boundary"]]
        ys = [p[1] for p in plan["room"]["boundary"]]
        self.assertAlmostEqual(max(xs) - min(xs), 36.0, delta=0.5)
        self.assertAlmostEqual(max(ys) - min(ys), 18.0, delta=0.5)
        area = plan["extensions"]["plan219"]["area"]
        self.assertEqual(area["case_m2"], 626)
        self.assertEqual(area["status"], "оценка")

    def test_T2_plan_matches_the_slide(self):
        self.assertEqual(overlay(load(ORIGINAL), mirror=False), 0)
        self.assertEqual(overlay(load(MIRROR), mirror=True), 0)

    def test_T2_wrong_scale_is_caught(self):
        # A plan read with 1 grid square = 6 m taken as the column pitch: every
        # coordinate is half of the truth. The overlay must refuse it.
        plan = load(ORIGINAL)
        for wall in plan["walls"]:
            wall["from"] = [v / 2 for v in wall["from"]]
            wall["to"] = [v / 2 for v in wall["to"]]
        for opening in plan["openings"]:
            opening["offset_m"] /= 2
            opening["width_m"] /= 2
        for obj in plan["objects"]:
            obj["position"] = [v / 2 for v in obj["position"]]
        plan["room"]["boundary"] = [[x / 2, y / 2] for x, y in plan["room"]["boundary"]]
        self.assertEqual(overlay(plan, mirror=False), 1)


class WallsAndOpenings(unittest.TestCase):
    def test_contour_is_fixed_and_five_partitions_are_removable(self):
        plan = load(ORIGINAL)
        meta = plan["extensions"]["plan219"]["walls"]
        walls = {w["id"]: w for w in plan["walls"]}
        self.assertEqual(set(meta["fixedIds"]) | set(meta["removableIds"]), set(walls))
        self.assertFalse(set(meta["fixedIds"]) & set(meta["removableIds"]))
        boundary = plan["room"]["boundary"]
        edges = [(boundary[i], boundary[(i + 1) % len(boundary)]) for i in range(len(boundary))]

        def on_edge(wall):
            ends = sorted([tuple(wall["from"]), tuple(wall["to"])])
            return any(sorted([tuple(a), tuple(b)]) == ends for a, b in edges)

        self.assertTrue(all(on_edge(walls[i]) for i in meta["fixedIds"]))
        removable = [walls[i] for i in meta["removableIds"]]
        vertical = [w for w in removable if w["from"][0] == w["to"][0]]
        horizontal = [w for w in removable if w["from"][1] == w["to"][1]]
        self.assertEqual((len(vertical), len(horizontal)), (3, 2))

    def test_two_crossed_doors_on_top_two_openings_on_bottom(self):
        plan = load(ORIGINAL)
        meta = plan["extensions"]["plan219"]["openings"]
        walls = {w["id"]: w for w in plan["walls"]}
        top = [o for o in plan["openings"] if o["wallId"] == "w_north"]
        bottom = [o for o in plan["openings"] if o["wallId"] == "w_south"]
        self.assertEqual((len(top), len(bottom)), (2, 2))
        self.assertTrue(all(meta[o["id"]]["crossedOutRed"] for o in top))
        self.assertFalse(any(meta[o["id"]]["crossedOutRed"] for o in bottom))
        for o in plan["openings"]:
            wall = walls[o["wallId"]]
            self.assertLessEqual(o["offset_m"] + o["width_m"], plan_overlay.wall_length(wall))


class Mirror(unittest.TestCase):
    def test_mirror_is_reflection_about_x_18(self):
        original, mirror = load(ORIGINAL), load(MIRROR)
        width = max(p[0] for p in original["room"]["boundary"])

        def reflect(p):
            return [width - p[0], p[1]]

        def close(a, b):
            return all(math.isclose(u, v, abs_tol=1e-9) for u, v in zip(a, b))

        walls = {w["id"]: w for w in mirror["walls"]}
        self.assertEqual(set(walls), {w["id"] for w in original["walls"]})
        for wall in original["walls"]:
            self.assertTrue(close(reflect(wall["from"]), walls[wall["id"]]["from"]), wall["id"])
            self.assertTrue(close(reflect(wall["to"]), walls[wall["id"]]["to"]), wall["id"])
        self.assertEqual(original["openings"], mirror["openings"])
        objects = {o["id"]: o for o in mirror["objects"]}
        for obj in original["objects"]:
            self.assertTrue(close(reflect(obj["position"]), objects[obj["id"]]["position"]), obj["id"])
        self.assertEqual(mirror["extensions"]["plan219"]["variant"], "mirror")
        self.assertNotEqual(
            original["extensions"]["plan219"]["workshop"]["wallId"],
            mirror["extensions"]["plan219"]["workshop"]["wallId"],
        )


if __name__ == "__main__":
    unittest.main()
