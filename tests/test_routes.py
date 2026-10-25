"""Checks for content/routes.json (issue #22).

Shape: draft content/ contract #43 (routes.schema.json). Covers scenarios S1-S4, S8
(route criteria), trap T6 (6 audiences of slide 7) and gates G1, G2, G3, G5.
Stdlib only: runs under unittest and pytest.

Visit limit per route: `duration_max_min`. The values 90 / 60 / 40 are scenario
inputs (S1, S3, S4 in origin/arch/lassard:task/_arch/02-scenarios.md, marked
"(выдумано)"), not ЛАССАРД facts; customer 60 and media 45 are a concept decision.
Real visit length is [СПРОСИТЬ].
Each message has a slide-10 label (message prefix before ':'). Zones carry the slide-10 ids (zones.json, lint S10).
Client path: concept/01-layout.md, section 3 (steps 1-12; 12 = side stops 9-10).
"""
import json
import re
import unittest
from pathlib import Path

ROUTES = Path(__file__).resolve().parents[1] / "content" / "routes.json"
CONTENT = ROUTES.parent

# Slide 10: the 5 messages. Label is the message text prefix before ':'.
MESSAGES = {
    "Масштаб",
    "Богатая история",
    "Локализация",
    "Полный цикл",
    "Передовое российское производство",
}
BRIEFING = "Инструктаж"

ROLES = {"prospect", "customer", "education", "government", "students", "media"}
DETAILED = {"prospect", "customer", "education", "government"}
SLIDE3 = [
    "crystals", "quantrons", "diodes", "laser_sources", "robots",
    "engraving", "cutting", "handheld", "optomechanics", "edu_class",
]
# Client path in the hall (layout section 3), zones 2-9.
SLIDE3_LAYOUT = ["crystals", "quantrons", "diodes", "laser_sources", "robots", "engraving", "handheld", "cutting"]
ZONES = set(SLIDE3) | {"entrance", "meeting", "test_lab"}

# S4.1: hard limit for the government route, independent of duration_max_min.
GOVERNMENT_MAX_MIN = 40

# G5 / S3.3 / S8.1 (D-001, #152): there is no beam in the showroom. The demo zone takes
# guest samples; these roles never step into it. Robots, engraving and handheld are
# unpowered exhibits: any role may visit them or skip them for time.
DEMO_ZONE = {"test_lab"}
SAFE_ROLES = {"students", "media", "government", "education"}
BEAM_ZONES = {"robots", "engraving", "handheld"}

# D-001 (#152): a route message must not promise a live beam, a live process or a big machine.
LIVE_PROMISE = re.compile(
    r"открыт\w* луч|класса четыре|вживую|наносит|гравировка или очистка|очистка детали"
    r"|по согласованному режиму|окно передачи|только выставочно|новые станки резки|новых станков резки"
    r"|образцы реза\b"
    # a live-process verb near a beam or laser word: «включаем лазер», «лазер режет», «работает луч»
    r"|(?:включ|работ|реж[еу]|гравиру|очища|очистк|свар|маркиру)\w*\W+(?:\w+\W+){0,3}(?:луч|лазер)\w*"
    r"|(?:луч|лазер)\w*\W+(?:\w+\W+){0,3}(?:включ|работ|режет|режут|гравиру|очища|свар|маркиру)\w*"
    # a machine that cuts in the hall; «станки режут в цехе» is allowed
    r"|станк\w+ реж\w+\b(?! в цехе)"
)


def load():
    with ROUTES.open(encoding="utf-8") as f:
        return json.load(f)


def by_role(data):
    return {r["role"]: r for r in data["routes"]}


def zones(route):
    return [s["zone"] for s in route["steps"]]


def label(step):
    return step["message"].split(":", 1)[0].strip()


def text(route):
    return " ".join(s["message"] for s in route["steps"])


def render(message):
    """Like the guide renderer: {{fact:id}} -> fact text, {{item:id}} -> item name."""
    facts = {f["id"]: f["text"] for f in json.loads((CONTENT / "facts.json").read_text(encoding="utf-8"))["facts"]}
    items = {i["id"]: i["name"] for i in json.loads((CONTENT / "catalog.json").read_text(encoding="utf-8"))["items"]}
    return re.sub(
        r"\{\{(fact|item):([a-z0-9_.-]+)\}\}",
        lambda m: (facts if m.group(1) == "fact" else items)[m.group(2)],
        message,
    )


class Shape(unittest.TestCase):
    def setUp(self):
        self.data = load()

    def test_TRAP_6_six_audiences_four_detailed(self):
        # TRAP-6: 6 audiences on slide 7, 4 in detail on slide 9. All 6 have a route;
        # the 4 detailed ones (S1-S4) are prospect, customer, education, government.
        roles = {r["role"] for r in self.data["routes"]}
        self.assertEqual(roles, ROLES)
        self.assertEqual(len(roles), 6)
        self.assertLessEqual(DETAILED, roles)
        self.assertEqual(roles - DETAILED, {"students", "media"})

    def test_version_and_six_roles(self):
        # T6: every slide-7 audience has its own route.
        self.assertEqual(self.data["version"], 1)
        roles = [r["role"] for r in self.data["routes"]]
        self.assertEqual(sorted(roles), sorted(ROLES))

    def test_step_fields(self):
        for r in self.data["routes"]:
            self.assertTrue(r["steps"], r["role"])
            for s in r["steps"]:
                self.assertTrue({"zone", "minutes", "message"} <= set(s) <= {"zone", "minutes", "message", "carries"}, (r["role"], s))
                self.assertIn(s["zone"], ZONES, (r["role"], s))
                self.assertIsInstance(s["minutes"], int)
                self.assertGreaterEqual(s["minutes"], 1)
                self.assertIn(label(s), MESSAGES | {BRIEFING}, (r["role"], s))

    def test_no_digits_outside_fact_refs(self):
        # G1: a number in a text comes only from facts.json.
        for r in self.data["routes"]:
            for t in [s["message"] for s in r["steps"]] + [k["reason"] for k in r.get("skipped", [])]:
                bare = re.sub(r"\{\{(fact|item):[a-z0-9_.-]+\}\}", "", t)
                self.assertIsNone(re.search(r"\d", bare), (r["role"], t))

    def test_minutes_fit_visit(self):
        for r in self.data["routes"]:
            total = sum(s["minutes"] for s in r["steps"])
            self.assertGreaterEqual(r["duration_max_min"], 1, r["role"])
            self.assertLessEqual(total, r["duration_max_min"], r["role"])

    def test_government_fits_40(self):
        # S4.1
        gov = by_role(self.data)["government"]
        self.assertLessEqual(sum(s["minutes"] for s in gov["steps"]), GOVERNMENT_MAX_MIN)
        self.assertLessEqual(gov["duration_max_min"], GOVERNMENT_MAX_MIN)

    def test_briefing_first(self):
        # S3.4: briefing before the hall.
        for r in self.data["routes"]:
            self.assertEqual(label(r["steps"][0]), BRIEFING, r["role"])
            self.assertEqual(r["steps"][0]["zone"], "entrance", r["role"])

    def test_five_messages_in_every_route(self):
        # S1.8, S7.9
        for r in self.data["routes"]:
            got = {label(s) for s in r["steps"]} - {BRIEFING}
            self.assertEqual(got, MESSAGES, r["role"])

    def test_every_slide3_zone_is_visited_or_skipped_with_reason(self):
        for r in self.data["routes"]:
            skipped = {k["zone"]: k["reason"] for k in r.get("skipped", [])}
            for z in SLIDE3:
                self.assertTrue(z in zones(r) or skipped.get(z), (r["role"], z))
            self.assertFalse(set(skipped) & set(zones(r)), r["role"])


class LaserSafety(unittest.TestCase):
    """G5 and D-001 (#152): no beam in the showroom; students, media, government, education skip the demo zone."""

    def test_safe_roles(self):
        routes = by_role(load())
        for role in SAFE_ROLES:
            self.assertFalse(set(zones(routes[role])) & DEMO_ZONE, role)

    def test_no_message_promises_live_beam_or_process(self):
        for route in load()["routes"]:
            for step in route["steps"]:
                self.assertIsNone(LIVE_PROMISE.search(step["message"]), (route["role"], step["message"]))

    def test_skipped_reasons_do_not_cite_a_beam(self):
        # The gravers and handheld devices stand unpowered: «открытый луч» is no reason to skip a zone.
        for route in load()["routes"]:
            for k in route["skipped"]:
                self.assertNotIn("луч", k["reason"].lower(), (route["role"], k))
                self.assertNotIn("класса", k["reason"].lower(), (route["role"], k))

    def test_every_route_briefing_says_no_beam(self):
        for route in load()["routes"]:
            self.assertIn("луча нет", route["steps"][0]["message"], route["role"])

    def test_test_lab_no_live_process(self):
        # The demo zone shows one moving sample without a beam; the guest sample is processed in the workshop.
        for route in load()["routes"]:
            for step in route["steps"]:
                if step["zone"] == "test_lab":
                    self.assertIn("луча нет", step["message"], route["role"])
                    self.assertIn("в цех не входит", step["message"], route["role"])

    def test_cutting_is_miniature_not_machine(self):
        # D-001: no big machines in the hall: a 1:5 miniature and a 1:1 video stand; cutting only in the workshop.
        # Government has two short glass steps only: no machine is named there.
        for route in load()["routes"]:
            cut = " ".join(s["message"] for s in route["steps"] if s["zone"] == "cutting")
            if route["role"] != "government":
                self.assertIn("миниатюр", cut, route["role"])

    def test_handheld_is_unpowered(self):
        for route in load()["routes"]:
            for step in route["steps"]:
                if step["zone"] == "handheld":
                    self.assertIn("без питания", step["message"], route["role"])

    def test_students_and_education_visit_unpowered_zones(self):
        # Unpowered zones are relevant for school groups: short steps, not skipped.
        routes = by_role(load())
        for role in ("students", "education"):
            self.assertTrue(BEAM_ZONES <= set(zones(routes[role])), role)
            self.assertEqual([k["zone"] for k in routes[role]["skipped"]], ["test_lab"], role)

    def test_no_guide_instruction_in_guest_text(self):
        # #160 item 3: «"Лазерный класс" коротко» told the guide how to speak, not the guest what to see.
        for route in load()["routes"]:
            self.assertNotIn("коротко", text(route), route["role"])


class Prospect(unittest.TestCase):
    """S1."""

    def setUp(self):
        self.z = zones(by_role(load())["prospect"])

    def test_layout_steps_1_to_11(self):
        # concept/01-layout.md, section 3: steps 1-11; glass to the workshop ends the exposition.
        order = []
        for z in self.z:
            if z not in order:
                order.append(z)
        # #160: side stops 9-10 (optomechanics, edu_class) come after the meeting, on the way to the exit.
        self.assertEqual(order, ["entrance"] + SLIDE3_LAYOUT + ["test_lab", "meeting", "optomechanics", "edu_class"])

    def test_all_ten_zones_visited(self):
        # S1.3: all 10 zones of slide 3 are steps; nothing is skipped.
        route = by_role(load())["prospect"]
        self.assertTrue(set(SLIDE3) <= set(zones(route)))
        self.assertEqual(route["skipped"], [])

    def test_demo_zone_manager_takes_sample(self):
        # D-001 (#152): the manager takes the guest sample; it is processed in the workshop; the guest does not enter.
        # The guest does not watch their own sample: the glass step comes before the demo zone.
        for role in ("prospect", "customer"):
            route = by_role(load())[role]
            msg = [s["message"] for s in route["steps"] if s["zone"] == "test_lab"][0]
            self.assertIn("Менеджер принимает образец", msg, role)
            self.assertIn("в цехе", msg, role)
            self.assertIn("в цех не входит", msg, role)

    def test_partition_and_protocol(self):
        # S1.5, S1.6
        route = by_role(load())["prospect"]
        self.assertIn("перегородк", text(route))
        test_steps = [s["message"] for s in route["steps"] if s["zone"] == "test_lab"]
        self.assertEqual(len(test_steps), 1)
        for field in ("материал", "толщина", "режим", "время", "фото кромки", "панел"):
            self.assertIn(field, test_steps[0], field)


class Customer(unittest.TestCase):
    """S2."""

    def setUp(self):
        routes = by_role(load())
        self.route = routes["customer"]
        self.prospect = routes["prospect"]

    def test_differs_from_prospect(self):
        self.assertNotEqual(zones(self.route), zones(self.prospect))

    def test_service_stop(self):
        self.assertIn("сервис", text(self.route).lower())

    def test_ten_zones_in_order(self):
        seen = []
        for z in zones(self.route):
            if z in SLIDE3 and z not in seen:
                seen.append(z)
        self.assertEqual(seen, SLIDE3_LAYOUT + ["optomechanics", "edu_class"])

    def test_side_stops_order_after_meeting(self):
        # #160: the plan puts zones 9-10 (x 17.5-28) east of the meeting room (x 6.5-11.2), on the way to the main entrance op_south_2.
        # Visiting them after the meeting means no walk back west to the glass.
        for role in ("prospect", "customer"):
            z = zones(by_role(load())[role])
            self.assertEqual(z[-2:], ["optomechanics", "edu_class"], role)
            self.assertLess(max(i for i, n in enumerate(z) if n == "meeting"), z.index("optomechanics"), role)
            self.assertLess(z.index("cutting"), z.index("optomechanics"), role)

    def test_maintenance_fallback(self):
        cut = [s["message"] for s in self.route["steps"] if s["zone"] == "cutting"]
        self.assertTrue(any("обслуживании" in m for m in cut))


class Education(unittest.TestCase):
    """S3: zones 1-4 and laser class; teachers get the supply material."""

    def test_zones_and_teachers(self):
        r = by_role(load())["education"]
        self.assertTrue(set(SLIDE3[:4]) | {"edu_class"} <= set(zones(r)))
        self.assertIn("Преподавателям", text(r))


class Government(unittest.TestCase):
    """S4."""

    def setUp(self):
        self.route = by_role(load())["government"]
        self.t = text(self.route)

    def test_registry_with_localization_and_crystals(self):
        reg = [s["message"] for s in self.route["steps"] if "реестр" in s["message"]]
        self.assertTrue(any("{{fact:localization}}" in m and "кристалл" in m for m in reg))
        self.assertIn("crystals", zones(self.route))

    def test_named_facts(self):
        for ref in ("{{fact:employees}}", "{{fact:regions}}", "{{fact:technopolis_launch}}"):
            self.assertIn(ref, self.t)
        self.assertIn("Беларусь", render(self.t))

    def test_partition(self):
        self.assertIn("перегородк", self.t)


class Media(unittest.TestCase):
    """S8."""

    def test_media_point(self):
        t = text(by_role(load())["media"])
        self.assertIn("медиа-точка", t)
        self.assertIn("{{fact:localization}}", t)

    def test_handheld_weld_samples(self):
        """S8.2: instead of filming welding, media get weld samples and the guide video (D-001)."""
        steps = [s for s in by_role(load())["media"]["steps"] if s["zone"] == "handheld"]
        self.assertEqual(len(steps), 1)
        m = steps[0]["message"]
        self.assertIn("швов", m)
        self.assertIn("видео гида", m)


class Rendered(unittest.TestCase):
    """Messages read naturally after the fact texts are substituted (review of PR #148)."""

    def messages(self):
        for r in load()["routes"]:
            for i, st in enumerate(r["steps"]):
                yield r["role"], i, render(st["message"])

    def test_no_immediately_repeated_word(self):
        for role, i, t in self.messages():
            words = re.findall(r"[\w-]+", t.lower())
            for a, b in zip(words, words[1:]):
                self.assertNotEqual(a, b, (role, i, t))

    def test_no_repeated_phrase_in_one_message(self):
        # Two words (3+ letters each) that occur twice in one message: «экспорт в Беларусь» twice.
        for role, i, t in self.messages():
            words = [w for w in re.findall(r"[\w-]+", t.lower())]
            pairs = [(a, b) for a, b in zip(words, words[1:]) if len(a) >= 3 and len(b) >= 3]
            self.assertEqual(len(pairs), len(set(pairs)), (role, i, t))

    def test_power_fact_not_next_to_20_kw_source(self):
        # laser_power_max is the case number (9 kW). LS-FL20000 is 20 kW: they must not stand together.
        for role, i, t in self.messages():
            if "LS-FL20000" in t:
                self.assertNotIn("9 кВт", t, (role, i, t))

    def test_TRAP_5_rendered_says_products_not_machines(self):
        # TRAP-5: slide 3 says «30 видов станков», slide 9 says «30+ изделий». S4.4 wants «30+ видов изделий».
        seen = False
        for role, i, t in self.messages():
            self.assertNotIn("видов станков", t, (role, i, t))
            seen = seen or "более 30 видов изделий" in t
        self.assertTrue(seen)

    def test_rendered_has_no_leftover_refs(self):
        for role, i, t in self.messages():
            self.assertNotIn("{{", t, (role, i, t))


class Wording(unittest.TestCase):
    """G2 brand name; G3 wording; T5."""

    def setUp(self):
        self.raw = ROUTES.read_text(encoding="utf-8")

    def test_brand(self):
        self.assertIsNone(re.search(r"Лассард|ЛАССАРДа|Lassard", self.raw))

    def test_no_superlatives(self):
        self.assertIsNone(re.search(r"100\s*%", self.raw))
        self.assertIsNone(re.search(r"(?i)самый|самая|самое|лучш|лидер|№\s*\d", self.raw))

    def test_TRAP_5_no_30_machine_types_in_raw_text(self):
        self.assertNotIn("видов станков", self.raw)


if __name__ == "__main__":
    unittest.main()
