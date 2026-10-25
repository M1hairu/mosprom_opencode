"""Tests for scripts/check-wording.py: per rule, one caught line and one clean line."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_wording", Path(__file__).resolve().parent.parent / "scripts" / "check-wording.py")
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)

CASES = [
    # (rule fragment, caught line, clean line)
    ("write ЛАССАРД", "Компания Лассард открыла зал.", "Компания ЛАССАРД открыла зал."),
    ("write ЛАССАРД", "Продукт Lassard Showroom.", "Продукт LASSARD Showroom."),
    ("write ЛАССАРД", "Сайт lassard для всех.", "Сайт https://lassard.ru/about."),
    ("write ЛАССАРД", "Файл `Лассард` в тексте.", "Файл `lassard_facts.md` в тексте."),
    ("lowercase ending", "Станки ЛАССАРДа стоят в зале.", "Станки ЛАССАРД стоят в зале."),
    ("lowercase ending", "Станки ЛАССАРД-а и ЛАССАРД’а.", "Станки ЛАССАРД и LASSARD."),
    ("name in quotes", "Бренд «ЛАССАРД» растёт.", "Бренд ЛАССАРД растёт, см. «Итоги 2024»."),
    ("100 %", "Локализация 100 % по кейсу.", "Локализация 80 % по кейсу."),
    ("самый", "Это самый быстрый станок.", "Проверка самого шаблона."),
    ("самый", "Этот станок самый-самый.", "Маршрут показан на плане."),
    ("самый", "Работа самого быстрого станка.", "Это то же самое."),
    ("самый", "Самый мощный станок.", "От самой удалённой точки до выхода."),
    ("самый", "Самый мощный станок.", "От самого удаленного места."),
    ("самый", "Ставим на самом мощном источнике.", "На самом деле всё иначе."),
    ("лучший", "Лучший лазер в классе.", "Станок работает лучше после настройки."),
    ("лучший", "Выбрали `лучший_станок`.", "Открыть `content/facts.json`."),
    ("лучший", "Написано `лучший.станок`.", "Открыть `facts.json`."),
    ("лучший", "Это лучшую цену даёт.", "Выбор за клиентом."),
    ("лучший", "О лучшей модели.", "О новой модели."),
    ("лучший", "Лучшем из залов.", "О новом зале."),
    ("лучший", "Лучшими станками.", "Новыми станками."),
    ("лучший", "Наилучший результат.", "Хороший результат."),
    ("№ 1", "Компания № 1 в России.", "Зона №10 на плане."),
    ("лидер рынка", "ЛАССАРД, лидер рынка лазеров.", "Лидер проекта назначен."),
    ("30 видов станков", "Выпускает 30 видов станков.", "Выпускает 30+ видов изделий."),
    ("write ЛАССАРД", "Сервис lassard для всех.", "Каталог `lassard` на сервере."),
    ("write ЛАССАРД", "Сервис lassard для всех.", "Журнал: journalctl -u lassard-update."),
    ("100 %", "Локализация 100 % по кейсу.", "В тексте нет «100 %»."),
    ("лучший", "Лучший лазер в классе.", 'Слов "лучший" и «самый» нет.'),
    ("30 видов станков", "Выпускает 30 видов станков.", "Слайд 3 пишет «более 30 видов станков»."),
]


class WordingTest(unittest.TestCase):
    def test_caught_and_clean(self):
        for rule, bad, good in CASES:
            with self.subTest(rule=rule, line=bad):
                self.assertTrue(any(rule in r for r in cw.check_line(bad)), cw.check_line(bad))
            with self.subTest(rule=rule, line=good):
                self.assertEqual(cw.check_line(good), [])

    def test_marker_exempts_case_quote(self):
        self.assertEqual(cw.check_line("Кейс: «лучший шоурум» " + cw.MARKER), [])

    def _hits(self, name: str, body: str) -> int:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "content").mkdir()
            (Path(d) / "content" / name).write_text(body, encoding="utf-8")
            return sum(1 for f in cw.files(Path(d)) for _, t in cw.text_lines(f) if cw.check_line(t))

    def test_json_quotes_are_not_name_in_quotes(self):
        self.assertEqual(self._hits("a.json", json.dumps({"brand": "ЛАССАРД"}, ensure_ascii=False)), 0)
        self.assertEqual(self._hits("b.json", json.dumps({"t": "Лучший станок"}, ensure_ascii=False)), 1)

    def test_quoted_slogan_is_a_claim(self):
        for line in ("Слоган: «Лучший шоурум Москвы».", "«Самый точный лазер в России»",
                     "«100 % локализация»"):
            with self.subTest(line=line):
                self.assertNotEqual(cw.check_line(line), [])

    def test_json_case_quote_is_skipped_in_facts_only(self):
        body = json.dumps({"text": "более 30 видов изделий", "case": {"value": "более 30 видов станков"}},
                          ensure_ascii=False)
        self.assertEqual(self._hits("facts.json", body), 0)
        self.assertEqual(self._hits("zones.json", body), 1)
        body = {"text": "более 30 видов станков"}
        self.assertEqual(self._hits("facts.json", json.dumps(body, ensure_ascii=False)), 1)

    def test_html_marker_exempts_line(self):
        self.assertEqual(self._hits("a.html", "<p>Лучший станок <!-- case-quote --></p>"), 0)
        self.assertEqual(self._hits("b.html", "<p>Лучший станок</p>"), 1)

    def test_html_style_and_script_are_skipped(self):
        page = "<style>\nbody{height:100%}\n</style>\n<script>let a='Лассард'</script>\n<p>Бренд ЛАССАРД</p>"
        self.assertEqual(self._hits("a.html", page), 0)
        self.assertEqual(self._hits("b.html", "<style>p{}</style>\n<p>Локализация 100 %</p>"), 1)

    def test_html_attribute_is_not_name_in_quotes(self):
        self.assertEqual(self._hits("a.html", '<img alt="LASSARD">'), 0)
        self.assertEqual(self._hits("b.html", "<p>Бренд «LASSARD»</p>"), 1)


if __name__ == "__main__":
    unittest.main()
