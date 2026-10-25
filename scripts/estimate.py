#!/usr/bin/env python3
"""Sum the showroom estimate from content/estimate.json.

Prints the per-article table, the total, the share of the total that has a
source, and the share that has a source read from the page (not a search
snippet). Exits 1 if the data is invalid or the sourced share is below
--min-share. Standard library only.
"""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "content" / "estimate.json"
DEFAULT_MIN_SHARE = 0.70
QUALITIES = ("page", "snippet")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(data):
    """Return a list of error strings. Empty list means the data is valid."""
    errors = []
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return ["items: list is missing or empty"]
    seen = set()
    for idx, item in enumerate(items):
        tag = item.get("id") or f"items[{idx}]"
        if tag in seen:
            errors.append(f"{tag}: duplicate id")
        seen.add(tag)
        for key in ("article", "name", "unit", "qty_basis"):
            if not str(item.get(key, "")).strip():
                errors.append(f"{tag}: '{key}' is empty")
        qty = item.get("qty")
        price = item.get("unit_price")
        if not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0:
            errors.append(f"{tag}: 'qty' must be a positive number")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
            errors.append(f"{tag}: 'unit_price' must be a non-negative number")
        has_source = "source" in item
        is_estimate = item.get("estimate") is True
        if has_source == is_estimate:
            errors.append(f"{tag}: needs exactly one of 'source' or 'estimate: true'")
            continue
        if has_source:
            src = item["source"] or {}
            # A sourced line must point to the page or snippet it came from.
            # Without a URL the price is an estimate, not a source.
            if not str(src.get("url") or "").strip():
                errors.append(f"{tag}: source needs a non-empty 'url'")
            if not str(src.get("date") or "").strip():
                errors.append(f"{tag}: source needs 'date'")
            if src.get("quality") not in QUALITIES:
                errors.append(f"{tag}: source 'quality' must be one of {QUALITIES}")
        else:
            if not str(item.get("basis", "")).strip():
                errors.append(f"{tag}: estimate needs a non-empty 'basis'")
    return errors


def line_total(item):
    return item["qty"] * item["unit_price"]


def summarize(data):
    """Return totals: total, sourced, sourced_page, shares and per-article rows."""
    total = sourced = sourced_page = 0.0
    articles = {}
    for item in data["items"]:
        amount = line_total(item)
        total += amount
        row = articles.setdefault(item["article"], {"total": 0.0, "sourced": 0.0})
        row["total"] += amount
        if "source" in item:
            sourced += amount
            row["sourced"] += amount
            if item["source"].get("quality") == "page":
                sourced_page += amount
    exhibits = sum(e["price"] for e in data.get("exhibits", {}).get("items", []))
    return {
        "total": total,
        "sourced": sourced,
        "sourced_page": sourced_page,
        "estimated": total - sourced,
        "share": sourced / total if total else 0.0,
        "share_page": sourced_page / total if total else 0.0,
        "articles": articles,
        "exhibits": exhibits,
    }


# Scenarios over the base estimate (content/estimate.json). Only quantities and prices change; every price comes
# from the same research pages (research/notes/costs_timelines.md). Safety and norms are never cut: АУП и СПС,
# Вентиляция, Перегородки (EIW, лазерный слой).
NEVER_CUT = ("АУП и СПС", "Вентиляция", "Перегородки")
SCENARIOS = {
    "min": {
        "title": "Минимум: экспозицию режем количеством, безопасность и нормы не трогаем",
        "items": {
            "video_stands": {"qty": 2, "why": "LED 1:1 только у резки и роботов, у остальных зон — экраны пролёта"},
            "kiosks": {"qty": 1, "why": "один киоск у входа, у зон — QR на телефон"},
            "touch_table": {"qty": 0, "why": "подбор станка — на планшете менеджера"},
            "mini_models": {"qty": 3, "why": "миниатюры 1:5 только SMART BASE, LS-FL9000, LASERHARD"},
            "mini_hoods": {"qty": 3, "why": "колпаки под 3 миниатюры"},
            "laser_class_seats": {"qty": 8, "why": "группа 8 человек"},
        },
    },
    "max": {
        "title": "Максимум: верхние цены тех же источников (флагман)",
        "items": {
            "design_project": {"unit_price": 3500, "why": "dizajn-interera-spb.ru, от 3 500 ₽/м²",
                               "url": "https://dizajn-interera-spb.ru/services/dizajn_interera_shouruma"},
            "finishing": {"unit_price": 12500, "why": "kronotech.ru, капитальный и дизайнерский ремонт от 12 500 ₽/м²",
                          "url": "https://kronotech.ru/otdelka-pomeshcheniy/kapitalnyy-remont-ofisa"},
            "video_3d": {"qty": 3, "why": "по минуте на площадку: Технополис, Варшавское ш., Обнинск"},
            "kiosks": {"qty": 4, "why": "киоск на каждой остановке акта"},
        },
    },
}


def apply_scenario(data, name):
    """Copy of the data with the scenario's quantities/prices; a line with qty 0 is dropped."""
    over = SCENARIOS[name]["items"]
    items = []
    for item in data["items"]:
        o = over.get(item["id"])
        if o:
            if item["article"] in NEVER_CUT and o.get("qty", item["qty"]) < item["qty"]:
                raise ValueError(f"{item['id']}: safety/norm lines are never cut")
            item = dict(item)
            if "qty" in o:
                item["qty"] = o["qty"]
            if "unit_price" in o:
                item["unit_price"] = o["unit_price"]
                if "url" in o:
                    item["source"] = dict(item.get("source") or {}, url=o["url"])
        if item["qty"] > 0:
            items.append(item)
    return dict(data, items=items)


def scenario_rows(data):
    """[(name, summary)] for min, base, max."""
    return [("min", summarize(apply_scenario(data, "min"))), ("base", summarize(data)),
            ("max", summarize(apply_scenario(data, "max")))]


def render_scenarios(data):
    names = {"min": "Минимум", "base": "База", "max": "Максимум"}
    rows = scenario_rows(data)
    lines = ["", "Сценарии:"]
    for name, sm in rows:
        lines.append(f"{names[name]:<10}{rub(sm['total']):>16}   с источником {pct(sm['share'])}")
    return "\n".join(lines)


def rub(value):
    return f"{round(value):,}".replace(",", " ") + " ₽"


def pct(value):
    # Gate G3 forbids a "100 %" claim in texts; a full share is printed in words.
    if value >= 1:
        return "вся сумма"
    return f"{value * 100:.1f} %".replace(".", ",")


def render(summary):
    lines = []
    width = max(len(a) for a in summary["articles"]) + 2
    # Per-article shares are not printed: a full share would read as a
    # forbidden "100 %" claim (gate G3) in the PR body.
    lines.append(f"{'Статья':<{width}}{'Сумма':>16}{'С источником':>16}{'Оценка':>16}")
    for name, row in summary["articles"].items():
        estimated = row["total"] - row["sourced"]
        lines.append(
            f"{name:<{width}}{rub(row['total']):>16}{rub(row['sourced']):>16}{rub(estimated):>16}"
        )
    lines.append("-" * (width + 48))
    lines.append(f"Итого: {rub(summary['total'])}")
    lines.append(f"С источником: {rub(summary['sourced'])} — {pct(summary['share'])}")
    lines.append(
        f"Из них страница прочитана: {rub(summary['sourced_page'])} — {pct(summary['share_page'])}"
    )
    lines.append(
        f"Оценка: {rub(summary['estimated'])} — {pct(1 - summary['share'])}"
    )
    if summary["exhibits"]:
        lines.append(
            f"Экспонаты ЛАССАРД по прайсу (справочно, не в сумме): {rub(summary['exhibits'])}"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sum the showroom estimate.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH))
    parser.add_argument("--min-share", type=float, default=DEFAULT_MIN_SHARE)
    args = parser.parse_args(argv)

    data = load(args.path)
    errors = validate(data)
    if errors:
        for err in errors:
            print(f"ERROR {err}", file=sys.stderr)
        return 1
    summary = summarize(data)
    print(render(summary))
    print(render_scenarios(data))
    if summary["share"] < args.min_share:
        print(
            f"ERROR sourced share {pct(summary['share'])} < {pct(args.min_share)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
