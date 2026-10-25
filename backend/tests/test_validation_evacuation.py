"""G16 and G17 on the evacuation grid. One violating and one clean plan each."""

import json
from pathlib import Path

from plan_builder import area, codes, door, findings, hall, item, wall

from api.contracts import PlanDocument
from api.validation import validate_plan

ROOT = Path(__file__).resolve().parents[2]


def two_exits(width: float = 20, depth: float = 10, capacity: float | None = None) -> dict:
    return hall(width, depth, exits=[("south", 2, 1.2), ("north", 9, 1.2)], capacity=capacity)


def test_plan_219_has_no_findings():
    """The columns on the locked layer l_building are the hall itself, not misplaced objects."""
    for name in ("plan-219.json", "plan-219-mirror.json"):
        plan = PlanDocument.model_validate_json((ROOT / "content" / name).read_text("utf-8"))
        assert validate_plan(plan) == []


def test_building_column_still_collides_with_a_stand():
    plan = json.loads((ROOT / "content" / "plan-219.json").read_text("utf-8"))
    column = next(o for o in plan["objects"] if o["id"] == "col_A2")
    plan["objects"].append({**item("stand", column["position"], (1, 1)), "layerId": "l_base"})
    plan["layers"].append(
        {"id": "l_base", "name": "Основной", "visible": True, "locked": False, "order": 1}
    )
    found = validate_plan(PlanDocument.model_validate(plan))
    assert ("OBJECT_COLLISION", ["col_A2", "stand"]) in [
        (f.code, [r.id for r in f.refs]) for f in found
    ]


def test_locked_layer_is_not_the_building():
    """D-014: `locked` only stops moving; an object outside the room is still an error."""
    plan = two_exits()
    plan["layers"][0]["locked"] = True
    plan["objects"].append(item("stand", (19.9, 5), (1, 1)))
    assert "OBJECT_OUTSIDE_ROOM" in codes(plan)


def test_room_without_exit_is_error():
    plan = hall(20, 10)
    assert codes(plan) == ["EXITS_TOO_FEW"]


def test_one_exit_for_crowd_is_error():
    plan = hall(20, 10, exits=[("south", 2, 1.2)], capacity=60)
    found = findings(plan)
    assert [f.code for f in found] == ["EXITS_TOO_FEW"]
    assert [r.id for r in found[0].refs] == ["room", "op_1"]


def test_one_exit_for_small_group_and_short_path_is_clean():
    plan = hall(20, 10, exits=[("south", 9, 1.2)], capacity=30)
    assert codes(plan) == []


def test_one_exit_with_path_over_25_m_is_error():
    plan = hall(28, 6, exits=[("south", 0.5, 1.2)], capacity=30)
    found = findings(plan)
    assert [f.code for f in found] == ["EXITS_TOO_FEW"]
    assert "больше 25" in found[0].message


def test_unknown_capacity_takes_strict_exit_width():
    plan = hall(20, 10, exits=[("south", 2, 1.0), ("north", 9, 1.2)])
    found = findings(plan)
    assert [f.code for f in found] == ["EXIT_TOO_NARROW"]
    assert [r.id for r in found[0].refs] == ["op_1"]
    assert "Вместимость не указана" in found[0].message


def test_narrow_exit_for_small_group_is_clean():
    plan = hall(20, 10, exits=[("south", 2, 1.0), ("north", 9, 1.2)], capacity=30)
    assert codes(plan) == []


def test_window_is_not_an_exit():
    plan = two_exits()
    plan["openings"][1]["kind"] = "window"
    plan["openings"][1]["sill_m"] = 0.9
    assert codes(plan) == ["EXITS_TOO_FEW"]


def test_far_corner_over_30_m_is_error():
    plan = hall(40, 8, exits=[("west", 1, 1.2), ("west", 5, 1.2)])
    found = findings(plan)
    assert [f.code for f in found] == ["EXIT_TOO_FAR"]
    length = float(found[0].message.split("около ")[1].split("\xa0")[0].replace(",", "."))
    # About the straight line from the far corner (39.9, 0.1) to the exit edge (0.1, 1.8).
    assert 39 < length < 40.5


def test_exit_at_each_end_is_clean():
    plan = hall(40, 8, exits=[("west", 3, 1.2), ("east", 3, 1.2)])
    assert codes(plan) == []


def test_path_around_a_partition_counts_the_detour():
    """Straight line about 24 m; around the partition the path is about 32 m."""
    plan = hall(26, 12, exits=[("south", 0.5, 1.2), ("west", 9, 1.2)], capacity=30)
    plan["walls"].append(wall("w_part", (12, 0), (12, 10.5), 0.1))
    assert codes(plan) == ["EXIT_TOO_FAR"]


def test_fire_compartment_floor_is_not_hall_path():
    plan = hall(40, 8, exits=[("west", 1, 1.2), ("west", 5, 1.2)])
    plan["walls"].append(wall("w_part", (24, 0), (24, 8), 0.1))
    plan["openings"].append(door("op_part", "w_part", 3, 1.2))
    plan["zones"].append(area("z_demo", 24, 0, 40, 8, fireBarrier="EIW 45"))
    assert codes(plan) == []


def test_only_narrow_gap_to_the_exit_is_error():
    plan = two_exits()
    plan["openings"] = plan["openings"][:1] + [door("op_2", "w_west", 7, 1.2)]
    plan["walls"].append(wall("w_part", (10, 0), (10, 9), 0.1))
    found = findings(plan)
    assert [f.code for f in found] == ["PASSAGE_TOO_NARROW"]
    assert sorted(r.id for r in found[0].refs) == ["w_north", "w_part"]
    assert "0,90" in found[0].message


def test_wide_gap_to_the_exit_is_clean():
    plan = two_exits()
    plan["openings"] = plan["openings"][:1] + [door("op_2", "w_west", 7, 1.2)]
    plan["walls"].append(wall("w_part", (10, 0), (10, 8.5), 0.1))
    assert codes(plan) == []


def test_narrow_gap_with_wide_detour_is_clean():
    plan = two_exits()
    plan["objects"] += [item("stand_a", (8, 5), (2, 2)), item("stand_b", (11, 5), (2, 2))]
    assert codes(plan) == []


def test_small_group_takes_one_metre_passage():
    plan = two_exits(capacity=30)
    plan["openings"] = plan["openings"][:1] + [door("op_2", "w_west", 7, 1.2)]
    plan["walls"].append(wall("w_part", (10, 0), (10, 8.8), 0.1))
    assert codes(plan) == []


def test_closed_off_part_of_hall_is_error():
    plan = two_exits()
    plan["openings"] = plan["openings"][:1] + [door("op_2", "w_west", 7, 1.2)]
    plan["walls"].append(wall("w_part", (10, 0), (10, 10), 0.1))
    found = findings(plan)
    assert [f.code for f in found] == ["EXIT_UNREACHABLE"]
    assert [r.id for r in found[0].refs] == ["z_hall"]


def test_huge_room_is_not_checked():
    plan = hall(130, 130, exits=[("south", 2, 1.2), ("north", 9, 1.2)])
    found = findings(plan)
    assert [(f.code, f.severity) for f in found] == [("EVACUATION_NOT_CHECKED", "warning")]


def test_hall_path_does_not_run_through_fire_compartment():
    """Under 30 m through the compartment doors; around the compartment about 33 m."""
    plan = hall(26, 14, exits=[("west", 1, 1.2), ("west", 3, 1.2)])
    plan["walls"] += [
        wall("w_c_w", (10, 0), (10, 12), 0.1),
        wall("w_c_n", (10, 12), (20, 12), 0.1),
        wall("w_c_e", (20, 0), (20, 12), 0.1),
    ]
    plan["openings"] += [door("op_c_w", "w_c_w", 0.5, 1.2), door("op_c_e", "w_c_e", 0.5, 1.2)]
    plan["zones"].append(area("z_demo", 10, 0, 20, 12, fireBarrier="EIW 45"))
    assert codes(plan) == ["EXIT_TOO_FAR"]
