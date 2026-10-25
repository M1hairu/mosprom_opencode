"""Laser and fire rules: G5 with TRAP-4, D-001 (no live beam process), G15. One violating and one clean plan each."""

from plan_builder import area, codes, door, findings, hall, item, wall


def showroom() -> dict:
    return hall(20, 10, exits=[("south", 2, 1.2), ("north", 9, 1.2)])


def compartment(plan: dict) -> dict:
    """Corner 14..20 × 6..10 closed by two partitions with a door: a fire compartment."""
    plan["walls"] += [
        wall("w_part_v", (14, 10), (14, 6), 0.1),
        wall("w_part_h", (14, 6), (20, 6), 0.1),
    ]
    plan["openings"].append(door("op_part", "w_part_h", 2, 1.2))
    plan["zones"].append(area("z_demo", 14, 6, 20, 10, fireBarrier="EIW 45", interlock=True))
    return plan


def test_clean_showroom_has_no_findings():
    assert codes(showroom()) == []


def test_TRAP_4_open_beam_in_visitor_hall_is_error():
    """TRAP-4: an open class 4 beam (hand lasers, SMART BASE) in the visitor zone."""
    plan = showroom()
    plan["objects"].append(item("hand", (5, 5), (1, 1), "ot_cleaner", beam="open"))
    found = findings(plan)
    assert [f.code for f in found] == ["OPEN_BEAM_OUTSIDE_INTERLOCK"]
    assert found[0].refs[0].id == "hand"
    assert "Питание не указано" in found[0].message


def test_TRAP_4_open_beam_in_unwalled_interlock_zone_is_error():
    """TRAP-4: an interlock flag on a zone without walls is not a cabin."""
    plan = showroom()
    plan["zones"].append(area("z_cabin", 3, 3, 7, 7, interlock=True))
    plan["objects"].append(item("hand", (5, 5), (1, 1), "ot_cleaner", beam="open"))
    assert codes(plan) == ["OPEN_BEAM_OUTSIDE_INTERLOCK"]


def test_TRAP_4_open_beam_in_walled_interlock_zone_is_clean():
    """Power is explicit (live: false). Power not specified: see the #174 test below."""
    plan = compartment(showroom())
    plan["objects"].append(item("hand", (17, 8.5), (1, 1), "ot_cleaner", beam="open", live=False))
    assert codes(plan) == []


def test_open_beam_without_power_stands_in_hall():
    plan = showroom()
    plan["objects"].append(item("hand", (5, 5), (1, 1), "ot_cleaner", beam="open", live=False))
    assert codes(plan) == []


def test_open_beam_unknown_power_in_walled_interlock_zone_is_error():
    """#174: power not specified means not proven off. The cabin does not make it clean."""
    plan = compartment(showroom())
    plan["objects"].append(item("hand", (17, 8.5), (1, 1), "ot_cleaner", beam="open"))
    found = findings(plan)
    assert [f.code for f in found] == ["LIVE_PROCESS_FORBIDDEN"]
    assert found[0].refs[0].id == "hand"
    assert "питание не указано" in found[0].message
    assert "live: false" in found[0].message


def test_open_beam_unknown_power_in_hall_gives_one_finding():
    """The hall case stays G5 only: one finding, not two."""
    plan = showroom()
    plan["objects"].append(item("hand", (5, 5), (1, 1), "ot_cleaner", beam="open"))
    assert codes(plan) == ["OPEN_BEAM_OUTSIDE_INTERLOCK"]


def test_g5_message_does_not_promise_a_working_beam():
    plan = showroom()
    plan["objects"].append(item("hand", (5, 5), (1, 1), "ot_cleaner", beam="open", live=True))
    messages = " ".join(
        f.message for f in findings(plan) if f.code == "OPEN_BEAM_OUTSIDE_INTERLOCK"
    )
    assert "работает только" not in messages
    assert "D-001" in messages


def test_closed_beam_by_type_default_without_power_is_clean():
    plan = showroom()
    plan["objects"].append(item("smart", (5, 5), (2, 1), "ot_cutter", live=False))
    assert codes(plan) == []


def test_closed_beam_unknown_power_in_demo_zone_is_error():
    """#301: one rule for all beams. Power not specified is not proven off, closed beam too."""
    plan = compartment(showroom())
    plan["objects"].append(item("engraver", (17, 8.5), (1, 1), "ot_engraver", beam="closed"))
    found = findings(plan)
    assert [f.code for f in found] == ["LIVE_PROCESS_FORBIDDEN"]
    assert [r.id for r in found[0].refs] == ["engraver"]
    assert "питание не указано" in found[0].message
    assert "live: false" in found[0].message


def test_closed_beam_unknown_power_by_type_default_gives_one_finding():
    """The beam comes from the catalog type (ot_cutter: closed). One finding, in the hall too."""
    plan = showroom()
    plan["objects"].append(item("smart", (5, 5), (2, 1), "ot_cutter"))
    found = findings(plan)
    assert [f.code for f in found] == ["LIVE_PROCESS_FORBIDDEN"]
    assert [r.id for r in found[0].refs] == ["smart"]


def test_unknown_power_gives_one_finding_per_item_in_every_place():
    """No double findings: the fire barrier rule (G15) is for explicit live: true only."""
    for beam in ("open", "closed"):
        for plan in (showroom(), compartment(showroom())):
            plan["objects"].append(item("x", (17, 8.5), (1, 1), "ot_engraver", beam=beam))
            assert len(findings(plan)) == 1, beam


def test_item_without_beam_and_power_is_clean():
    """An item without `beam` (stand; engraver type with no beam key) is not a beam item: unknown power is no finding."""
    plan = compartment(showroom())
    plan["objects"].append(item("stand", (17, 8.5), (1, 1), "ot_stand"))
    plan["objects"].append(item("engraver", (5, 5), (1, 1), "ot_engraver"))
    assert codes(plan) == []


def test_live_cutting_is_forbidden():
    plan = compartment(showroom())
    plan["objects"].append(item("smart", (17, 8.5), (2, 1), "ot_cutter", live=True))
    assert codes(plan) == ["LIVE_PROCESS_FORBIDDEN"]


def test_live_engraving_is_forbidden_even_in_walled_compartment():
    """New D-001 (#152): no live beam process at all, engraving included."""
    plan = compartment(showroom())
    plan["objects"].append(item("engraver", (17, 8.5), (1, 1), "ot_engraver", live=True))
    found = findings(plan)
    assert [f.code for f in found] == ["LIVE_PROCESS_FORBIDDEN"]
    assert found[0].severity == "error"
    assert [r.id for r in found[0].refs] == ["engraver"]
    assert "без питания" in found[0].message
    assert "D-001" in found[0].message


def test_live_cleaning_is_forbidden_even_in_walled_compartment():
    plan = compartment(showroom())
    plan["objects"].append(item("hand", (17, 8.5), (1, 1), "ot_cleaner", beam="open", live=True))
    assert codes(plan) == ["LIVE_PROCESS_FORBIDDEN"]


def test_live_object_without_category_is_forbidden():
    plan = compartment(showroom())
    plan["objects"].append(item("mystery", (17, 8.5), (1, 1), "ot_unknown", live=True))
    assert codes(plan) == ["LIVE_PROCESS_FORBIDDEN"]


def test_engraver_and_cleaner_without_power_are_clean():
    plan = showroom()
    plan["objects"].append(item("engraver", (5, 5), (1, 1), "ot_engraver", live=False))
    plan["objects"].append(item("hand", (8, 5), (1, 1), "ot_cleaner", beam="open", live=False))
    assert codes(plan) == []


def test_live_machine_outside_fire_compartment_is_error():
    plan = showroom()
    plan["objects"].append(item("engraver", (5, 5), (1, 1), "ot_engraver", live=True))
    found = findings(plan)
    assert sorted(f.code for f in found) == ["LASER_ZONE_NO_FIRE_BARRIER", "LIVE_PROCESS_FORBIDDEN"]
    barrier = next(f for f in found if f.code == "LASER_ZONE_NO_FIRE_BARRIER")
    assert [r.id for r in barrier.refs] == ["engraver"]


def test_compartment_open_to_hall_is_error():
    plan = compartment(showroom())
    plan["walls"] = [w for w in plan["walls"] if w["id"] != "w_part_v"]
    plan["objects"].append(item("engraver", (17, 8.5), (1, 1), "ot_engraver", live=True))
    found = findings(plan)
    assert sorted(f.code for f in found) == ["LASER_ZONE_NO_FIRE_BARRIER", "LIVE_PROCESS_FORBIDDEN"]
    barrier = next(f for f in found if f.code == "LASER_ZONE_NO_FIRE_BARRIER")
    assert [r.id for r in barrier.refs] == ["z_demo", "engraver"]
