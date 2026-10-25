"""Data traps and issue #20 rules on the real content/catalog.json (stdlib unittest; make check)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "content" / "catalog.json"

# Hand lasers and open GRAVER models: open class 4 beam, live work only in a cabin (G5, G19).
OPEN_BEAM_IDS = {"multi-hero", "welder-mini", "cleaner-case", "cleaner-prom",
                 "graver-compact", "graver-mobile", "graver-line", "graver-uv"}
# lassard.ru/services/demonstration: 9 machines; both LEADER fields are one item "leader".
CURRENT_SHOWROOM_IDS = {"leader", "optimum", "smart-base", "smart-5d", "multi-hero",
                        "cleaner-case", "welder-mini", "graver-3d"}
# Catalog 2026, page 2 (table of contents): 33 positions; SMART XL is split by field.
CATALOG_2026_IDS = {
    "smart-base", "smart-xl-1300x800", "optimum", "leader", "leader-y", "sirius", "optimum-tube",
    "tube-long", "tube-prime", "smart-turn", "smart-round", "smart-5d", "premium-5d", "master",
    "lfilter-smart", "lfilter-optimum", "lfilter-leader", "paladin", "laserhard",
    "graver-3d", "graver-compact", "graver-line", "graver-mobile", "graver-portal", "graver-uv",
    "multi-hero", "welder-mini", "welder-mini-2000", "welder-tt", "scanwelder",
    "cleaner-case", "cleaner-prom", "cleaner-portal",
}


def load_items():
    return {it["id"]: it for it in json.loads(CATALOG.read_text(encoding="utf-8"))["items"]}


class Trap3SmartBaseFieldTest(unittest.TestCase):
    """TRAP-3: SMART BASE in the catalog shows the 800 x 800 mm field; it is not the machine size."""

    def setUp(self):
        self.items = load_items()

    def test_TRAP_3_smart_base_800_is_work_area_not_size(self):
        sb = self.items["smart-base"]
        area = sb["work_area_mm"]
        self.assertEqual((area["length"], area["width"]), (800, 800))
        self.assertTrue(area["source"])
        size = sb["size_mm"]
        self.assertGreater(size["length"], 800)
        self.assertGreater(size["width"], 800)

    def test_TRAP_3_smart_base_size_is_official_with_source(self):
        sb = self.items["smart-base"]
        self.assertFalse(sb["estimate"])
        self.assertIn("Katalog_oborudovanie_2026", sb["size_source"])

    def test_TRAP_3_footprint_is_larger_than_work_area(self):
        for iid, it in self.items.items():
            area, size = it.get("work_area_mm"), it.get("size_mm")
            if area is None or size is None or None in (size["length"], size["width"]):
                continue
            foot = sorted((size["length"], size["width"]))
            field = sorted((area["length"], area["width"]))
            with self.subTest(item=iid):
                self.assertGreater(foot[0], field[0])
                self.assertGreater(foot[1], field[1])


class Trap4OpenBeamTest(unittest.TestCase):
    """TRAP-4: class 4 beam of hand lasers and SMART BASE."""

    def setUp(self):
        self.items = load_items()

    def test_TRAP_4_hand_lasers_and_open_gravers_have_open_beam(self):
        for iid in sorted(OPEN_BEAM_IDS):
            with self.subTest(item=iid):
                self.assertEqual(self.items[iid]["beam"], "open")

    def test_TRAP_4_smart_base_is_class_4_in_a_cabinet(self):
        sb = self.items["smart-base"]
        self.assertEqual(sb["laser_class"], "4")
        self.assertEqual(sb["beam"], "closed")

    def test_TRAP_4_open_beam_items_say_no_beam_in_showroom(self):
        # D-001: no beam in the showroom; no cabin either.
        for iid, it in self.items.items():
            if it["beam"] == "open":
                note = it.get("note", "")
                with self.subTest(item=iid):
                    self.assertIn("D-001", note)
                    self.assertIn("TRAP-4", note)
                    self.assertIn("луча нет", note)
                    self.assertNotIn("в кабине", note)


class CatalogRulesTest(unittest.TestCase):
    """Issue #20: coverage, current showroom, MULTI HERO sizes."""

    def setUp(self):
        self.items = load_items()

    def test_catalog_2026_positions_are_present(self):
        self.assertEqual(len(CATALOG_2026_IDS), 33)
        self.assertEqual(CATALOG_2026_IDS - set(self.items), set())

    def test_components_optomechanics_and_laser_class_are_present(self):
        cats = {it["category"] for it in self.items.values()}
        self.assertTrue({"component", "optomechanics", "education"} <= cats)
        for iid in ("ls-fl9000", "ls-fl20000", "ls-fl30000", "ls-fl50000", "gaas-wafer",
                    "quantron-qcw", "mirea-kit", "laminar-66lb-alm", "laser-class"):
            self.assertIn(iid, self.items)

    def test_current_showroom_matches_demonstration_page(self):
        shown = {iid for iid, it in self.items.items() if it["in_current_showroom"]}
        self.assertEqual(shown, CURRENT_SHOWROOM_IDS)

    def test_multi_hero_has_both_published_sizes_with_sources(self):
        mh = self.items["multi-hero"]
        sizes = [(mh["size_mm"], mh["size_source"])] + [(a["size_mm"], a["size_source"]) for a in mh["size_alt"]]
        dims = {(s["length"], s["width"], s["height"]) for s, _ in sizes}
        self.assertEqual(dims, {(1170, 706, 1119), (1102, 700, 1266)})
        self.assertTrue(all(src for _, src in sizes))

    def test_official_size_is_complete_with_source(self):
        for iid, it in self.items.items():
            with self.subTest(item=iid):
                if it["estimate"]:
                    self.assertTrue(it.get("estimate_basis"))
                else:
                    self.assertTrue(it.get("size_source"))
                    self.assertNotIn(None, it["size_mm"].values())

    def test_no_superlatives_or_100_percent(self):
        text = CATALOG.read_text(encoding="utf-8").lower()
        for word in ("100 %", "100%", "самый", "самая", "самое", "крупнейш", "лучш", "уникальн"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
