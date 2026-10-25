"""Tests for scripts/estimate.py and the rationale section (task #25).

Run: python3 -m unittest tests/test_estimate.py
"""

import copy
import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "estimate.py"
DATA = ROOT / "content" / "estimate.json"
RATIONALE = ROOT / "concept" / "06-rationale.md"
QA = ROOT / "pitch" / "QA.md"
PLANS = [ROOT / "content" / "plan-219-zoned.json", ROOT / "content" / "plan-219-mirror-zoned.json"]

_spec = importlib.util.spec_from_file_location("estimate", SCRIPT)
estimate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(estimate)


def sourced(item_id, article, qty, price, quality="page"):
    return {
        "id": item_id,
        "article": article,
        "name": item_id,
        "qty": qty,
        "unit": "шт.",
        "unit_price": price,
        "qty_basis": "test",
        "source": {"url": "https://example.ru", "note": "n", "date": "2026-10-23", "quality": quality},
    }


def estimated(item_id, article, qty, price):
    return {
        "id": item_id,
        "article": article,
        "name": item_id,
        "qty": qty,
        "unit": "шт.",
        "unit_price": price,
        "qty_basis": "test",
        "estimate": True,
        "basis": "assumption",
    }


FIXTURE = {
    "items": [
        sourced("a", "Отделка", 10, 1000),               # 10 000, page
        sourced("b", "Отделка", 2, 2500, "snippet"),     # 5 000, snippet
        estimated("c", "Кабины", 1, 5000),               # 5 000, estimate
    ],
    "exhibits": {"items": [{"name": "X", "price": 7000}]},
}


class SummaryTest(unittest.TestCase):
    def test_totals_and_shares(self):
        s = estimate.summarize(FIXTURE)
        self.assertEqual(s["total"], 20000)
        self.assertEqual(s["sourced"], 15000)
        self.assertEqual(s["sourced_page"], 10000)
        self.assertEqual(s["estimated"], 5000)
        self.assertAlmostEqual(s["share"], 0.75)
        self.assertAlmostEqual(s["share_page"], 0.5)

    def test_per_article(self):
        s = estimate.summarize(FIXTURE)
        self.assertEqual(s["articles"]["Отделка"], {"total": 15000, "sourced": 15000})
        self.assertEqual(s["articles"]["Кабины"], {"total": 5000, "sourced": 0})

    def test_exhibits_not_in_total(self):
        s = estimate.summarize(FIXTURE)
        self.assertEqual(s["exhibits"], 7000)
        self.assertEqual(s["total"], 20000)

    def test_render_has_no_full_share_claim(self):
        # Gate G3: the PR body carries this output; no "100 %" in it.
        data = {"items": [sourced("a", "Проект", 1, 1000)]}
        out = estimate.render(estimate.summarize(data))
        self.assertIn("Итого: 1 000 ₽", out)
        self.assertNotRegex(out, r"100(,0)?\s*%")


class ValidateTest(unittest.TestCase):
    def test_fixture_is_valid(self):
        self.assertEqual(estimate.validate(FIXTURE), [])

    def test_line_needs_source_or_estimate(self):
        data = copy.deepcopy(FIXTURE)
        del data["items"][0]["source"]
        errors = estimate.validate(data)
        self.assertTrue(any("exactly one" in e for e in errors), errors)

    def test_line_cannot_have_both(self):
        data = copy.deepcopy(FIXTURE)
        data["items"][0]["estimate"] = True
        data["items"][0]["basis"] = "x"
        errors = estimate.validate(data)
        self.assertTrue(any("exactly one" in e for e in errors), errors)

    def test_estimate_needs_basis(self):
        data = copy.deepcopy(FIXTURE)
        data["items"][2]["basis"] = " "
        errors = estimate.validate(data)
        self.assertTrue(any("basis" in e for e in errors), errors)

    def test_source_needs_date_and_quality(self):
        data = copy.deepcopy(FIXTURE)
        data["items"][0]["source"]["date"] = ""
        data["items"][0]["source"]["quality"] = "guess"
        errors = estimate.validate(data)
        self.assertTrue(any("'date'" in e for e in errors), errors)
        self.assertTrue(any("quality" in e for e in errors), errors)

    def test_source_needs_url(self):
        # Review of PR #49: a note without URL is not a source, for both qualities.
        for quality in ("page", "snippet"):
            data = copy.deepcopy(FIXTURE)
            data["items"][0]["source"]["quality"] = quality
            data["items"][0]["source"]["url"] = " "
            errors = estimate.validate(data)
            self.assertTrue(any("non-empty 'url'" in e for e in errors), (quality, errors))

    def test_bad_numbers_and_duplicate_id(self):
        data = copy.deepcopy(FIXTURE)
        data["items"][0]["qty"] = 0
        data["items"][1]["unit_price"] = "1000"
        data["items"][2]["id"] = "a"
        errors = estimate.validate(data)
        self.assertTrue(any("'qty'" in e for e in errors), errors)
        self.assertTrue(any("'unit_price'" in e for e in errors), errors)
        self.assertTrue(any("duplicate" in e for e in errors), errors)


class CliTest(unittest.TestCase):
    def run_cli(self, data, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "estimate.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = estimate.main([str(path), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_share_below_threshold_fails(self):
        code, _, err = self.run_cli(FIXTURE, "--min-share", "0.8")
        self.assertEqual(code, 1)
        self.assertIn("sourced share", err)

    def test_share_at_threshold_passes(self):
        code, out, _ = self.run_cli(FIXTURE, "--min-share", "0.75")
        self.assertEqual(code, 0)
        self.assertIn("Итого: 20 000 ₽", out)

    def test_invalid_data_fails(self):
        data = copy.deepcopy(FIXTURE)
        del data["items"][2]["estimate"]
        code, _, err = self.run_cli(data)
        self.assertEqual(code, 1)
        self.assertIn("ERROR", err)


class RealEstimateTest(unittest.TestCase):
    """Acceptance of #25 and #166 on the committed content/estimate.json."""

    @classmethod
    def setUpClass(cls):
        cls.data = estimate.load(DATA)
        cls.ids = {i["id"] for i in cls.data["items"]}
        cls.by_id = {i["id"]: i for i in cls.data["items"]}
        cls.assumptions = {a["id"]: a for a in cls.data["assumptions"]}

    def test_valid(self):
        self.assertEqual(estimate.validate(self.data), [])

    def test_sourced_share_at_least_70_percent(self):
        s = estimate.summarize(self.data)
        self.assertGreaterEqual(s["share"], 0.70)

    def test_covers_required_articles(self):
        # Articles from task #25 and the safety systems of concept/05-safety.md.
        # New D-001 (#166): no "Кабины" article, miniatures 1:5 added.
        articles = {i["article"] for i in self.data["items"]}
        required = {
            "Отделка", "Перегородки", "Миниатюры", "АУП и СПС", "Вентиляция",
            "Свет", "Экраны", "Мебель", "Лазерный класс", "Продукт",
        }
        self.assertTrue(required <= articles, required - articles)
        self.assertNotIn("Кабины", articles)
        for needed in ("eiw_workshop", "laser_layer_workshop", "glass_live_zone",
                       "sps_hall", "general_ventilation", "mini_models",
                       "mini_hoods", "video_stands"):
            self.assertIn(needed, self.ids)

    def test_no_exhaust_in_total(self):
        # D-001: no beam in the hall, so no local exhaust (concept/05-safety.md,
        # 5). The LFILTER price stays only in the assumption exhaust_if_beam,
        # out of the total, for the case a new decision brings the beam back.
        self.assertEqual(
            [i for i in self.ids if "exhaust" in i], [])
        self.assertIn("exhaust_if_beam", self.assumptions)

    def test_d001_no_live_beam_lines(self):
        # Trap (#166): new D-001 — no beam in the hall. Lines that exist only
        # for a live beam are gone: cleaning cabin, its camera, goggles, laser
        # layer of the demo-zone windows. The laser layer of the glass to the
        # workshop stays: the beam works in the workshop (05-safety, 3.5).
        for gone in ("cabins", "cabin_cameras", "goggles",
                     "laser_layer_live_zone", "local_exhaust_smart"):
            self.assertNotIn(gone, self.ids)
        self.assertIn("laser_layer_workshop", self.ids)
        for key in ("curtains_alternative", "cleaning_cabin",
                    "cleaning_exhaust", "engraver_exhaust"):
            self.assertNotIn(key, self.assumptions)

    def test_demo_zone_behind_plain_glass(self):
        # Human decision 25.10 (#497) answers question 17: no dangerous process in
        # the demo zone, it stays in the hall class behind plain glass. The EIW 45
        # walls and the water АУП of the zone are gone; the workshop glass stays.
        self.assertIn("glass_live_zone", self.ids)
        for gone in ("eiw_live_zone", "aup_live_zone", "aupt_project"):
            self.assertNotIn(gone, self.ids)
        for kept in ("eiw_workshop", "laser_layer_workshop", "sps_hall"):
            self.assertIn(kept, self.ids)
        text = self.assumptions["live_zone"]["text"]
        self.assertIn("вопрос 17", text)
        self.assertIn("решение человека 25.10", text)
        self.assertNotIn("лазерн", text.lower())

    def test_no_old_d001_wording(self):
        # #233: estimate.json quoted the old D-001 ("гравировка вживую",
        # "без вытяжки"). The new D-001 has no beam at all.
        raw = DATA.read_text(encoding="utf-8")
        for stale in ("вживую", "без вытяжки", "кабин", "лазерной чистк"):
            self.assertNotIn(stale, raw.lower(), stale)

    def test_miniatures_match_plan(self):
        # One model and one plinth with a glass hood per miniature object of
        # the zoned plans (scripts/plan_zones.py, both variants).
        for plan in PLANS:
            doc = json.loads(plan.read_text(encoding="utf-8"))
            minis = [o for o in doc["objects"] if o["label"].startswith("Миниатюра")]
            self.assertEqual(self.by_id["mini_models"]["qty"], len(minis), plan.name)
            self.assertEqual(self.by_id["mini_hoods"]["qty"], len(minis), plan.name)

    def test_video_stand_per_zone_with_miniature(self):
        # concept/04-zones.md: each zone with a miniature of a large machine
        # has one 1:1 video stand.
        for plan in PLANS:
            doc = json.loads(plan.read_text(encoding="utf-8"))
            zones = {o["zoneId"] for o in doc["objects"] if o["label"].startswith("Миниатюра")}
            self.assertEqual(self.by_id["video_stands"]["qty"], len(zones), plan.name)

    def test_manufacturer_items_out_of_total(self):
        # Human decision 25.10 (#497): miniatures and the «Лазерный класс» kit are
        # ЛАССАРД products, like the exhibits; the line stays for the plan, price 0.
        for own in ("mini_models", "laser_class_kit"):
            self.assertEqual(self.by_id[own]["unit_price"], 0, own)
            self.assertIn("в сумму не входит", self.by_id[own]["name"], own)

    def test_known_research_gaps_are_estimates(self):
        # Trap: research has no per-m² price for laser windows and no price of
        # scale models or museum hoods; the АУПТ project is a search snippet
        # without a checked URL. These lines must not pretend to have a source.
        for gap in ("laser_layer_workshop", "mini_models",
                    "mini_hoods"):
            self.assertIs(self.by_id[gap].get("estimate"), True, gap)
            self.assertNotIn("source", self.by_id[gap])
        for gap in ("mini_models", "mini_hoods"):
            self.assertIn("Оценка команды", self.by_id[gap]["basis"], gap)

    def test_lfilter_prices_from_product_pages(self):
        # Trap: costs_timelines.md says the LFILTER price is not on the page.
        # The product page shows it (schema.org price, checked 24.10.2026).
        # The exhaust is out of the total, so the price lives in the assumption.
        exhaust = self.assumptions["exhaust_if_beam"]
        self.assertIn(
            "https://lassard.ru/products/equipment/ventilation/lfilter-smart",
            exhaust["source"])
        self.assertIn("700 000 ₽", exhaust["text"])


class RationaleTextTest(unittest.TestCase):
    """Gates G2/T1 and G3 on concept/06-rationale.md."""

    @classmethod
    def setUpClass(cls):
        text = RATIONALE.read_text(encoding="utf-8")
        # Quoted case text is allowed to keep the original spelling.
        cls.text = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith(">")
        )

    def test_brand_name(self):
        self.assertNotRegex(self.text, r"Лассард|Lassard|ЛАССАРДа|«ЛАССАРД»")

    def test_no_full_or_superlative_claims(self):
        self.assertNotRegex(self.text, r"100\s*%")
        self.assertNotRegex(
            self.text, r"(?i)\bсам(ый|ая|ое|ые|ого|ой|ым)\b|\bлучш|№\s*1|лидер рынка"
        )

    def test_total_matches_script(self):
        s = estimate.summarize(estimate.load(DATA))
        total = f"{round(s['total']):,}".replace(",", " ")
        self.assertIn(total, self.text)
        share = f"{s['share'] * 100:.1f}".replace(".", ",")
        self.assertIn(share, self.text)

    def test_payback_ratio_matches_total(self):
        # §4.4: "≈ N продажи SMART BASE" must follow the total (#166).
        data = estimate.load(DATA)
        total = estimate.summarize(data)["total"]
        price = next(e["price"] for e in data["exhibits"]["items"]
                     if e["name"] == "SMART BASE")
        ratio = f"{total / price:.1f}".replace(".", ",")
        total_rub = f"{round(total):,}".replace(",", " ")
        self.assertIn(f"≈ {ratio} продажи SMART BASE", self.text)
        self.assertIn(total_rub + " / 11 633 305,78", self.text)
        # Review of PR #267: pitch/QA.md (answers 3 and 17) quotes the same numbers.
        if not QA.exists():
            return
        qa = QA.read_text(encoding="utf-8")
        ratios = re.findall(r"(\d+,\d) продажи SMART BASE", qa)
        self.assertTrue(ratios, "pitch/QA.md: no ratio to SMART BASE")
        self.assertEqual(set(ratios), {ratio})
        self.assertIn(total_rub + " ₽ / 11 633 305,78", qa)
        self.assertIn("точно " + total_rub + " ₽", qa)
        self.assertNotIn("до пересчёта #166", qa)

    def test_no_live_beam_lines_in_rationale(self):
        # New D-001 (#166): no cabin, no live engraving or cleaning in the hall.
        for stale in ("кабин", "вживую", "без вытяжки", "лазерный слой окна демо"):
            self.assertNotIn(stale, self.text.lower(), stale)

    def test_embedded_output_matches_script(self):
        # The section quotes the script output; a stale copy is a G1 failure.
        rendered = estimate.render(estimate.summarize(estimate.load(DATA)))
        self.assertIn("```\n" + rendered + "\n```", self.text)


if __name__ == "__main__":
    unittest.main()


class ScenarioTests(unittest.TestCase):
    """Three scenarios over the base estimate (#399): order min < base < max, safety and norms never cut."""

    def setUp(self):
        self.data = estimate.load(estimate.DEFAULT_PATH)
        self.rows = dict(estimate.scenario_rows(self.data))

    def test_order(self):
        self.assertLess(self.rows["min"]["total"], self.rows["base"]["total"])
        self.assertLess(self.rows["base"]["total"], self.rows["max"]["total"])

    def test_safety_and_norms_never_cut(self):
        for art in estimate.NEVER_CUT:
            base = self.rows["base"]["articles"][art]["total"]
            self.assertEqual(self.rows["min"]["articles"][art]["total"], base, art)

    def test_scenario_ids_exist(self):
        ids = {i["id"] for i in self.data["items"]}
        for sc in estimate.SCENARIOS.values():
            self.assertTrue(set(sc["items"]) <= ids)
