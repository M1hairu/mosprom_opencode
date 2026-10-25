"""Domain tests for the real content/zones.json (issues #21, #152): zone set, show method, S1.3, S2,
S5.4, D-001, TRAP-4.

Stdlib only. Run: python3 -m unittest tests/test_zones.py (make check runs it).
Format rules (schema, digits G1, brand G2, claims G3, refs, slide 10 coverage) are checked by
scripts/check-content.py in make lint and tested in tests/test_check_content.py. Not repeated here.
"""
import copy
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

_spec = importlib.util.spec_from_file_location("check_content", ROOT / "scripts" / "check-content.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

SLIDE3_ZONES = {
    "crystals", "quantrons", "diodes", "laser_sources", "robots", "engraving", "cutting",
    "handheld", "optomechanics", "edu_class",
}
ZONE_IDS = SLIDE3_ZONES | {"entrance", "meeting", "test_lab"}
# Zones with a machine, a video stand or a working unit: each has a replacement for maintenance (S2).
MACHINE_ZONES = {"crystals", "laser_sources", "robots", "engraving", "cutting", "handheld", "edu_class",
                 "test_lab"}
# D-001 (#152): no live beam in the showroom. Large equipment is a miniature under glass and a
# full-size video stand. Physically in the hall: only handheld units and engravers, unpowered.
BEAM_CATEGORIES = {"cutting", "engraving", "cleaning", "welding", "hardening"}
LARGE_IN_ZONE = {"smart-base": "cutting", "robot-graver-cell": "robots", "listopad-vgf": "crystals",
                 "ls-fl9000": "laser_sources", "ls-fl20000": "laser_sources"}
PHYSICAL_ALLOWED = {"multi-hero", "cleaner-prom", "welder-mini", "graver-compact", "graver-portal"}
NOT_PHYSICAL = ("миниатюр", "видео")
PROCESS_WORDS = ("резк","гравир", "маркир", "чистк", "сварк")
SHOW_WORDS = ("видео", "витрин", "стекл", "окно", "миниатюр", "симулятор", "стенд", "экран",
              "образц", "разрез")
UNPOWERED = "без питания"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def naming(zone, item_id):
    """Display sentences that name the exhibit by {{item:<id>}}."""
    ref = "{{item:" + item_id + "}}"
    return [s for s in sentences(zone["display"]) if ref in s]


def unpowered(zone, item_id):
    """True when a display sentence names the exhibit by {{item:<id>}} and says it is unpowered."""
    return any(UNPOWERED in s for s in naming(zone, item_id))


def shown_not_physically(zone, item_id):
    """True when every sentence naming the exhibit shows it as a miniature or video, not unpowered."""
    found = naming(zone, item_id)
    return bool(found) and all(any(w in s.lower() for w in NOT_PHYSICAL) and UNPOWERED not in s
                               for s in found)


def zone_texts(zone):
    """Visitor texts of a zone: name, display, messages, safety notes, maintenance replacement."""
    yield zone["name"]
    yield zone["display"]
    yield from zone["messages"]
    yield from zone["safety"].get("notes", [])
    if "maintenance" in zone:
        yield zone["maintenance"]["replacement"]


class ZonesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = load(CONTENT / "zones.json")
        cls.zones = {z["id"]: z for z in cls.raw["zones"]}
        cls.items = {it["id"]: it for it in load(CONTENT / "catalog.json")["items"]}

    def test_all_13_zones_once(self):
        ids = [z["id"] for z in self.raw["zones"]]
        self.assertEqual(len(ids), len(set(ids)), "zone id repeats")
        self.assertEqual(set(ids), ZONE_IDS)

    def test_slide3_zones_have_samples_and_show_method(self):
        # S1.3: every slide 3 zone names product samples and a way to show the process.
        for zid in SLIDE3_ZONES:
            z = self.zones[zid]
            with self.subTest(zone=zid):
                self.assertTrue(z["exhibits"], "zone without catalog exhibits")
                self.assertTrue(any(w in z["display"].lower() for w in SHOW_WORDS),
                                "display names no show method")

    def test_each_zone_carries_a_message(self):
        # Slide 10: every zone, not only the hall as a whole, carries at least one message.
        for zid, z in self.zones.items():
            with self.subTest(zone=zid):
                self.assertTrue(z["carries"])
                self.assertTrue(z["messages"])

    def test_crystals_no_live_growth(self):
        # S5.4: no live GaAs growth in the hall (melt, arsenic); samples, video, miniature (D-001).
        z = self.zones["crystals"]
        text = z["display"].lower()
        self.assertIn("живого роста в зале нет", text)
        self.assertIn("мышьяк", text)
        self.assertIn("плавления", text)
        self.assertIn("{{item:listopad-vgf}}", text)  # the item name renders as «Листопад»
        self.assertIn("видео", text)
        self.assertIn("миниатюр", text)
        self.assertEqual(set(z["exhibits"]), {"gaas-crystal", "gaas-wafer", "listopad-vgf"})
        self.assertFalse(z["safety"]["interlock"])

    def test_machine_zones_have_maintenance_replacement(self):
        # S2: a machine zone has its replacement ready; status is the only edit to switch.
        for zid in MACHINE_ZONES:
            z = self.zones[zid]
            with self.subTest(zone=zid):
                self.assertGreater(len(z["maintenance"]["replacement"]), 20)
                self.assertNotEqual(z["maintenance"].get("zone"), zid)

    def test_maintenance_is_one_edit(self):
        # S2.3, S2.6: zone 7 goes to maintenance and back by status only; content stays valid.
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(CONTENT, tmp, dirs_exist_ok=True)
            for status in ("maintenance", "normal"):
                data = copy.deepcopy(self.raw)
                next(z for z in data["zones"] if z["id"] == "cutting")["status"] = status
                Path(tmp, "zones.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                self.assertEqual(cc.check(Path(tmp), Path(tmp) / "schemas"), [], status)
        self.assertIn("огороженная зона обслуживания закрыта",
                      self.zones["cutting"]["maintenance"]["replacement"])

    def test_no_cutting_in_hall(self):
        # D-001: no cutting in the showroom; the guest sees cutting in the workshop behind the glass.
        self.assertIn("резки в зале нет", self.zones["cutting"]["display"].lower())
        self.assertIn("цех", self.zones["cutting"]["display"])
        self.assertIn("закрытом кожухе", self.zones["test_lab"]["display"])

    def test_D001_no_live_beam_in_any_zone(self):
        # D-001 (#152): no live cutting, engraving, cleaning or welding anywhere in the showroom.
        # No zone needs a laser room: no interlock. A live process word is allowed only for the workshop.
        for zid, z in self.zones.items():
            with self.subTest(zone=zid):
                self.assertFalse(z["safety"]["interlock"], "no laser room in the showroom")
                for text in zone_texts(z):
                    for sentence in sentences(text):
                        low = sentence.lower()
                        if re.search(r"\bжив\w*", low) and any(w in low for w in PROCESS_WORDS):
                            self.assertIn("цех", low, f"live process outside the workshop: {sentence}")
                        self.assertNotIn("вживую", low, sentence)
                        self.assertNotRegex(low, r"луч\w* работает", sentence)

    def test_D001_demo_zone_moving_sample_without_beam(self):
        # D-001 (#152): the demo zone has one moving sample and no laser; no beam equipment there.
        lab = self.zones["test_lab"]
        for ex in lab["exhibits"]:
            with self.subTest(exhibit=ex):
                self.assertNotIn(self.items[ex]["category"], BEAM_CATEGORIES)
        text = lab["display"].lower()
        self.assertIn("движущийся образец", text)
        self.assertIn("лазера и луча в зоне нет", text)

    def test_D001_large_equipment_only_miniature_and_video(self):
        # D-001 (#152): SMART BASE, the robot cell, LS-FL sources and «Листопад» are a miniature under
        # glass and a full-size video stand. The zone still names the real catalog item.
        for item_id, zid in LARGE_IN_ZONE.items():
            z = self.zones[zid]
            with self.subTest(item=item_id, zone=zid):
                self.assertIn(item_id, z["exhibits"])
                self.assertTrue(shown_not_physically(z, item_id), "large item not named as miniature or video")
                self.assertIn("миниатюр", z["display"].lower())
                self.assertIn("видеостенд", z["display"].lower())
        for zid, z in self.zones.items():
            for ex in z["exhibits"]:
                if ex.startswith("ls-fl") or ex in LARGE_IN_ZONE:
                    with self.subTest(zone=zid, exhibit=ex):
                        self.assertTrue(shown_not_physically(z, ex), "large item stands in the hall")

    def test_D001_physical_only_handheld_and_engravers_unpowered(self):
        # D-001 (#152): a beam device that stands in the hall is a handheld unit or an engraver, unpowered.
        seen = set()
        for zid, z in self.zones.items():
            for ex in z["exhibits"]:
                if self.items[ex]["category"] not in BEAM_CATEGORIES or shown_not_physically(z, ex):
                    continue
                with self.subTest(zone=zid, exhibit=ex):
                    self.assertIn(ex, PHYSICAL_ALLOWED, "beam device stands in the hall")
                    self.assertTrue(unpowered(z, ex), "exhibit not named as unpowered")
                seen.add(ex)
        self.assertEqual(seen, PHYSICAL_ALLOWED)

    def test_meeting_has_processing_samples_stand(self):
        # D-001 (#152): the meeting room holds a stand of processing samples for all four processes.
        text = self.zones["meeting"]["display"].lower()
        self.assertIn("стенд образцов", text)
        for word in ("резк", "сварк", "чистк", "маркировк"):
            with self.subTest(process=word):
                self.assertIn(word, text)

    def test_TRAP_4_open_beam_exhibit_unpowered(self):
        # TRAP-4: class 4 open beam (handheld lasers, open GRAVER; class unknown = treat as 4).
        # D-001 (#152): no laser room in the showroom, so such an exhibit is unpowered in the hall
        # or is not in the hall at all (miniature or video, e.g. the robot cell).
        checked = set()
        for zid, z in self.zones.items():
            for ex in z["exhibits"]:
                it = self.items[ex]
                if it["beam"] != "open" or it["laser_class"] not in ("4", None):
                    continue
                with self.subTest(zone=zid, exhibit=ex):
                    self.assertTrue(unpowered(z, ex) or shown_not_physically(z, ex),
                                    "open beam exhibit not named as unpowered, miniature or video")
                checked.add(ex)
        self.assertTrue({"multi-hero", "cleaner-prom", "welder-mini", "graver-compact"} <= checked)

    def test_robot_cell_and_vgf_are_zone_exhibits(self):
        # #150: the beam check reads only exhibits, so the cell and the VGF model must be listed.
        self.assertIn("robot-graver-cell", self.zones["robots"]["exhibits"])
        self.assertIn("listopad-vgf", self.zones["crystals"]["exhibits"])
        self.assertEqual(self.items["robot-graver-cell"]["beam"], "open")  # class unknown = open
        self.assertNotIn("Листопад", self.zones["crystals"]["display"])  # name comes from the item once

    def test_item_reference_occurs_once_per_display(self):
        # #150: render() puts the item name in the text, so a repeated reference repeats the name.
        for zid, z in self.zones.items():
            refs = re.findall(r"\{\{item:([^}]+)\}\}", z["display"])
            with self.subTest(zone=zid):
                self.assertEqual(len(refs), len(set(refs)), "item reference repeats in display")


if __name__ == "__main__":
    unittest.main()
