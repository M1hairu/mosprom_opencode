"""Tests for scripts/check-content.py (stdlib unittest; run by `make lint`)."""
import contextlib
import copy
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SCHEMAS = CONTENT / "schemas"
BROKEN = ROOT / "tests" / "fixtures" / "content-broken"
PLAN = "plan-219-zoned"  # PlanDocument v1 with zones (#46, #23); written as PLAN + ".json"

_spec = importlib.util.spec_from_file_location("check_content", ROOT / "scripts" / "check-content.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

# Rule tests mutate a small frozen zones example; the real content/zones.json (13 zones, #21)
# is checked whole by ExamplesTest and by tests/test_zones.py.
EXAMPLE_ZONES = {
    "version": 1,
    "zones": [
        {
            "id": "entrance", "name": "Входная зона", "exhibits": [],
            "display": "Стена хронологии и карта поставок.",
            "safety": {"restricted": False, "interlock": False}, "status": "normal",
            "carries": ["scale", "history", "localization", "full_cycle", "russian_production"],
            "messages": ["ЛАССАРД — российский производитель полного цикла: {{fact:area_production}}."],
        },
        {
            "id": "cutting", "name": "Лазерная резка", "exhibits": ["smart-base"],
            "display": "Станок {{item:smart-base}} стоит в зале. Резку показывает видео.",
            "safety": {"restricted": False, "interlock": False, "notes": ["Луч закрыт корпусом станка."]},
            "status": "normal", "carries": ["full_cycle"], "messages": ["Станок собран на площадке ЛАССАРД."],
        },
    ],
}

# Same for routes: rule tests mutate a frozen one-route example. The real content/routes.json
# (6 roles, #22) is checked whole by ExamplesTest and by tests/test_routes.py.
EXAMPLE_ROUTES = {
    "version": 1,
    "routes": [
        {
            "role": "prospect", "title": "Потенциальный клиент", "duration_max_min": 90,
            "steps": [
                {"zone": "entrance", "minutes": 10, "message": "Узнайте историю и масштаб ЛАССАРД."},
                {"zone": "cutting", "minutes": 15, "message": "Посмотрите станок {{item:smart-base}} и видео резки."},
            ],
            "skipped": [],
        },
    ],
}


def load_examples():
    docs = {n: json.loads((CONTENT / f"{n}.json").read_text(encoding="utf-8")) for n in cc.FILES}
    docs["zones"] = copy.deepcopy(EXAMPLE_ZONES)
    docs["routes"] = copy.deepcopy(EXAMPLE_ROUTES)
    docs[PLAN] = json.loads((CONTENT / f"{PLAN}.json").read_text(encoding="utf-8"))
    return docs


def run(docs, extra=None, schemas=SCHEMAS):
    """Write docs (name -> data) and extra files (filename -> data) to a temp dir and check it."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in docs.items():
            Path(tmp, f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        for fname, data in (extra or {}).items():
            Path(tmp, fname).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return cc.check(Path(tmp), schemas)


def joined(errors):
    return "\n".join(errors)


class ExamplesTest(unittest.TestCase):
    def test_content_examples_pass(self):
        self.assertEqual(cc.check(CONTENT, SCHEMAS), [])

    def test_broken_fixture_fails_on_each_trap(self):
        out = joined(cc.check(BROKEN, SCHEMAS))
        for marker in [
            "facts.json: $.facts[0]: число T8",
            "facts.json: $.facts[1]: число без источника",
            "catalog.json: $.items[0]: габарит неполный или без",
            "zones.json: $.zones[0]: статус maintenance",
            "zones.json: $.zones[0].safety.notes[0]: число в тексте",
            "zones.json: $.zones[0].messages[0]: число в тексте",
            "сообщение слайда 10 «scale»",
            "routes.json: $.routes[0]: сумма минут",
            "routes.json: $.routes[0].steps[0]: роль «students»",
            "routes.json: $.routes[0].steps[1]: нет зоны «lobby»",
            "plan-219.json: $.openings[0].wallId: «w_none» нет в walls",
            "plan-219.json: $.zones[1].id: зона «lobby» не из списка зон",
            "plan-219.json: $.objects[0].typeId: «ot_none» нет в catalog.objectTypes",
        ]:
            self.assertIn(marker, out)

    def test_cli_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cc.main([str(CONTENT), "--schemas", str(SCHEMAS)]), 0)
            self.assertEqual(cc.main([str(BROKEN), "--schemas", str(SCHEMAS)]), 1)


class SchemaSubsetTest(unittest.TestCase):
    def test_unknown_schema_keyword_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            schemas = Path(tmp)
            for f in SCHEMAS.glob("*.schema.json"):
                shutil.copy(f, schemas / f.name)
            s = json.loads((schemas / "routes.schema.json").read_text(encoding="utf-8"))
            s["properties"]["routes"]["maxItems"] = 6
            (schemas / "routes.schema.json").write_text(json.dumps(s), encoding="utf-8")
            out = joined(run(load_examples(), schemas=schemas))
        self.assertIn("ключ схемы «maxItems» не поддержан", out)

    def test_min_items(self):
        docs = load_examples()
        docs["routes"]["routes"][0]["steps"] = []
        self.assertIn("steps: элементов 0, нужно не меньше 1", joined(run(docs)))


class FactsTest(unittest.TestCase):
    def setUp(self):
        self.docs = load_examples()
        self.fact = self.docs["facts"]["facts"][0]

    def test_trap8_number_without_public_fails(self):
        """TRAP-8: case numbers vs public ones (80 %, 400+, 14 400 m2) need `public` (G14)."""
        for value, text in ((80, "80 %"), (0.8, "0.8"), (400, "400+ единиц в год"), (14400, "14 400 м²")):
            docs = copy.deepcopy(self.docs)
            f = docs["facts"]["facts"][0]
            f["value"], f["text"] = value, text
            f.pop("public")
            self.assertIn("(G14)", joined(run(docs)), value)

    def test_t8_text_is_a_whole_number(self):
        self.fact["value"], self.fact["text"] = 180, "180 % плана"
        self.fact.pop("public")
        self.assertEqual(run(self.docs), [])

    def test_t8_detected_by_text(self):
        self.fact["value"] = 1
        self.fact["text"] = "1 шоурум, 80 % локализации"
        self.fact.pop("public")
        self.assertIn("(G14)", joined(run(self.docs)))

    def test_text_must_contain_value(self):
        self.fact["text"] = "1 440 м²"
        self.assertIn("в «text» нет числа value=14400", joined(run(self.docs)))
        self.fact["value"], self.fact["text"] = 0.8, "80 %"
        self.assertIn("в «text» нет числа value=0.8", joined(run(self.docs)))

    def test_t8_number_with_public_passes(self):
        self.assertEqual(self.fact["value"], 14400)
        self.assertEqual(run(self.docs), [])

    def test_fact_without_any_source_fails(self):
        self.fact["value"], self.fact["text"] = 7, "7 зон"
        self.fact.pop("public")
        self.fact.pop("case")
        self.assertIn("число без источника", joined(run(self.docs)))

    def test_norm_is_a_source(self):
        self.fact["value"], self.fact["text"] = 2, "не меньше 2 выходов"
        self.fact.pop("public")
        self.fact.pop("case")
        self.fact["norm"] = {"doc": "СП 1.13130.2020", "clause": "4.2.7"}
        self.fact["check"] = True
        self.assertEqual(run(self.docs), [])

    def test_public_url_and_date_patterns(self):
        self.fact["public"]["url"] = "lassard.ru"
        self.fact["public"]["date"] = "23.10.2026"
        out = joined(run(self.docs))
        self.assertIn("public.url", out)
        self.assertIn("public.date", out)

    def test_extra_field_and_wrong_type(self):
        self.fact["source"] = "кейс"
        self.fact["value"] = "14 400"
        out = joined(run(self.docs))
        self.assertIn("лишнее поле «source»", out)
        self.assertIn("$.facts[0].value: ожидался тип number", out)

    def test_duplicate_id_path(self):
        n = len(self.docs["facts"]["facts"])  # the copy lands after all real facts
        self.docs["facts"]["facts"].append(copy.deepcopy(self.fact))
        self.assertIn(f"facts.json: $.facts[{n}]: повтор id «area_production»", joined(run(self.docs)))


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.docs = load_examples()
        self.item = self.docs["catalog"]["items"][0]

    def test_consumer_fields_pass(self):
        self.item["size_alt"] = [{"size_mm": {"length": 1170, "width": 706, "height": 1119}, "size_source": "каталог"}]
        self.item["power_w"] = {"min": 1000, "max": 3000, "source": "сайт"}
        self.item["price_from"] = {"value_rub": 1, "source": "сайт"}
        self.assertEqual(run(self.docs), [])

    def test_unknown_class_beam_and_size_are_explicit_nulls(self):
        self.item.update(laser_class=None, beam=None, size_mm=None, estimate=True, estimate_basis="нет данных")
        self.item.pop("size_source")
        self.assertEqual(run(self.docs), [])
        self.item.pop("laser_class")
        self.assertIn("нет поля «laser_class»", joined(run(self.docs)))

    def test_partial_or_null_size_needs_estimate_basis(self):
        self.item["size_mm"]["height"] = None
        self.assertIn("(G4)", joined(run(self.docs)))
        self.item["estimate"] = True
        self.assertIn("«estimate: true» без «estimate_basis»", joined(run(self.docs)))
        self.item["estimate_basis"] = "высота не опубликована"
        self.assertEqual(run(self.docs), [])

    def test_submillimetre_size(self):
        self.item["size_mm"] = {"length": 100, "width": 100, "height": 0.625}
        self.assertEqual(run(self.docs), [])
        self.item["size_mm"]["height"] = 0
        self.assertIn("меньше минимума", joined(run(self.docs)))


class ZonesTest(unittest.TestCase):
    def setUp(self):
        self.docs = load_examples()
        self.entrance, self.cutting = self.docs["zones"]["zones"]

    def test_each_slide10_message_is_carried(self):
        self.entrance["carries"] = ["history"]
        out = joined(run(self.docs))
        self.assertIn("«scale» не несёт ни одна зона", out)
        self.assertNotIn("«full_cycle» не несёт", out)

    def test_maintenance_needs_replacement(self):
        self.cutting["status"] = "maintenance"
        self.assertIn("(S2)", joined(run(self.docs)))
        self.cutting["maintenance"] = {"replacement": "Видео резки.", "zone": "entrance"}
        self.assertEqual(run(self.docs), [])
        self.cutting["maintenance"]["zone"] = "lobby"
        self.assertIn("maintenance.zone: нет зоны «lobby»", joined(run(self.docs)))

    def test_digits_in_any_visitor_text(self):
        self.cutting["safety"]["notes"] = ["Дистанция 2 м, мощность 9 кВт"]
        self.cutting["name"] = "Зона 7"
        out = joined(run(self.docs))
        self.assertIn("safety.notes[0]: число в тексте", out)
        self.assertIn("$.zones[1].name: число в тексте", out)

    def test_item_ref_allows_model_names_with_digits(self):
        self.docs["catalog"]["items"][0]["name"] = "LS-FL9000"
        self.cutting["messages"] = ["Источник {{item:smart-base}} работает в кабине."]
        self.assertEqual(run(self.docs), [])
        self.cutting["messages"] = ["Источник LS-FL9000."]
        self.assertIn("число в тексте", joined(run(self.docs)))
        # The id must not exist in the real content/catalog.json.
        self.cutting["messages"] = ["Источник {{item:ls-fl99999}}."]
        self.assertIn("неизвестный экспонат «ls-fl99999»", joined(run(self.docs)))

    def test_unknown_zone_id_and_status(self):
        self.cutting["id"] = "laser_class"
        self.cutting["status"] = "closed"
        out = joined(run(self.docs))
        self.assertIn("$.zones[1].id", out)
        self.assertIn("$.zones[1].status", out)


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.docs = load_examples()
        self.route = self.docs["routes"]["routes"][0]
        self.cutting = self.docs["zones"]["zones"][1]

    def test_restricted_roles_never_enter_closed_zones(self):
        cases = [
            ({"restricted": True, "interlock": False}, "cutting"),
            ({"restricted": False, "interlock": True}, "cutting"),
            ({"restricted": False, "interlock": False}, "test_lab"),
        ]
        for safety, zone_id in cases:
            docs = copy.deepcopy(self.docs)
            zone = docs["zones"]["zones"][1]
            zone["safety"], zone["id"] = safety, zone_id
            route = docs["routes"]["routes"][0]
            route["steps"][1]["zone"] = zone_id
            self.assertEqual(run(docs), [], (safety, zone_id))  # prospect may enter
            for role in ("students", "media", "government"):
                route["role"] = role
                self.assertIn(f"роль «{role}» не входит в зону «{zone_id}»", joined(run(docs)), (role, zone_id))

    def test_duration_limit_and_government_40(self):
        self.route["steps"][0]["minutes"] = 80
        self.assertIn("сумма минут 95 больше duration_max_min 90", joined(run(self.docs)))
        self.route["role"] = "government"
        self.route["steps"][0]["minutes"] = 30
        self.assertIn("(S4.1)", joined(run(self.docs)))

    def test_unique_role(self):
        self.docs["routes"]["routes"].append(copy.deepcopy(self.route))
        self.assertIn("routes.json: $.routes[1]: повтор role «prospect»", joined(run(self.docs)))

    def test_digits_in_title_and_skip_reason(self):
        self.route["title"] = "Клиент 2"
        self.route["skipped"] = [{"zone": "entrance", "reason": "закрыто 3 дня"}]
        out = joined(run(self.docs))
        self.assertIn("$.routes[0].title: число в тексте", out)
        self.assertIn("skipped[0].reason: число в тексте", out)

    def test_minutes_minimum(self):
        self.route["steps"][0]["minutes"] = 0
        self.assertIn("меньше минимума", joined(run(self.docs)))


class PlanTest(unittest.TestCase):
    """content/plan*.json is pochta PlanDocument v1: shape invariants and references."""

    def setUp(self):
        self.docs = load_examples()
        self.plan = self.docs[PLAN]
        self.fname = f"{PLAN}.json: $"

    def test_every_plan_file_is_checked(self):
        broken = copy.deepcopy(self.plan)
        broken["schemaVersion"] = 2
        out = joined(run(self.docs, {"plan-219.json": broken, "plan-219-mirror.json": self.plan}))
        self.assertIn("plan-219.json: $.schemaVersion", out)
        self.assertNotIn("plan-219-mirror.json", out)

    def test_at_least_one_plan(self):
        self.docs.pop(PLAN)
        self.assertIn("нет ни одного файла плана", joined(run(self.docs)))

    def test_shape_failure_skips_references(self):
        obj = self.plan["objects"][0]
        obj.pop("position")
        obj["typeId"] = "ot_none"
        out = joined(run(self.docs))
        self.assertIn("нет поля «position»", out)
        self.assertNotIn("ot_none", out)

    def test_references_inside_plan(self):
        self.plan["openings"][0]["wallId"] = "w_none"
        self.plan["zones"][0].update(typeId="zt_none", parentId="z_none", layerId="l_none")
        self.plan["objects"][0].update(typeId="ot_none", zoneId="z_none", layerId="l_none")
        out = joined(run(self.docs))
        for marker in [
            "$.openings[0].wallId: «w_none» нет в walls",
            "$.zones[0].typeId: «zt_none» нет в catalog.zoneTypes",
            "$.zones[0].parentId: «z_none» нет в zones",
            "$.zones[0].layerId: «l_none» нет в layers",
            "$.objects[0].typeId: «ot_none» нет в catalog.objectTypes",
            "$.objects[0].zoneId: «z_none» нет в zones",
            "$.objects[0].layerId: «l_none» нет в layers",
        ]:
            self.assertIn(f"{self.fname}{marker[1:]}", out)

    def test_plan_zone_is_a_zones_json_id(self):
        zone = self.plan["zones"][0]
        for obj in self.plan["objects"]:
            if obj["zoneId"] == zone["id"]:
                obj["zoneId"] = "lobby"
        zone["id"] = "lobby"
        self.assertIn("$.zones[0].id: зона «lobby» не из списка зон zones.json", joined(run(self.docs)))

    def test_unique_ids_in_plan(self):
        self.plan["objects"].append(copy.deepcopy(self.plan["objects"][0]))
        n = len(self.plan["objects"]) - 1
        self.assertIn(f"{self.fname}.objects[{n}]: повтор id", joined(run(self.docs)))

    def test_plan_type_must_exist_in_a_plan(self):
        self.docs["catalog"]["items"][0]["plan_type"] = "ot_none"
        self.assertIn("$.items[0].plan_type: нет типа «ot_none»", joined(run(self.docs)))

    def test_sub_zone_has_parent_from_zones_json(self):
        cabin = copy.deepcopy(self.plan["zones"][0])
        cabin.update(id="cutting_cabin", parentId="cutting")
        self.plan["zones"].append(cabin)
        self.assertEqual(run(self.docs), [])
        cabin["parentId"] = None
        self.assertIn("зона «cutting_cabin» не из списка зон zones.json", joined(run(self.docs)))


class BrandGatesTest(unittest.TestCase):
    def test_g2_rejects_brand_variants_in_cli(self):
        docs = load_examples()
        docs["zones"]["zones"][0]["display"] = "Лассард представляет оборудование"
        self.assertIn("(G2)", joined(run(docs)))

    def test_g3_rejects_superlatives_in_cli(self):
        docs = load_examples()
        docs["catalog"]["items"][0]["note"] = "Лучший станок"
        self.assertIn("(G3)", joined(run(docs)))


class PlanBrandGatesTest(unittest.TestCase):
    def test_plan_name_is_a_visitor_text(self):
        docs = load_examples()
        docs[PLAN]["name"] = "Лассард — лучший производитель"
        out = joined(run(docs))
        self.assertIn("(G2)", out)
        self.assertIn("(G3)", out)

    def test_plan_object_label_is_a_visitor_text(self):
        docs = load_examples()
        docs[PLAN]["objects"][0]["label"] = "100 % локализации"
        self.assertIn("(G3)", joined(run(docs)))

    def test_plan_provenance_and_ids_are_not_visitor_text(self):
        docs = load_examples()
        docs[PLAN]["id"] = "Лассард — лучший производитель"
        docs[PLAN]["extensions"]["source"] = {"note": "100 % из исходного документа"}
        self.assertEqual(run(docs), [])


if __name__ == "__main__":
    unittest.main()
