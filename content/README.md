# content/ — данные продукта, записки и слайдов

Один формат для всех потребителей. Схемы — `content/schemas/*.schema.json`.
Проверка — `make lint` (`scripts/check-content.py`, затем тест валидатора).

| Файл | Что внутри |
|---|---|
| `facts.json` | числа: `value`, `unit`, `text` + источник `case` (слайд), `public` (url, date, value) или `norm`; `check: true` — метка «уточняется» |
| `catalog.json` | экспонаты: `category`, `size_mm` + `size_source` или `estimate: true` + `estimate_basis`; `size_alt`, `laser_class`, `beam` (null — неизвестно), `work_area_mm`, `power_w`, `price_from`, `in_current_showroom`, `plan_type` (тип объекта плана), `note` |
| `zones.json` | 13 зон: экспонаты, способ показа, безопасность, `status: normal\|maintenance` + `maintenance.replacement`, `carries` (сообщения слайда 10), тексты |
| `routes.json` | 6 ролей слайда 7 → `duration_max_min` и шаги (зона, минуты, сообщение); пропуск зоны — `skipped` с причиной |
| `plan*.json` | планы зала в формате pochta `PlanDocument` v1 (`plan-219*.json`, #46): `schemaVersion: 1`, метры, X вправо, Y вверх. Другого формата плана нет |

`id` зон: entrance, crystals, quantrons, diodes, laser_sources, robots, engraving, cutting,
handheld, optomechanics, edu_class («Лазерный класс»), meeting, test_lab.
Роли: prospect, customer, education, government, students, media.
Сообщения слайда 10: scale, history, localization, full_cycle, russian_production.

## Правила проверки

- Факт без источника → ошибка (G1). В `text` есть число `value`.
- Число T8 (80, 0.8, 400+, 14 400 — по `value` или по `text`) без `public` → ошибка (G14).
- Габарит неполный или без `size_source` → нужно `estimate: true` + `estimate_basis` (G4).
- G5 — только `/api/validate` (D-014 слой здания, safety.py). Здесь G5 не проверяем:
  поля `laser_class`, `beam`, `plan_type`, `safety` — данные для него.
- Роли `students`, `media`, `government` не входят в `test_lab`, в зону с `interlock`
  и в зону `restricted`.
- В текстах зон и маршрутов нет цифр. Число — `{{fact:<id>}}`, имя экспоната —
  `{{item:<id>}}` (G1).
- Каждое сообщение слайда 10 несёт хотя бы одна зона. Зона `maintenance` — с заменой (S2).
- Сумма минут ≤ `duration_max_min`; органы власти ≤ 40 мин (S4.1).
- Ссылки между файлами существуют. `id` и роли не повторяются.
- План: `wallId`, `typeId`, `zoneId`, `parentId`, `layerId` ссылаются на объекты плана.
  `id` зоны плана — из списка зон `zones.json`;
  у подзоны (кабина, отсек) — `parentId` такой зоны. `plan_type` есть в плане.
- Ключ схемы вне подмножества валидатора → ошибка.

Полная схема PlanDocument — #57. Здесь проверяем только поля, нужные для ссылок.
