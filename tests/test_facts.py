"""Facts for the entrance and zones (#146) on the real content/ (stdlib unittest; make check)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

# ids that routes.json and zones.json refer to as {{fact:<id>}}
ENTRANCE_FACT_IDS = {
    "founded_kaluga", "technopolis_launch", "employees", "product_types", "optomech_items",
    "regions", "laser_power_max", "units_per_year", "localization", "gaas_melt_temp",
}


def load(name):
    return json.loads((CONTENT / f"{name}.json").read_text(encoding="utf-8"))


def facts():
    return {f["id"]: f for f in load("facts")["facts"]}


class FactIdsTest(unittest.TestCase):
    def test_entrance_fact_ids_exist_with_a_source(self):
        all_facts = facts()
        self.assertEqual(ENTRANCE_FACT_IDS - set(all_facts), set())
        for fid in ENTRANCE_FACT_IDS:
            self.assertTrue({"case", "public", "norm"} & set(all_facts[fid]), fid)

    def test_case_numbers_match_slide_3(self):
        expected = {"founded_kaluga": 2015, "technopolis_launch": 2023, "employees": 600,
                    "product_types": 30, "optomech_items": 100, "regions": 40,
                    "laser_power_max": 9, "units_per_year": 400, "localization": 80}
        all_facts = facts()
        for fid, value in expected.items():
            self.assertEqual(all_facts[fid]["value"], value, fid)
            self.assertEqual(all_facts[fid]["case"]["slide"], 3, fid)

    def test_gaas_melt_temp_is_a_public_physical_constant(self):
        fact = facts()["gaas_melt_temp"]
        self.assertEqual((fact["value"], fact["unit"]), (1240, "°C"))
        self.assertNotIn("case", fact)
        self.assertTrue(fact["public"]["url"].startswith("https://"))


class Trap8CaseVsPublicTest(unittest.TestCase):
    """TRAP-8: the case number and the public number differ. The registry keeps both."""

    def test_TRAP_8_units_per_year_keeps_case_and_public(self):
        fact = facts()["units_per_year"]
        self.assertEqual(fact["value"], 400)
        self.assertIn("400", fact["case"]["value"])
        self.assertIn("100+", fact["public"]["value"])
        # 400+ is design capacity, not output: the product text must say so
        self.assertIn("проектная мощность", fact["text"])

    def test_TRAP_8_localization_keeps_case_and_public(self):
        fact = facts()["localization"]
        self.assertEqual(fact["value"], 80)
        self.assertIn("80", fact["case"]["value"])
        self.assertIn("70", fact["public"]["value"])
        self.assertIs(fact.get("check"), True)

    def test_TRAP_8_every_t8_number_has_public(self):
        for fid, fact in facts().items():
            if fact["value"] in (80, 0.8, 400, 14400):
                self.assertIn("public", fact, fid)

    def test_area_production_public_does_not_state_site_count(self):
        # The note says the number of sites is not written: case and catalog disagree.
        value = facts()["area_production"]["public"]["value"]
        self.assertIn("14 400", value)
        self.assertNotRegex(value, r"\d\s+производственн\w+\s+площадк")


class ZoneCatalogItemsTest(unittest.TestCase):
    def test_robot_and_vgf_items_match_plan_types(self):
        items = {it["id"]: it for it in load("catalog")["items"]}
        plan_types = {t["id"] for t in load("plan-219-zoned")["catalog"]["objectTypes"]}
        for iid, plan_type in (("robot-graver-cell", "ot_robot_cell"), ("listopad-vgf", "ot_vgf")):
            self.assertEqual(items[iid]["plan_type"], plan_type)
            self.assertIn(plan_type, plan_types)
            self.assertTrue(items[iid]["estimate"])  # sizes are not published


if __name__ == "__main__":
    unittest.main()
