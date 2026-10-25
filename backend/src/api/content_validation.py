"""Validate content/*.json against content/schemas/*.schema.json plus content rules.

Stdlib only (Python 3.10). Supported JSON Schema subset: type, required, properties,
additionalProperties (bool), enum, items, minimum, minItems, pattern. Annotations
description, title, $schema, $id are ignored. Any other keyword is an error: a schema
must not carry a constraint that this validator does not check.

Files: facts.json, catalog.json, zones.json, routes.json and every plan*.json.
A plan is a pochta PlanDocument v1 (content/plan-219*.json, #46). Its full schema is #57;
here only the invariants the references need (PLAN_SHAPE) and the references themselves.
At least one plan file is required.

Content rules on top of the schemas:
  G1  every fact has a source: `case`, `public` or `norm`; `text` contains `value`;
  G14 a T8 number (80 %, 0.8, 400+, 14 400 m2 — by value or by text) must have `public`;
  G4  a catalog size is complete with `size_source`, or `estimate: true` with `estimate_basis`;
  G5  (laser class 4 beam on the plan) is NOT checked here: one source is the backend
      POST /api/validate (#30, safety.py, D-014);
  roles students, media, government never step into test_lab, an interlock zone
      or a restricted zone (test_lab: the group has no sample to test, see `reason` in
      routes.json; the reason is not safety, D-001 leaves no beam in the showroom);
  G1  visitor texts in zones and routes have no digits outside {{fact:<id>}} and {{item:<id>}};
  S10 each slide 10 message is carried by at least one zone;
  S2  a zone in maintenance has `maintenance.replacement`;
  S4  the sum of step minutes is within `duration_max_min`; government route <= 40 min;
  ids are unique; references between files exist;
  plan: openings[].wallId, zones[].typeId/parentId/layerId, objects[].typeId/zoneId/layerId
  exist in the plan; a plan zone id (or its parentId for a sub-zone) is a zones.json id
  (enum of zones.schema.json);
  catalog `plan_type` exists in catalog.objectTypes of a plan.

Usage: check-content.py [content_dir] [--schemas schemas_dir]
Exit 0 when valid, 1 on findings, 2 on usage error.
"""

import json
import math
import os
import re
import sys
from pathlib import Path

FILES = ("facts", "catalog", "zones", "routes")
PLAN_GLOB = "plan*.json"
SLIDE10_MESSAGES = ("scale", "history", "localization", "full_cycle", "russian_production")
T8_VALUES = {80, 0.8, 400, 14400}
# T8 number in a compact text; not a part of a longer number (180 %, 1 440).
T8_TEXT = re.compile(r"(?<!\d)(?<!\d\.)(80%|400\+|14400)(?!\d)")
RESTRICTED_ROLES = {"students", "media", "government"}
NEVER_FOR_RESTRICTED_ROLES = {"test_lab"}
GOVERNMENT_MAX_MIN = 40
REF = re.compile(r"\{\{(fact|item):([a-z0-9_.-]+)\}\}")
DIGIT = re.compile(r"\d")
# Keys whose values are ids or enums, not visitor texts.
NON_TEXT_KEYS = {"id", "zone", "exhibits", "status", "carries", "role"}

KEYWORDS = {
    "type",
    "required",
    "properties",
    "additionalProperties",
    "enum",
    "items",
    "minimum",
    "minItems",
    "pattern",
}
ANNOTATIONS = {"description", "title", "$schema", "$id"}

POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2}
STR = {"type": "string"}
STR_OR_NULL = {"type": ["string", "null"]}


def rows(*required, **props):
    """Array of objects with a string id; other fields are free (PlanDocument has more)."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["id", *required],
            "properties": {"id": STR, **props},
        },
    }


# pochta PlanDocument v1: only what the reference checks read. Full schema — #57.
PLAN_SHAPE = {
    "type": "object",
    "required": [
        "schemaVersion",
        "id",
        "name",
        "room",
        "walls",
        "openings",
        "layers",
        "zones",
        "objects",
        "catalog",
    ],
    "properties": {
        "schemaVersion": {"type": "integer", "enum": [1]},
        "id": STR,
        "name": STR,
        "room": {
            "type": "object",
            "required": ["boundary"],
            "properties": {"boundary": {"type": "array", "items": POINT, "minItems": 3}},
        },
        "walls": rows("from", "to", **{"from": POINT, "to": POINT}),
        "openings": rows("wallId", wallId=STR),
        "layers": rows(),
        "zones": rows(
            "typeId",
            "polygon",
            typeId=STR,
            parentId=STR_OR_NULL,
            layerId=STR_OR_NULL,
            polygon={"type": "array", "items": POINT, "minItems": 3},
        ),
        "objects": rows(
            "typeId",
            "position",
            typeId=STR,
            zoneId=STR_OR_NULL,
            layerId=STR_OR_NULL,
            position=POINT,
        ),
        "catalog": {
            "type": "object",
            "required": ["objectTypes", "zoneTypes"],
            "properties": {"objectTypes": rows(), "zoneTypes": rows()},
        },
        "extensions": {"type": "object"},
    },
}

TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and (not isinstance(v, float) or math.isfinite(v))
    ),
    "null": lambda v: v is None,
}


def schema_keywords(schema, path, errors):
    """Report keywords that validate() would silently skip."""
    for key in schema:
        if key not in KEYWORDS and key not in ANNOTATIONS:
            errors.append(f"{path}: ключ схемы «{key}» не поддержан валидатором")
    for key, sub in schema.get("properties", {}).items():
        schema_keywords(sub, f"{path}.properties.{key}", errors)
    if isinstance(schema.get("items"), dict):
        schema_keywords(schema["items"], f"{path}.items", errors)
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        errors.append(f"{path}: additionalProperties — только true или false")


def validate(value, schema, path, errors):
    """Append 'path: message' strings to errors for the supported schema subset."""
    stype = schema.get("type")
    if stype is not None:
        names = stype if isinstance(stype, list) else [stype]
        if not any(TYPES[n](value) for n in names):
            errors.append(f"{path}: ожидался тип {'|'.join(names)}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            f"{path}: значение {json.dumps(value, ensure_ascii=False)} не из {schema['enum']}"
        )
    if "minimum" in schema and TYPES["number"](value) and value < schema["minimum"]:
        errors.append(f"{path}: {value} меньше минимума {schema['minimum']}")
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        errors.append(f"{path}: «{value}» не по шаблону {schema['pattern']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: нет поля «{key}»")
        for key, item in value.items():
            if key in props:
                validate(item, props[key], f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: лишнее поле «{key}»")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: элементов {len(value)}, нужно не меньше {schema['minItems']}")
        if "items" in schema:
            for i, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{i}]", errors)


def visitor_texts(node, path):
    """Yield (path, text) for every visitor-facing string under node."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from visitor_texts(item, f"{path}[{i}]")
    elif isinstance(node, dict):
        for key, item in node.items():
            if key not in NON_TEXT_KEYS:
                yield from visitor_texts(item, f"{path}.{key}")


def check_texts(node, path, ids, errors):
    """G1: digits only through {{fact:<id>}} or {{item:<id>}}; refs must exist."""
    for tpath, text in visitor_texts(node, path):
        for kind, ref in REF.findall(text):
            known = ids.get(kind)
            if known is not None and ref not in known:
                name = "факт" if kind == "fact" else "экспонат"
                errors.append(f"{tpath}: ссылка на неизвестный {name} «{ref}»")
        if DIGIT.search(REF.sub("", text)):
            errors.append(
                f"{tpath}: число в тексте без {{{{fact:<id>}}}} — число берём только из facts.json (G1)"
            )


def unique(rows, key, path, errors):
    seen = set()
    for i, row in enumerate(rows):
        if row.get(key) in seen:
            errors.append(f"{path}[{i}]: повтор {key} «{row.get(key)}»")
        seen.add(row.get(key))


def compact(text):
    return text.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")


def value_in_text(value, text):
    num = int(value) if float(value).is_integer() else value
    return re.search(rf"(?<![\d.]){re.escape(str(num))}(?![\d]|\.\d)", compact(text)) is not None


def brand_claims(node, path, errors):
    for tpath, text in visitor_texts(node, path):
        names = re.findall(r"(?i)\b(?:лассард|lassard)\w*", text)
        if any(name not in ("ЛАССАРД", "LASSARD") for name in names) or re.search(
            r'[«"“](?:ЛАССАРД|LASSARD)[»"”]', text
        ):
            errors.append(f"{tpath}: имя бренда — ЛАССАРД или LASSARD (G2)")
        if re.search(r"(?i)100\s*%|\bсам(ый|ая|ое|ые|ого|ой|ым)\b|\bлучш|№\s*1|лидер рынка", text):
            errors.append(f"{tpath}: запрещено 100 % и превосходная степень (G3)")


def check_rules(docs, plans, zone_ids, plans_ok, errors):
    """Content rules. A reference is checked only when its target file passed the schema."""
    facts = docs.get("facts", {}).get("facts", [])
    catalog = docs.get("catalog", {}).get("items", [])
    zones = docs.get("zones", {}).get("zones", [])
    routes = docs.get("routes", {}).get("routes", [])
    has = set(docs)

    unique(facts, "id", "facts.json: $.facts", errors)
    unique(catalog, "id", "catalog.json: $.items", errors)
    unique(zones, "id", "zones.json: $.zones", errors)
    unique(routes, "role", "routes.json: $.routes", errors)

    for i, f in enumerate(facts):
        p = f"facts.json: $.facts[{i}]"
        if not any(k in f for k in ("case", "public", "norm")):
            errors.append(f"{p}: число без источника — нужно «case», «public» или «norm» (G1)")
        is_t8 = f["value"] in T8_VALUES or T8_TEXT.search(compact(f["text"])) is not None
        if is_t8 and "public" not in f:
            errors.append(f"{p}: число T8 «{f['text']}» без «public» (url, date, value) (G14)")
        if not value_in_text(f["value"], f["text"]):
            errors.append(f"{p}: в «text» нет числа value={f['value']} (G1)")

    for index, fact in enumerate(facts):
        brand_claims(fact["text"], f"facts.json: $.facts[{index}].text", errors)
    for index, item in enumerate(catalog):
        for key in ("name", "note"):
            if key in item:
                brand_claims(item[key], f"catalog.json: $.items[{index}].{key}", errors)
    for name, entries in (("zones", zones), ("routes", routes)):
        for index, entry in enumerate(entries):
            brand_claims(entry, f"{name}.json: $.{name}[{index}]", errors)

    items = {}
    for i, it in enumerate(catalog):
        p = f"catalog.json: $.items[{i}]"
        items[it["id"]] = it
        size = it["size_mm"]
        complete = size is not None and all(
            size.get(k) is not None for k in ("length", "width", "height")
        )
        if it["estimate"] is True:
            if not it.get("estimate_basis"):
                errors.append(f"{p}: «estimate: true» без «estimate_basis» (G4)")
        elif not (complete and it.get("size_source")):
            errors.append(
                f"{p}: габарит неполный или без «size_source» — нужно «estimate: true» + «estimate_basis» (G4)"
            )

    ids = {
        "fact": {f["id"] for f in facts} if "facts" in has else None,
        "item": set(items) if "catalog" in has else None,
    }

    zone_by_id = {z["id"]: z for z in zones}
    carried = set()
    for i, z in enumerate(zones):
        p = f"zones.json: $.zones[{i}]"
        carried.update(z["carries"])
        for j, ex in enumerate(z["exhibits"]):
            if "catalog" not in has:
                continue
            if ex not in items:
                errors.append(f"{p}.exhibits[{j}]: нет экспоната «{ex}» в catalog.json")
        if z["status"] == "maintenance" and "maintenance" not in z:
            errors.append(f"{p}: статус maintenance без «maintenance.replacement» (S2)")
        repl_zone = z.get("maintenance", {}).get("zone")
        if repl_zone is not None and repl_zone not in zone_by_id:
            errors.append(f"{p}.maintenance.zone: нет зоны «{repl_zone}» в zones.json")
        check_texts(z, p, ids, errors)
    if "zones" in has:
        for msg in SLIDE10_MESSAGES:
            if msg not in carried:
                errors.append(
                    f"zones.json: сообщение слайда 10 «{msg}» не несёт ни одна зона (carries)"
                )

    for i, r in enumerate(routes):
        p = f"routes.json: $.routes[{i}]"
        role = r["role"]
        total = sum(s["minutes"] for s in r["steps"])
        if total > r["duration_max_min"]:
            errors.append(
                f"{p}: сумма минут {total} больше duration_max_min {r['duration_max_min']}"
            )
        if role == "government" and total > GOVERNMENT_MAX_MIN:
            errors.append(
                f"{p}: маршрут органов власти {total} мин — больше {GOVERNMENT_MAX_MIN} (S4.1)"
            )
        for j, step in enumerate(r["steps"]):
            sp = f"{p}.steps[{j}]"
            zone = zone_by_id.get(step["zone"])
            if zone is None:
                if "zones" in has:
                    errors.append(f"{sp}: нет зоны «{step['zone']}» в zones.json")
                continue
            safety = zone["safety"]
            closed = (
                zone["id"] in NEVER_FOR_RESTRICTED_ROLES
                or safety["interlock"]
                or safety["restricted"]
            )
            if role in RESTRICTED_ROLES and closed:
                errors.append(
                    f"{sp}: роль «{role}» не входит в зону «{zone['id']}» (испытания, кабина или ограничение)"
                )
        for j, sk in enumerate(r.get("skipped", [])):
            if "zones" in has and sk["zone"] not in zone_by_id:
                errors.append(f"{p}.skipped[{j}]: нет зоны «{sk['zone']}» в zones.json")
        check_texts(r, p, ids, errors)

    plan_types = set()
    for fname, plan in plans.items():
        plan_types.update(t["id"] for t in plan["catalog"]["objectTypes"])
        check_plan(fname, plan, zone_ids, errors)
    if plans_ok:
        for i, it in enumerate(catalog):
            if "plan_type" in it and it["plan_type"] not in plan_types:
                errors.append(
                    f"catalog.json: $.items[{i}].plan_type: нет типа «{it['plan_type']}» "
                    f"в catalog.objectTypes ни одного плана"
                )


def check_plan(fname, plan, zone_ids, errors):
    """PlanDocument v1 references inside the plan; plan zones vs zones.json ids."""
    p = f"{fname}: $"
    brand_claims(plan["name"], f"{p}.name", errors)
    for group, key in (("layers", "name"), ("zones", "name"), ("objects", "label")):
        for i, row in enumerate(plan[group]):
            brand_claims(row.get(key, ""), f"{p}.{group}[{i}].{key}", errors)
    cat = plan["catalog"]
    for group in ("objectTypes", "zoneTypes"):
        for i, kind in enumerate(cat[group]):
            path = f"{p}.catalog.{group}[{i}]"
            brand_claims(kind.get("label", ""), f"{path}.label", errors)
            attributes = kind.get("attributes", [])
            if isinstance(attributes, list):
                for j, attribute in enumerate(attributes):
                    if isinstance(attribute, dict):
                        brand_claims(
                            attribute.get("label", ""), f"{path}.attributes[{j}].label", errors
                        )
    for key in ("walls", "openings", "layers", "zones", "objects"):
        unique(plan[key], "id", f"{p}.{key}", errors)
    for key in ("objectTypes", "zoneTypes"):
        unique(cat[key], "id", f"{p}.catalog.{key}", errors)
    walls = {w["id"] for w in plan["walls"]}
    layers = {lay["id"] for lay in plan["layers"]}
    object_types = {t["id"] for t in cat["objectTypes"]}
    zone_types = {t["id"] for t in cat["zoneTypes"]}
    plan_zones = {z["id"]: z for z in plan["zones"]}

    def ref(path, value, known, what):
        if value is not None and value not in known:
            errors.append(f"{path}: «{value}» нет в {what}")

    for i, op in enumerate(plan["openings"]):
        ref(f"{p}.openings[{i}].wallId", op["wallId"], walls, "walls")
    for i, z in enumerate(plan["zones"]):
        zp = f"{p}.zones[{i}]"
        # A sub-zone (cabin, compartment) has its own id and parentId of a zones.json zone.
        if zone_ids is not None and z["id"] not in zone_ids and z.get("parentId") not in zone_ids:
            errors.append(
                f"{zp}.id: зона «{z['id']}» не из списка зон zones.json и без parentId такой зоны"
            )
        ref(f"{zp}.typeId", z["typeId"], zone_types, "catalog.zoneTypes")
        ref(f"{zp}.parentId", z.get("parentId"), plan_zones, "zones")
        ref(f"{zp}.layerId", z.get("layerId"), layers, "layers")
    for i, obj in enumerate(plan["objects"]):
        op = f"{p}.objects[{i}]"
        ref(f"{op}.typeId", obj["typeId"], object_types, "catalog.objectTypes")
        ref(f"{op}.zoneId", obj.get("zoneId"), plan_zones, "zones")
        ref(f"{op}.layerId", obj.get("layerId"), layers, "layers")


def load(path, label, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"{label}: файл не читается: {exc}")
        return None


def check(content_dir, schemas_dir):
    errors = []
    docs, plans = {}, {}
    targets = [(name, f"{name}.json", content_dir / f"{name}.json") for name in FILES]
    plan_paths = sorted(content_dir.glob(PLAN_GLOB))
    if not plan_paths:
        errors.append(f"{PLAN_GLOB}: нет ни одного файла плана")
    targets += [("plan", p.name, p) for p in plan_paths]
    schemas = {}
    for name in FILES:
        label = f"schemas/{name}.schema.json"
        schema = load(schemas_dir / f"{name}.schema.json", label, errors)
        if schema is not None:
            before = len(errors)
            schema_keywords(schema, label, errors)
            if len(errors) == before:
                schemas[name] = schema
    plans_ok = bool(plan_paths)
    for name, label, path in targets:
        schema = PLAN_SHAPE if name == "plan" else schemas.get(name)
        if schema is None:
            continue
        data = load(path, label, errors)
        if data is None:
            plans_ok = plans_ok and name != "plan"
            continue
        before = len(errors)
        validate(data, schema, "$", errors)
        errors[before:] = [f"{label}: {e}" for e in errors[before:]]
        if len(errors) == before:
            if name == "plan":
                plans[label] = data
            else:
                docs[name] = data
        elif name == "plan":
            plans_ok = False
    zone_ids = None
    if "zones" in schemas:
        zone_ids = set(schemas["zones"]["properties"]["zones"]["items"]["properties"]["id"]["enum"])
    check_rules(docs, plans, zone_ids, plans_ok, errors)
    return errors


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = list(argv)
    schemas_dir = None
    if "--schemas" in args:
        i = args.index("--schemas")
        if i + 1 >= len(args):
            print("--schemas: нужен путь", file=sys.stderr)
            return 2
        schemas_dir = Path(args[i + 1])
        del args[i : i + 2]
    if len(args) > 1:
        print(__doc__, file=sys.stderr)
        return 2
    content_dir = Path(args[0]) if args else Path("content")
    schemas_dir = schemas_dir or Path("content/schemas")
    errors = check(content_dir, schemas_dir)
    for e in errors:
        print(f"{content_dir}/{e}", file=sys.stderr)
    if errors:
        print(f"content: ошибок — {len(errors)}", file=sys.stderr)
        return 1
    print(f"content: {content_dir} по схемам — ок")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


def content_directory():
    return Path(os.environ.get("CONTENT_DIR", Path(__file__).resolve().parents[3] / "content"))


def document_errors(body, shapes_only=False):
    """Validate an in-memory document using the same canonical schemas and rules as the CLI."""
    errors, docs, plans = [], {}, {}
    schemas_dir = content_directory() / "schemas"
    schemas = {}
    for name in FILES:
        schema = load(schemas_dir / f"{name}.schema.json", f"schemas/{name}.schema.json", errors)
        if schema is not None:
            schema_keywords(schema, name, errors)
            schemas[name] = schema
    if errors:
        raise RuntimeError("; ".join(errors))
    for name in (*FILES, "plan"):
        before = len(errors)
        validate(body.get(name), PLAN_SHAPE if name == "plan" else schemas[name], "$", errors)
        errors[before:] = [f"{name}.json: {error}" for error in errors[before:]]
        if len(errors) == before:
            if name == "plan":
                plans["plan.json"] = body[name]
            else:
                docs[name] = body[name]
    if not shapes_only and not errors:
        zone_ids = set(schemas["zones"]["properties"]["zones"]["items"]["properties"]["id"]["enum"])
        check_rules(docs, plans, zone_ids, True, errors)
    return errors
