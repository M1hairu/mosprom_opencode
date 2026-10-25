#!/usr/bin/env python3
"""Zoned plan of hall 219 (task #23): build PlanDocument files and check the geometry.

    python3 scripts/plan_zones.py --write   # content/plan-219-zoned.json, ...-mirror-zoned.json
    python3 scripts/plan_zones.py --check   # print the checks; exit 1 if a check fails

Input: content/plan-219.json and content/plan-219-mirror.json (pochta PlanDocument v1).
In both files the workshop wall lies at x = 0 (original: w_west, mirror: w_east), so
the zones next to the workshop have the same x in both variants. The entrances differ.

Checks (concept/01-layout.md, section «Проверки»):
  zone areas and their sum against 626 m2 (slide 6); zone overlaps; exhibits against
  columns, walls, door approaches and their zone; passages between exhibits, columns
  and walls >= 1.2 m in the hall (evacuation paths) and >= 1.0 m inside the meeting
  room and the demo zone; exit widths >= 1.2 m; exit spacing against half of the hall
  diagonal; the longest path to an exit on a 0.2 m grid (8 neighbours, so the length
  is not shorter than the real one). Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import heapq
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = {"original": ROOT / "content" / "plan-219.json", "mirror": ROOT / "content" / "plan-219-mirror.json"}
OUT = {
    "original": ROOT / "content" / "plan-219-zoned.json",
    "mirror": ROOT / "content" / "plan-219-mirror-zoned.json",
}

CASE_AREA_M2 = 626.0  # task/case.md, slide 6
# concept/05-safety.md 4.2 (SP 1.13130.2020, 4.3.3): evacuation path >= 1.2 m if more than
# 50 people evacuate, else >= 1.0 m. The hall holds 90 people (05-safety 4.2), so every
# passage in the hall is 1.2 m. The meeting room (8 seats) and the demo zone (staff only)
# are separate rooms with fewer than 50 people: 1.0 m inside them.
MIN_EVAC_PATH_M = 1.2
MIN_PASSAGE_M = 1.0
SMALL_ROOMS = {"meeting", "test_lab"}
AGAINST_WALL_M = 0.1  # an exhibit this close to a wall stands against it: no passage behind
WALL_MOUNTED = {"ot_wall_screen"}  # part of its wall: no wall-gap check
MIN_EXIT_M = 1.2  # 05-safety 4.2: SP 1.13130.2020, 4.2.19 / 7.1.6
MAX_PATH_C0_M = 30.0  # 05-safety 4.2: table 5, volume up to 5000 m3, class C0
MAX_PATH_C1_M = 20.0  # same table, class C1
APPROACH_M = 1.2  # free floor in front of an exit, team rule
GRID_M = 0.2
CLEARANCE_M = 0.3  # half of a person: a path cell keeps 0.3 m from obstacles

# Contract ids (content/schemas/zones.schema.json, PR #43).
ZONE_IDS = [
    "entrance", "crystals", "quantrons", "diodes", "laser_sources", "robots", "engraving",
    "cutting", "handheld", "optomechanics", "edu_class", "meeting", "test_lab",
]
# Visitor route of the prospect (slide 4): entrance -> path of the machine -> glass -> demo -> meeting.
ROUTE = [
    "entrance", "crystals", "quantrons", "diodes", "laser_sources", "robots", "engraving",
    "handheld", "cutting", "test_lab", "meeting",
]
SIDE_STOPS = ["optomechanics", "edu_class"]  # stops for partners and groups (teaser #48, block 2)

ZONE_META = {
    # id: (name, zone type, slide 3 row or None, fire class)
    "entrance": ("Вход: хронология, масштаб, география", "zt_entrance", None, "Ф2.2"),
    "crystals": ("Выращивание кристаллов", "zt_expo", 1, "Ф2.2"),
    "quantrons": ("Квантроны", "zt_expo", 2, "Ф2.2"),
    "diodes": ("Диоды", "zt_expo", 3, "Ф2.2"),
    "laser_sources": ("Лазерные источники", "zt_expo", 4, "Ф2.2"),
    "robots": ("Роботизированные ячейки и роботы", "zt_expo", 5, "Ф2.2"),
    "engraving": ("Гравировка и маркировка", "zt_expo", 6, "Ф2.2"),
    "cutting": ("Лазерная резка: SMART и стекло в цех", "zt_view", 7, "Ф2.2"),
    "handheld": ("Ручные лазерные аппараты", "zt_expo", 8, "Ф2.2"),
    "optomechanics": ("Оптомеханика", "zt_expo", 9, "Ф2.2"),
    "edu_class": ("Проект «Лазерный класс»", "zt_edu", 10, "Ф2.2"),
    "meeting": ("Переговорная", "zt_meeting", None, "Ф2.2"),
    "test_lab": ("Демо-зона", "zt_demo", None, "[СПРОСИТЬ]; в 05-safety принят Ф5.1"),
}

ZONE_TYPES = [
    ("zt_entrance", "Входная зона (Ф2.2)", "#F2C94C"),
    ("zt_expo", "Экспозиция (Ф2.2)", "#9AD0F5"),
    ("zt_view", "Точка у стекла в цех (Ф2.2)", "#6FCF97"),
    ("zt_edu", "Образовательная зона (Ф2.2)", "#BB9AF7"),
    ("zt_meeting", "Переговорная (Ф2.2)", "#F2994A"),
    ("zt_demo", "Демо-зона, класс [СПРОСИТЬ]", "#EB5757"),
]

SRC = "research/notes/lassard_facts.md, раздел 2"
# type id: label, category, size [x, y], height, provenance
OBJECT_TYPES = {
    "ot_vgf": ("Миниатюра установки VGF «Листопад» в масштабе 1:5, под стеклом", "Кристаллы", [0.5, 0.5], 1.5,
               f"Миниатюра 1:5 (D-001). Габариты установки не опубликованы ({SRC}); 1,5 × 1,5 × 2,5 м — "
               "оценка, модель 300 × 300 × 500 мм. Подиум со стеклом: модель + 0,1 м с каждой стороны — оценка."),
    "ot_showcase": ("Витрина с образцами", "Экспозиция", [1.2, 0.6], 1.2,
                    "Размер витрины — оценка команды."),
    "ot_wall_screen": ("Экран на стене", "Экспозиция", [2.0, 0.2], 2.5,
                       "Размер экрана — оценка команды."),
    "ot_panel": ("Стенд-панель", "Экспозиция", [4.0, 0.4], 7.0,
                 "Размер стенда — оценка команды."),
    "ot_ls_fl9000": ("Миниатюра LS-FL9000 в масштабе 1:5, под стеклом", "Лазерные источники", [0.36, 0.42], 1.24,
                     f"Миниатюра 1:5 (D-001): модель 160 × 220 × 240 мм от 800 × 1100 × 1200 мм, официально "
                     f"({SRC}). Подиум со стеклом: модель + 0,1 м с каждой стороны — оценка."),
    "ot_ls_fl20000": ("Миниатюра LS-FL20000 в масштабе 1:5, под стеклом", "Лазерные источники", [0.5, 0.44], 1.32,
                      f"Миниатюра 1:5 (D-001): модель 300 × 240 × 324 мм от 1500 × 1200 × 1620 мм, официально "
                      f"({SRC}). Подиум со стеклом: модель + 0,1 м с каждой стороны — оценка."),
    "ot_ndyag": ("Миниатюра лазера Nd:YAG в масштабе 1:5, под стеклом", "Лазерные источники", [0.39, 0.26], 1.03,
                 f"Миниатюра 1:5 (D-001): модель 187 × 59 × 30 мм от лазера 933 × 296 × 149 мм, официально "
                 f"({SRC}). Подиум со стеклом: модель + 0,1 м с каждой стороны — оценка."),
    "ot_robot_cell": ("Миниатюра ячейки робота с гравёром в масштабе 1:5, под стеклом", "Роботы", [0.8, 0.8], 1.44,
                      f"Миниатюра 1:5 (D-001). Габариты ячейки не опубликованы ({SRC}); 3 × 3 × 2,2 м с "
                      "ограждением — оценка, модель 600 × 600 × 440 мм. Подиум со стеклом: модель + 0,1 м "
                      "с каждой стороны — оценка."),
    "ot_graver_table": ("GRAVER COMPACT на столе, без питания", "Гравировка", [1.2, 0.8], 1.0,
                        f"Основание 524–527 мм, высота 825–1003 мм ({SRC}); стол 1,2 × 0,8 м — оценка."),
    "ot_graver_portal": ("GRAVER PORTAL, без питания", "Гравировка", [1.2, 1.0], 1.8,
                         f"Габариты не опубликованы, стол 950 × 750 мм ({SRC}). 1,2 × 1,0 м — оценка."),
    "ot_graver_3d": ("Закрытый гравёр GRAVER 3D, без питания", "Демо-зона", [0.8, 0.8], 1.6,
                     f"Гравёр без питания, луча нет (D-001). У GRAVER 3D габаритов нет ({SRC}). 0,8 × 0,8 м — оценка."),
    "ot_clean_zone": ("Ограждённый участок демо-зоны, без луча", "Демо-зона", [2.5, 2.5], 2.5,
                       "Луча и лазерной чистки нет (D-001). Что стоит за ограждением — [СПРОСИТЬ] эксперта ЛАССАРД. 2,5 × 2,5 м — оценка."),
    "ot_smart_base": ("Миниатюра SMART BASE в масштабе 1:5, под стеклом", "Резка", [0.55, 0.55], 1.44,
                      f"Миниатюра 1:5 (D-001): модель 350 × 350 × 440 мм от 1750 × 1750 × 2200 мм, официально "
                      f"({SRC}); не поле 800 × 800 мм (TRAP-3). Подиум со стеклом: модель + 0,1 м с каждой "
                      "стороны — оценка. Резки в зале нет."),
    "ot_multi_hero": ("MULTI HERO, без питания", "Ручные аппараты", [1.17, 0.706], 1.12,
                      f"1170 × 706 × 1119 мм по чертежу каталога ({SRC})."),
    "ot_cleaner_prom": ("CLEANER PROM, без питания", "Ручные аппараты", [1.17, 0.706], 1.119,
                        f"1170 × 706 × 1119 мм, официально ({SRC})."),
    "ot_welder_mini": ("WELDER MINI на подставке, без питания", "Ручные аппараты", [0.8, 0.6], 1.0,
                       f"640 × 400 × 660 мм, официально ({SRC}); подставка 0,8 × 0,6 м — оценка."),
    "ot_optical_table": ("Оптический стол", "Оптомеханика", [2.4, 1.2], 0.9,
                         "Размер стола — оценка команды, на opto.lassard.ru не сверен."),
    "ot_kit_stand": ("Стойка: набор МИРЭА или ламинарная станция", "Оптомеханика", [1.2, 0.8], 1.9,
                     "МИРЭА: размер — оценка команды. ex_laminar: 66LB-ALM 1660 × 1140 мм, минимальный "
                     "вариант (research/notes/lassard_facts.md, раздел 3); высота не опубликована, 1,9 м — оценка."),
    "ot_sim_desk": ("Парта оператора с симулятором", "Лазерный класс", [1.4, 0.8], 0.75,
                    "Парта есть в составе «Лазерного класса» (lassard_facts.md, раздел 4); размер — оценка."),
    "ot_meeting_table": ("Стол переговоров на 8 мест", "Переговоры", [2.4, 1.2], 0.75,
                         "Размер — оценка команды."),
}

# Zone rectangles [x0, y0, x1, y1], metres. The workshop is at x = 0 in both files.
TOP_BAND = {
    "crystals": [29.0, 11.0, 36.0, 17.85],
    "quantrons": [23.0, 11.0, 29.0, 17.85],
    "diodes": [17.5, 11.0, 23.0, 17.85],
    "laser_sources": [12.5, 11.0, 17.5, 17.85],
    "robots": [6.5, 11.0, 12.5, 17.85],
    "engraving": [0.0, 11.0, 6.5, 17.85],
}
TOP_OBJECTS = [
    # id, type, zone, centre, size or None (type default)
    ("ex_vgf", "ot_vgf", "crystals", [32.0, 15.0], None),
    ("ex_gaas", "ot_showcase", "crystals", [34.0, 12.5], None),
    ("ex_growth_video", "ot_wall_screen", "crystals", [32.5, 17.65], None),
    ("ex_quantrons_1", "ot_showcase", "quantrons", [26.0, 13.0], None),
    ("ex_quantrons_2", "ot_showcase", "quantrons", [26.2, 15.6], None),
    ("ex_diodes_1", "ot_showcase", "diodes", [19.5, 13.0], None),
    ("ex_diodes_2", "ot_showcase", "diodes", [21.0, 15.6], None),
    ("ex_diodes_video", "ot_wall_screen", "diodes", [19.5, 17.65], None),
    ("ex_fl9000", "ot_ls_fl9000", "laser_sources", [14.0, 13.0], None),
    ("ex_fl20000", "ot_ls_fl20000", "laser_sources", [15.5, 15.8], None),
    ("ex_ndyag", "ot_ndyag", "laser_sources", [16.5, 12.5], None),
    ("ex_robot_cell", "ot_robot_cell", "robots", [8.5, 13.0], None),
    ("ex_graver_compact", "ot_graver_table", "engraving", [2.5, 12.5], None),
    ("ex_graver_portal", "ot_graver_portal", "engraving", [4.8, 14.5], None),
    ("ex_engraving_samples", "ot_showcase", "engraving", [3.0, 17.5], [2.0, 0.5]),
]

# 66LB-ALM, minimal variant: length 1660 mm, width 1140 mm (research/notes/lassard_facts.md, section 3).
LAMINAR_SIZE_M = [1.66, 1.14]

VARIANTS = {
    "original": {
        "workshopWall": "w_west",
        "mainEntrance": "op_south_2",
        "zones": {
            **TOP_BAND,
            "entrance": [28.0, 0.0, 36.0, 9.5],
            "handheld": [6.5, 5.0, 12.0, 9.5],
            "cutting": [0.0, 6.0, 6.5, 11.0],
            "test_lab": [0.0, 0.0, 6.5, 6.0],
            "meeting": [6.5, 0.0, 11.2, 5.0],
            "optomechanics": [17.5, 0.0, 22.5, 9.0],
            "edu_class": [22.5, 0.0, 28.0, 9.0],
        },
        "walls": [
            # id, from, to, height, role
            ("w_lab_n", [0.0, 6.0], [6.5, 6.0], 7.0, "lab"),
            ("w_lab_e", [6.5, 0.0], [6.5, 6.0], 7.0, "lab"),
            ("w_meet_n", [6.5, 5.0], [11.2, 5.0], 7.0, "meeting"),
            ("w_meet_e", [11.2, 0.0], [11.2, 5.0], 7.0, "meeting"),
        ],
        "openings": [
            # id, wall, offset, width, kind, sill, height, role
            ("op_glass_workshop", "w_west", 6.0, 5.0, "window", 0.0, 3.5, "glass"),
            ("op_lab_workshop", "w_west", 1.0, 1.2, "door", 0.0, 2.1, "lab_workshop"),
            ("op_lab_hall", "w_lab_n", 4.6, 1.2, "door", 0.0, 2.1, "lab_hall"),
            ("op_lab_hatch", "w_lab_n", 0.8, 0.6, "window", 0.9, 0.6, "hatch"),
            ("op_meeting", "w_meet_e", 0.8, 1.2, "door", 0.0, 2.1, "meeting"),
        ],
        "objects": TOP_OBJECTS + [
            ("ex_timeline", "ot_panel", "entrance", [35.7, 7.45], [0.4, 4.0]),
            ("ex_map", "ot_panel", "entrance", [31.0, 7.0], None),
            ("ex_scale", "ot_panel", "entrance", [29.0, 3.5], [0.4, 3.0]),
            ("ex_multi_hero", "ot_multi_hero", "handheld", [8.35, 6.75], None),
            ("ex_cleaner_prom", "ot_cleaner_prom", "handheld", [10.75, 6.75], None),
            ("ex_welder_mini", "ot_welder_mini", "handheld", [9.0, 8.7], None),
            ("ex_smart_base", "ot_smart_base", "cutting", [4.0, 9.0], None),
            ("ex_demo_graver", "ot_graver_3d", "test_lab", [3.6, 5.45], None),
            ("ex_clean_zone", "ot_clean_zone", "test_lab", [5.15, 1.35], None),
            ("ex_meeting_table", "ot_meeting_table", "meeting", [8.85, 2.6], None),
            ("ex_meeting_screen", "ot_wall_screen", "meeting", [8.85, 4.85], [1.6, 0.15]),
            ("ex_optical_table", "ot_optical_table", "optomechanics", [20.0, 5.0], None),
            ("ex_mirea", "ot_kit_stand", "optomechanics", [18.6, 2.0], None),
            ("ex_laminar", "ot_kit_stand", "optomechanics", [21.4, 2.0], LAMINAR_SIZE_M),
            ("ex_sim_desk_1", "ot_sim_desk", "edu_class", [25.8, 6.5], None),
            ("ex_sim_desk_2", "ot_sim_desk", "edu_class", [26.4, 4.2], None),
            ("ex_edu_screen", "ot_wall_screen", "edu_class", [25.5, 0.2], None),
        ],
    },
    "mirror": {
        "workshopWall": "w_east",
        "mainEntrance": "op_south_1",
        "zones": {
            **TOP_BAND,
            "entrance": [16.5, 0.0, 25.0, 9.5],
            "handheld": [6.5, 5.5, 12.0, 9.5],
            "cutting": [0.0, 7.0, 6.5, 11.0],
            "test_lab": [0.0, 2.5, 6.5, 7.0],
            "meeting": [7.7, 0.0, 11.2, 5.5],
            "edu_class": [25.0, 0.0, 30.5, 9.5],
            "optomechanics": [30.5, 0.0, 36.0, 9.5],
        },
        "walls": [
            ("w_lab_s", [0.0, 2.5], [6.5, 2.5], 7.0, "lab"),
            ("w_lab_n", [0.0, 7.0], [6.5, 7.0], 7.0, "lab"),
            ("w_lab_e", [6.5, 2.5], [6.5, 7.0], 7.0, "lab"),
            ("w_meet_w", [7.7, 0.0], [7.7, 5.5], 7.0, "meeting"),
            ("w_meet_n", [7.7, 5.5], [11.2, 5.5], 7.0, "meeting"),
            ("w_meet_e", [11.2, 0.0], [11.2, 5.5], 7.0, "meeting"),
        ],
        "openings": [
            ("op_glass_workshop", "w_east", 7.0, 4.0, "window", 0.0, 3.5, "glass"),
            ("op_lab_workshop", "w_east", 5.0, 1.2, "door", 0.0, 2.1, "lab_workshop"),
            ("op_lab_hall", "w_lab_n", 4.6, 1.2, "door", 0.0, 2.1, "lab_hall"),
            ("op_lab_hatch", "w_lab_n", 0.5, 0.6, "window", 0.9, 0.6, "hatch"),
            ("op_meeting", "w_meet_e", 0.8, 1.2, "door", 0.0, 2.1, "meeting"),
        ],
        "objects": TOP_OBJECTS + [
            ("ex_timeline", "ot_panel", "entrance", [17.2, 5.0], [0.4, 4.5]),
            ("ex_map", "ot_panel", "entrance", [20.7, 7.0], None),
            ("ex_scale", "ot_panel", "entrance", [22.1, 3.8], [0.4, 3.0]),
            ("ex_multi_hero", "ot_multi_hero", "handheld", [8.4, 7.2], None),
            ("ex_cleaner_prom", "ot_cleaner_prom", "handheld", [10.8, 7.2], None),
            ("ex_welder_mini", "ot_welder_mini", "handheld", [9.0, 9.15], None),
            ("ex_smart_base", "ot_smart_base", "cutting", [4.0, 9.3], None),
            ("ex_demo_graver", "ot_graver_3d", "test_lab", [2.0, 6.5], None),
            ("ex_clean_zone", "ot_clean_zone", "test_lab", [5.15, 3.85], None),
            ("ex_meeting_table", "ot_meeting_table", "meeting", [9.45, 2.6], [1.2, 2.4]),
            ("ex_meeting_screen", "ot_wall_screen", "meeting", [9.45, 5.35], [1.6, 0.15]),
            ("ex_sim_desk_1", "ot_sim_desk", "edu_class", [27.0, 6.5], None),
            ("ex_sim_desk_2", "ot_sim_desk", "edu_class", [27.0, 4.0], None),
            ("ex_edu_screen", "ot_wall_screen", "edu_class", [27.75, 0.2], None),
            ("ex_optical_table", "ot_optical_table", "optomechanics", [33.2, 5.5], None),
            ("ex_mirea", "ot_kit_stand", "optomechanics", [31.15, 2.0], None),
            ("ex_laminar", "ot_kit_stand", "optomechanics", [33.86, 1.9], LAMINAR_SIZE_M),
        ],
    },
}

# Exits of the hall. Confirmed: the two open south openings. The candidate third exit is
# the red-crossed north door on the workshop side [СПРОСИТЬ]: on the slide it is the left
# door (op_north_1) in the original and the right door (op_north_2) in the mirror.
CONFIRMED_EXITS = ["op_south_1", "op_south_2"]
CANDIDATE_EXIT = {"original": "op_north_1", "mirror": "op_north_2"}


# --- geometry ------------------------------------------------------------------------

Box = tuple[float, float, float, float]


def rect_polygon(r: list[float]) -> list[list[float]]:
    x0, y0, x1, y1 = r
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def polygon_area(poly: list[list[float]]) -> float:
    s = 0.0
    for i, (x0, y0) in enumerate(poly):
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def polygon_box(poly: list[list[float]]) -> Box:
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def is_axis_rect(poly: list[list[float]]) -> bool:
    if len(poly) != 4:
        return False
    return math.isclose(polygon_area(poly), box_area(polygon_box(poly)), abs_tol=1e-9)


def box_area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def overlap_area(a: Box, b: Box) -> float:
    return box_area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def gap(a: Box, b: Box) -> float:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def inflate(b: Box, d: float) -> Box:
    return b[0] - d, b[1] - d, b[2] + d, b[3] + d


def object_box(obj: dict) -> Box:
    if obj["rotation_deg"] % 90:
        raise ValueError(f"{obj['id']}: only 0/90/180/270 degrees are supported")
    w, d = obj["size_m"]
    if obj["rotation_deg"] % 180:
        w, d = d, w
    x, y = obj["position"]
    return x - w / 2, y - d / 2, x + w / 2, y + d / 2


def wall_box(wall: dict, start: float = 0.0, end: float | None = None) -> Box:
    (x0, y0), (x1, y1) = wall["from"], wall["to"]
    length = math.hypot(x1 - x0, y1 - y0)
    end = length if end is None else end
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    a = (x0 + ux * start, y0 + uy * start)
    b = (x0 + ux * end, y0 + uy * end)
    t = wall["thickness_m"] / 2
    return min(a[0], b[0]) - t * abs(uy), min(a[1], b[1]) - t * abs(ux), \
        max(a[0], b[0]) + t * abs(uy), max(a[1], b[1]) + t * abs(ux)


def opening_segment(plan: dict, opening: dict) -> tuple[tuple[float, float], tuple[float, float]]:
    wall = next(w for w in plan["walls"] if w["id"] == opening["wallId"])
    (x0, y0), (x1, y1) = wall["from"], wall["to"]
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    s, e = opening["offset_m"], opening["offset_m"] + opening["width_m"]
    return (x0 + ux * s, y0 + uy * s), (x0 + ux * e, y0 + uy * e)


def segment_distance(a, b) -> float:
    """Shortest distance between two axis-parallel segments (as degenerate boxes)."""
    ba = (min(a[0][0], a[1][0]), min(a[0][1], a[1][1]), max(a[0][0], a[1][0]), max(a[0][1], a[1][1]))
    bb = (min(b[0][0], b[1][0]), min(b[0][1], b[1][1]), max(b[0][0], b[1][0]), max(b[0][1], b[1][1]))
    return gap(ba, bb)


def approach_box(plan: dict, opening: dict) -> Box:
    """Floor in front of an opening in the room contour, APPROACH_M deep, inside the hall."""
    (ax, ay), (bx, by) = opening_segment(plan, opening)
    x0, y0, x1, y1 = polygon_box(plan["room"]["boundary"])
    if math.isclose(ay, by):  # horizontal wall
        inward = APPROACH_M if math.isclose(ay, y0) else -APPROACH_M
        return min(ax, bx), min(ay, ay + inward), max(ax, bx), max(ay, ay + inward)
    inward = APPROACH_M if math.isclose(ax, x0) else -APPROACH_M
    return min(ax, ax + inward), min(ay, by), max(ax, ax + inward), max(ay, by)


# --- build ---------------------------------------------------------------------------

# Beam of the catalog model (content/catalog.json, field `beam`) per object type (#321).
# D-001: nothing in the showroom has power, so every item of these types gets `live: false`.
# Without `live`, the validator counts a beam item as powered (#301).
BEAMS = {
    "ot_robot_cell": "open",  # robot-graver-cell
    "ot_graver_table": "open",  # graver-compact
    "ot_graver_portal": "closed",  # graver-portal
    "ot_graver_3d": "closed",  # graver-3d
    "ot_smart_base": "closed",  # smart-base
    "ot_multi_hero": "open",  # multi-hero
    "ot_cleaner_prom": "open",  # cleaner-prom
    "ot_welder_mini": "open",  # welder-mini
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def beam_attributes(type_id: str) -> list[dict]:
    if type_id not in BEAMS:
        return []
    return [{"key": "beam", "label": "Луч", "type": "string", "required": False, "default": BEAMS[type_id]}]


# Expert of LASSARD, 24.10 (#335): white and red are the base, technical grey only for
# machines, black only in details. Furniture of the exhibition is white (#369).
WHITE_CATEGORIES = {"Экспозиция", "Лазерный класс", "Переговоры"}


def category_color(category: str) -> str:
    if category == "Демо-зона":
        return "#8F1E1E"
    return "#F1F3F5" if category in WHITE_CATEGORIES else "#4F4F4F"


def build(variant: str) -> dict:
    spec = VARIANTS[variant]
    plan = copy.deepcopy(load(BASE[variant]))
    meta = plan["extensions"]["plan219"]
    removed = list(meta["walls"]["removableIds"])
    plan["id"] = f"{plan['id']}_zoned"
    plan["name"] = plan["name"] + " — зонирование"
    plan["walls"] = [w for w in plan["walls"] if w["id"] not in removed]
    for wid, a, b, height, _role in spec["walls"]:
        plan["walls"].append({"id": wid, "from": a, "to": b, "thickness_m": 0.1, "height_m": height})
    for oid, wall, offset, width, kind, sill, height, _role in spec["openings"]:
        plan["openings"].append({
            "id": oid, "wallId": wall, "offset_m": offset, "width_m": width,
            "kind": kind, "sill_m": sill, "height_m": height,
        })
    plan["layers"] += [
        {"id": "l_zones", "name": "Зоны", "visible": True, "locked": False, "order": 1, "typeId": None},
        {"id": "l_exhibits", "name": "Экспонаты и мебель", "visible": True, "locked": False,
         "order": 2, "typeId": None},
    ]
    plan["zones"] = []
    for zid in ZONE_IDS:
        name, ztype, _row, _fire = ZONE_META[zid]
        plan["zones"].append({
            "id": zid, "typeId": ztype, "name": name, "polygon": rect_polygon(spec["zones"][zid]),
            "parentId": None, "layerId": "l_zones", "attributes": {},
        })
    for oid, tid, zid, pos, size in spec["objects"]:
        label, _cat, default_size, height, _prov = OBJECT_TYPES[tid]
        plan["objects"].append({
            "id": oid, "typeId": tid, "label": label, "position": pos,
            "size_m": size or default_size, "rotation_deg": 0, "base_m": 0, "height_m": height,
            "zoneId": zid, "layerId": "l_exhibits",
            "attributes": {"live": False} if tid in BEAMS else {},
        })
    catalog = plan["catalog"]
    catalog["version"] = "plan219-zoned-1"
    for tid, (label, cat, size, height, prov) in OBJECT_TYPES.items():
        catalog["objectTypes"].append({
            "id": tid, "label": label, "category": cat, "defaultSize_m": size,
            "defaultHeight_m": height, "defaultBase_m": 0, "physical": True, "occupiesFloor": True,
            "symbol": "rect", "color": category_color(cat),
            "attributes": beam_attributes(tid), "provenance": prov,
        })
    catalog["zoneTypes"] = [{"id": i, "label": lbl, "color": c, "attributes": []} for i, lbl, c in ZONE_TYPES]
    meta["zoning"] = "есть, см. extensions.zoning219 и concept/01-layout.md"
    plan["extensions"]["zoning219"] = zoning_extension(plan, variant, removed)
    plan["extensions"]["zoning219"]["checks"] = summary(check(plan))
    return plan


def zoning_extension(plan: dict, variant: str, removed: list[str]) -> dict:
    spec = VARIANTS[variant]
    roles = {o[0]: o[7] for o in spec["openings"]}
    zones = {}
    for z in plan["zones"]:
        name, _t, row, fire = ZONE_META[z["id"]]
        zones[z["id"]] = {
            "slide3Row": row, "fireClass": fire,
            "area_m2": round(polygon_area(z["polygon"]), 2),
            "routeStep": ROUTE.index(z["id"]) + 1 if z["id"] in ROUTE else None,
        }
    return {
        "task": "#23",
        "doc": "concept/01-layout.md",
        "variant": variant,
        "workshopWallId": spec["workshopWall"],
        "removedWallIds": removed,
        "route": ROUTE,
        "sideStops": SIDE_STOPS,
        "mainEntranceId": spec["mainEntrance"],
        "exits": {
            "confirmed": CONFIRMED_EXITS,
            "candidate": CANDIDATE_EXIT[variant],
            "candidateStatus": "проём перечёркнут на схеме; можно ли открыть его как эвакуационный выход — [СПРОСИТЬ]",
        },
        "zones": zones,
        "walls": {
            w[0]: ("стекло, противопожарная преграда EIW 45 (решение концепции, 05-safety 4.4), без лазерного слоя: луча в зоне нет (D-001)"
                   if w[4] == "lab" else "перегородка переговорной, высота 7 м, до потолка (#185, эксперт ЛАССАРД, ЧП2)")
            for w in spec["walls"]
        },
        "openings": {
            oid: {
                "glass": "светопрозрачная перегородка в цех: EIW 45 + лазерный фильтр (05-safety 3.5); участок — оценка",
                "lab_workshop": "запасной выход демо-зоны в цех — не подтверждён [СПРОСИТЬ] (05-safety 4.3)",
                "lab_hall": "дверь демо-зоны в зал, только персонал; луча в демо-зоне нет (D-001)",
                "hatch": "окно передачи образцов: гость отдаёт и получает образец, внутрь не входит; окно E 30 в преграде EIW 45 (05-safety 3.5, проверить)",
                "meeting": "дверь переговорной, открывается наружу",
            }[roles[oid]]
            for oid in roles
        },
        "gallery": "нет: галерею над цехом не закладываем (рекомендация, concept/01-layout.md, раздел 8)",
    }


# --- checks --------------------------------------------------------------------------

def solid_wall_boxes(plan: dict) -> list[Box]:
    """Wall pieces without door and entrance gaps (windows stay solid)."""
    return [b for _w, b in solid_walls(plan)]


def solid_walls(plan: dict) -> list[tuple[str, Box]]:
    """Same as solid_wall_boxes, with the wall id of each piece."""
    boxes = []
    for wall in plan["walls"]:
        length = math.hypot(wall["to"][0] - wall["from"][0], wall["to"][1] - wall["from"][1])
        gaps = sorted(
            (o["offset_m"], o["offset_m"] + o["width_m"]) for o in plan["openings"]
            if o["wallId"] == wall["id"] and o["kind"] in ("door", "entrance")
        )
        pos = 0.0
        for s, e in gaps + [(length, length)]:
            if s > pos:
                boxes.append((wall["id"], wall_box(wall, pos, s)))
            pos = max(pos, e)
    return boxes


def columns(plan: dict) -> list[dict]:
    return [o for o in plan["objects"] if o["typeId"] == "ot_column"]


def exhibits(plan: dict) -> list[dict]:
    return [o for o in plan["objects"] if o["typeId"] != "ot_column"]


def free_grid(plan: dict, clearance: float = CLEARANCE_M):
    """Walkable cells: a cell centre keeps `clearance` from walls, exhibits and columns."""
    x0, y0, x1, y1 = polygon_box(plan["room"]["boundary"])
    nx, ny = int((x1 - x0) / GRID_M), int((y1 - y0) / GRID_M)
    obstacles = [inflate(b, clearance) for b in solid_wall_boxes(plan)]
    obstacles += [inflate(object_box(o), clearance) for o in plan["objects"]]
    free = [[True] * ny for _ in range(nx)]
    for i in range(nx):
        cx = x0 + (i + 0.5) * GRID_M
        for j in range(ny):
            cy = y0 + (j + 0.5) * GRID_M
            free[i][j] = not any(b[0] < cx < b[2] and b[1] < cy < b[3] for b in obstacles)
    return (x0, y0, nx, ny), free


STEPS = [(di, dj, GRID_M * math.hypot(di, dj)) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]


def path_field(plan: dict, exit_ids: list[str]):
    """Distance to the nearest exit for every walkable cell (Dijkstra, 8 neighbours)."""
    (x0, y0, nx, ny), free = free_grid(plan)
    dist = [[math.inf] * ny for _ in range(nx)]
    heap = []
    for oid in exit_ids:
        (ax, ay), (bx, by) = opening_segment(plan, next(o for o in plan["openings"] if o["id"] == oid))
        seg = ((ax, ay), (bx, by))
        for i in range(nx):
            for j in range(ny):
                c = (x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M)
                d = segment_distance(seg, (c, c))
                if free[i][j] and d <= CLEARANCE_M + 1.5 * GRID_M and d < dist[i][j]:
                    dist[i][j] = d
                    heapq.heappush(heap, (d, i, j))
    while heap:
        d, i, j = heapq.heappop(heap)
        if d > dist[i][j]:
            continue
        for di, dj, w in STEPS:
            a, b = i + di, j + dj
            if 0 <= a < nx and 0 <= b < ny and free[a][b] and d + w < dist[a][b]:
                if di and dj and not (free[i + di][j] and free[i][j + dj]):
                    continue  # no corner cutting
                dist[a][b] = d + w
                heapq.heappush(heap, (d + w, a, b))
    return (x0, y0, nx, ny), free, dist


# --- visitor route line (for the PNG) ------------------------------------------------

# Route stops tied to an opening: (opening id, metres from it, side). "in" — towards the
# zone centre, "out" — away from it. The guest stands at the glass, at the hatch (outside
# the demo zone) and just inside the meeting room door.
STOP_CLEARANCE_M = 0.6
STOP_AT_OPENING = {
    "cutting": ("op_glass_workshop", 1.2, "in"),
    "test_lab": ("op_lab_hatch", 0.6, "out"),
    "meeting": ("op_meeting", 1.0, "in"),
}


STOP_MARK_R_M = 0.5  # stop circle on the PNG (0.45 m) plus a gap


def route_stops(plan: dict, avoid: list[Box] = ()) -> list[tuple[float, float]]:
    """One stop point per ROUTE zone: the walkable cell nearest to the target point.

    The target is the zone centre or, for STOP_AT_OPENING, a point in front of the opening.
    A stop keeps STOP_CLEARANCE_M from stands: the stop mark on the PNG does not cover them.
    `avoid` — label boxes of the PNG: a stop keeps STOP_MARK_R_M from them if the zone
    has such a cell.
    """
    (x0, y0, nx, ny), free = free_grid(plan, STOP_CLEARANCE_M)

    def clear_of_labels(i: int, j: int) -> bool:
        x, y = x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M
        return all(math.hypot(max(b[0] - x, 0, x - b[2]), max(b[1] - y, 0, y - b[3])) >= STOP_MARK_R_M
                   for b in avoid)
    stops = []
    for zid in ROUTE:
        box = polygon_box(next(z for z in plan["zones"] if z["id"] == zid)["polygon"])
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if zid in STOP_AT_OPENING:
            oid, off, side = STOP_AT_OPENING[zid]
            (ax, ay), (bx, by) = opening_segment(plan, next(o for o in plan["openings"] if o["id"] == oid))
            mx, my = (ax + bx) / 2, (ay + by) / 2
            length = math.hypot(bx - ax, by - ay)
            ux, uy = -(by - ay) / length, (bx - ax) / length  # wall normal
            sign = 1 if (cx - mx) * ux + (cy - my) * uy > 0 else -1
            sign = sign if side == "in" else -sign
            target = (mx + sign * off * ux, my + sign * off * uy)
        else:
            target = (cx, cy)
        cells = [(i, j) for i in range(nx) for j in range(ny) if free[i][j]
                 and (zid == "test_lab" or zone_of(plan, x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M) == zid)]
        cells = [c for c in cells if clear_of_labels(*c)] or cells
        best = min(
            cells,
            key=lambda c: math.hypot(x0 + (c[0] + 0.5) * GRID_M - target[0], y0 + (c[1] + 0.5) * GRID_M - target[1]),
        )
        stops.append((round(x0 + (best[0] + 0.5) * GRID_M, 2), round(y0 + (best[1] + 0.5) * GRID_M, 2)))
    return stops


def _grid_path(free, nx: int, ny: int, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    dist = {start: 0.0}
    prev: dict = {}
    heap = [(0.0, start)]
    while heap:
        d, c = heapq.heappop(heap)
        if c == goal:
            break
        if d > dist[c]:
            continue
        i, j = c
        for di, dj, w in STEPS:
            a, b = i + di, j + dj
            if not (0 <= a < nx and 0 <= b < ny and free[a][b]):
                continue
            if di and dj and not (free[i + di][j] and free[i][j + dj]):
                continue
            if d + w < dist.get((a, b), math.inf):
                dist[(a, b)] = d + w
                prev[(a, b)] = c
                heapq.heappush(heap, (d + w, (a, b)))
    if goal not in dist:
        raise ValueError(f"route: no walkable path {start} -> {goal}")
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1]


def _clear(free, a: tuple[int, int], b: tuple[int, int]) -> bool:
    """The straight line a-b stays on walkable cells (sampled every 1/4 cell)."""
    n = max(1, int(4 * math.hypot(b[0] - a[0], b[1] - a[1])))
    for k in range(n + 1):
        t = k / n
        i, j = round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t)
        if not free[i][j]:
            return False
    return True


def route_line(plan: dict, stops: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """Walkable line through the route stops: shortest grid path, then straightened.

    Every segment keeps CLEARANCE_M from exhibits, columns and walls, so the line on the
    PNG does not cross a stand.
    """
    (x0, y0, nx, ny), free = free_grid(plan)
    cell = [(int((x - x0) / GRID_M), int((y - y0) / GRID_M)) for x, y in (stops or route_stops(plan))]
    line: list[tuple[int, int]] = [cell[0]]
    for s, g in zip(cell, cell[1:]):
        path = _grid_path(free, nx, ny, s, g)
        k = 0
        while k < len(path) - 1:
            far = len(path) - 1
            while far > k + 1 and not _clear(free, path[k], path[far]):
                far -= 1
            line.append(path[far])
            k = far
    return [(round(x0 + (i + 0.5) * GRID_M, 2), round(y0 + (j + 0.5) * GRID_M, 2)) for i, j in line]


def zone_of(plan: dict, x: float, y: float) -> str | None:
    for z in plan["zones"]:
        b = polygon_box(z["polygon"])
        if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
            return z["id"]
    return None


def longest_paths(plan: dict, exit_ids: list[str]) -> dict:
    (x0, y0, nx, ny), free, dist = path_field(plan, exit_ids)
    best: dict[str, tuple[float, list[float]]] = {}
    unreachable = 0
    for i in range(nx):
        for j in range(ny):
            if not free[i][j]:
                continue
            x, y = x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M
            if math.isinf(dist[i][j]):
                unreachable += 1
                continue
            key = "test_lab" if zone_of(plan, x, y) == "test_lab" else "hall"
            if dist[i][j] > best.get(key, (-1.0, None))[0]:
                best[key] = (dist[i][j], [round(x, 1), round(y, 1)])
    return {
        key: {"length_m": round(v[0], 1), "from": v[1], "zone": zone_of(plan, *v[1])}
        for key, v in best.items()
    } | {"unreachableCells": unreachable}


def required_gap(zone_id: str | None) -> float:
    return MIN_PASSAGE_M if zone_id in SMALL_ROOMS else MIN_EVAC_PATH_M


def between_box(a: Box, b: Box) -> Box:
    """The free rectangle between two boxes (their gap)."""
    def span(a0, a1, b0, b1):
        if a1 <= b0:
            return a1, b0
        if b1 <= a0:
            return b1, a0
        return max(a0, b0), min(a1, b1)
    x0, x1 = span(a[0], a[2], b[0], b[2])
    y0, y1 = span(a[1], a[3], b[1], b[3])
    return x0, y0, x1, y1


def narrow_passages(plan: dict) -> list[list]:
    """Gaps below the norm: exhibit-exhibit, exhibit-column and exhibit-wall.

    A gap with a wall inside it is not a passage (the wall gap is checked instead).
    A gap of AGAINST_WALL_M or less is not a passage: the exhibit stands against the wall.
    The norm of a gap is 1.0 m only if all its exhibits are in the meeting room or the
    demo zone; else 1.2 m.
    """
    objs = exhibits(plan)
    cols = columns(plan)
    walls = solid_walls(plan)
    narrow = []
    others = objs + cols
    for k, a in enumerate(objs):
        for b in others[k + 1:]:
            ab, bb = object_box(a), object_box(b)
            g = gap(ab, bb)
            need = max(required_gap(a["zoneId"]), required_gap(b["zoneId"]) if b["zoneId"] else 0.0)
            if g >= need - 1e-9:
                continue
            mid = between_box(ab, bb)
            if any(overlap_area(w, mid) > 0 for _i, w in walls):
                continue
            narrow.append([a["id"], b["id"], round(g, 2)])
    for a in objs:
        if a["typeId"] in WALL_MOUNTED:
            continue
        ab = object_box(a)
        for wid, w in walls:
            g = gap(ab, w)
            if AGAINST_WALL_M < g < required_gap(a["zoneId"]) - 1e-9:
                narrow.append([a["id"], wid, round(g, 2)])
    return narrow


def check(plan: dict) -> dict:
    zones = plan["zones"]
    objs = exhibits(plan)
    cols = columns(plan)
    openings = {o["id"]: o for o in plan["openings"]}
    candidate = CANDIDATE_EXIT[plan["extensions"]["plan219"]["variant"]]
    out: dict = {"candidateExit": candidate}

    out["zoneIds"] = sorted(z["id"] for z in zones) == sorted(ZONE_IDS)
    out["zonesAreRectangles"] = all(is_axis_rect(z["polygon"]) for z in zones)
    areas = {z["id"]: round(polygon_area(z["polygon"]), 2) for z in zones}
    out["zoneAreas_m2"] = areas
    out["zoneAreaSum_m2"] = round(sum(areas.values()), 2)
    out["hallArea_m2"] = CASE_AREA_M2
    room = polygon_box(plan["room"]["boundary"])
    out["zonesOutsideRoom"] = [z["id"] for z in zones if overlap_area(polygon_box(z["polygon"]), room)
                               < polygon_area(z["polygon"]) - 1e-6]
    out["zoneOverlaps"] = [
        [a["id"], b["id"], round(overlap_area(polygon_box(a["polygon"]), polygon_box(b["polygon"])), 3)]
        for k, a in enumerate(zones) for b in zones[k + 1:]
        if overlap_area(polygon_box(a["polygon"]), polygon_box(b["polygon"])) > 1e-6
    ]
    zone_box = {z["id"]: polygon_box(z["polygon"]) for z in zones}
    out["objectsOutsideZone"] = [
        o["id"] for o in objs
        if o["zoneId"] not in zone_box or overlap_area(object_box(o), zone_box[o["zoneId"]])
        < box_area(object_box(o)) - 1e-6
    ]
    out["columnClashes"] = [
        [o["id"], c["id"]] for o in objs for c in cols if overlap_area(object_box(o), object_box(c)) > 0
    ]
    walls = solid_wall_boxes(plan)
    out["wallClashes"] = [o["id"] for o in objs if any(overlap_area(object_box(o), w) > 0 for w in walls)]
    out["narrowPassages"] = narrow_passages(plan)
    exit_ids = CONFIRMED_EXITS + [candidate]
    out["exitWidths_m"] = {i: openings[i]["width_m"] for i in exit_ids}
    out["narrowExits"] = [i for i in exit_ids if openings[i]["width_m"] < MIN_EXIT_M]
    out["blockedExitApproaches"] = [
        [i, o["id"]] for i in exit_ids for o in objs if overlap_area(object_box(o), approach_box(plan, openings[i])) > 0
    ]
    half_diag = math.hypot(room[2] - room[0], room[3] - room[1]) / 2
    seg = {i: opening_segment(plan, openings[i]) for i in exit_ids}
    out["exitSpacing"] = {
        "halfDiagonal_m": round(half_diag, 2),
        "method": "between the near edges of the openings (SP 1.13130.2020, 4.2.16; check the official text)",
        "confirmed_m": round(segment_distance(seg[CONFIRMED_EXITS[0]], seg[CONFIRMED_EXITS[1]]), 2),
        "confirmedFarEdges_m": round(max(math.dist(p, q) for p in seg[CONFIRMED_EXITS[0]]
                                         for q in seg[CONFIRMED_EXITS[1]]), 2),
        "withCandidate_m": round(max(segment_distance(seg[candidate], seg[i]) for i in CONFIRMED_EXITS), 2),
    }
    out["maxPath"] = {
        "confirmedExits": longest_paths(plan, CONFIRMED_EXITS),
        "onlyOneExit": {i: longest_paths(plan, [i])["hall"]["length_m"] for i in CONFIRMED_EXITS},
        "withCandidate": longest_paths(plan, exit_ids),
        "withBothNorthDoors": longest_paths(plan, CONFIRMED_EXITS + ["op_north_1", "op_north_2"])["hall"]["length_m"],
        "limitC0_m": MAX_PATH_C0_M,
        "limitC1_m": MAX_PATH_C1_M,
    }
    pos = {z: i for i, z in enumerate(ROUTE)}
    out["routeOrder"] = (
        ROUTE[0] == "entrance"
        and pos["crystals"] < pos["quantrons"] < pos["diodes"] < pos["laser_sources"]
        < min(pos[z] for z in ("robots", "engraving", "cutting", "handheld"))
        and pos["cutting"] < pos["test_lab"] < pos["meeting"] == len(ROUTE) - 1
        and sorted(ROUTE + SIDE_STOPS) == sorted(ZONE_IDS)
    )
    return out


def failures(result: dict) -> list[str]:
    bad = []
    for key in ("zoneIds", "zonesAreRectangles", "routeOrder"):
        if not result[key]:
            bad.append(key)
    for key in ("zonesOutsideRoom", "zoneOverlaps", "objectsOutsideZone", "columnClashes", "wallClashes",
                "narrowPassages", "narrowExits", "blockedExitApproaches"):
        if result[key]:
            bad.append(f"{key}: {result[key]}")
    if result["zoneAreaSum_m2"] > CASE_AREA_M2:
        bad.append(f"zoneAreaSum_m2 {result['zoneAreaSum_m2']} > {CASE_AREA_M2}")
    mp = result["maxPath"]["confirmedExits"]
    if mp["hall"]["length_m"] > MAX_PATH_C0_M:
        bad.append(f"maxPath hall {mp['hall']['length_m']} > {MAX_PATH_C0_M}")
    if mp["unreachableCells"]:
        bad.append(f"unreachable cells: {mp['unreachableCells']}")
    return bad


def summary(result: dict) -> dict:
    """What the zoned file records about itself (no per-zone dump, it is in zoning219.zones)."""
    mp = result["maxPath"]
    sp = result["exitSpacing"]
    return {
        "command": "python3 scripts/plan_zones.py --check",
        "zoneAreaSum_m2": result["zoneAreaSum_m2"],
        "zoneOverlaps": len(result["zoneOverlaps"]),
        "columnClashes": len(result["columnClashes"]),
        "narrowPassages": len(result["narrowPassages"]),
        "candidateExit": result["candidateExit"],
        "maxPathHall_m": mp["confirmedExits"]["hall"]["length_m"],
        "maxPathHallWithCandidate_m": mp["withCandidate"]["hall"]["length_m"],
        "maxPathHallWithBothNorthDoors_m": mp["withBothNorthDoors"],
        "maxPathTestLab_m": mp["confirmedExits"]["test_lab"]["length_m"],
        "exitSpacingConfirmed_m": sp["confirmed_m"],
        "exitSpacingConfirmedFarEdges_m": sp["confirmedFarEdges_m"],
        "exitSpacingWithCandidate_m": sp["withCandidate_m"],
        "halfDiagonal_m": sp["halfDiagonal_m"],
        "pathMethod": "сетка 0,2 м, 8 соседей, отступ 0,3 м от препятствий; длина не короче реальной",
    }


def report(variant: str, result: dict) -> list[str]:
    mp, sp = result["maxPath"], result["exitSpacing"]
    hall = mp["confirmedExits"]["hall"]
    lab = mp["confirmedExits"]["test_lab"]
    lines = [
        f"[{variant}] zones {len(result['zoneAreas_m2'])}, ids = contract: {result['zoneIds']}; "
        f"route order ok: {result['routeOrder']}",
        f"  zone area sum {result['zoneAreaSum_m2']} m2 <= hall {CASE_AREA_M2} m2: "
        f"{result['zoneAreaSum_m2'] <= CASE_AREA_M2}",
        "  areas: " + ", ".join(f"{k} {v}" for k, v in result["zoneAreas_m2"].items()),
        f"  zone overlaps {len(result['zoneOverlaps'])}, outside room {len(result['zonesOutsideRoom'])}, "
        f"objects outside zone {len(result['objectsOutsideZone'])}",
        f"  column clashes {len(result['columnClashes'])}, wall clashes {len(result['wallClashes'])}, "
        f"passages < {MIN_EVAC_PATH_M} m (hall) / {MIN_PASSAGE_M} m (meeting, demo zone): {len(result['narrowPassages'])}, blocked exit approaches "
        f"{len(result['blockedExitApproaches'])}",
        "  exit widths: " + ", ".join(f"{k} {v} m" for k, v in result["exitWidths_m"].items())
        + f" (min {MIN_EXIT_M})",
        f"  exit spacing (near edges): confirmed {sp['confirmed_m']} m (far edges {sp['confirmedFarEdges_m']} m), with {result['candidateExit']} {sp['withCandidate_m']} m; "
        f"half diagonal {sp['halfDiagonal_m']} m -> confirmed ok: {sp['confirmed_m'] >= sp['halfDiagonal_m']}",
        f"  max path to exit (hall, 2 confirmed exits): {hall['length_m']} m from {hall['from']} ({hall['zone']}); "
        f"C0 <= {MAX_PATH_C0_M}: {hall['length_m'] <= MAX_PATH_C0_M}; C1 <= {MAX_PATH_C1_M}: "
        f"{hall['length_m'] <= MAX_PATH_C1_M}",
        "  only one exit open: " + ", ".join(f"{k} {v} m" for k, v in mp["onlyOneExit"].items()),
        f"  with {result['candidateExit']}: hall {mp['withCandidate']['hall']['length_m']} m; "
        f"with both north doors: hall {mp['withBothNorthDoors']} m; "
        f"test_lab staff to a hall exit: {lab['length_m']} m; unreachable cells "
        f"{mp['confirmedExits']['unreachableCells']}",
    ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write content/plan-219*-zoned.json")
    parser.add_argument("--check", action="store_true", help="check the committed zoned files")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("use --write or --check")
    code = 0
    for variant in VARIANTS:
        if args.write:
            plan = build(variant)
            OUT[variant].write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {OUT[variant].relative_to(ROOT)}")
        plan = load(OUT[variant])
        result = check(plan)
        print("\n".join(report(variant, result)))
        if plan != build(variant):
            print(f"  FAIL: {OUT[variant].relative_to(ROOT)} differs from build(): run --write")
            code = 1
        bad = failures(result)
        for line in bad:
            print(f"  FAIL: {line}")
        code = code or (1 if bad else 0)
    return code


if __name__ == "__main__":
    sys.exit(main())
