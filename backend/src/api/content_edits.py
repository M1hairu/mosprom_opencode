"""Add and delete a fact or a catalog exhibit (#274). Each change is a new draft version.

The change starts from the newest version of the site (draft or published), as the admin
shows it. A new entry passes the canonical schema and content rules (G1, G4, G14, brand).
An entry that zones, routes or the plan still use is not deleted: 409 lists the places.
"""

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from api.content_validation import check_rules, content_directory, validate
from api.contracts import SiteDocument, SiteDocumentVersion
from api.site_documents import Db, Editor, append_version, commit, latest, lock_site, response
from api.visit_contracts import Slug

router = APIRouter(prefix="/api/sites/{site_id}")

# Section of the document, list key, content file, field the id is made from.
KINDS = {
    "fact": ("facts", "facts", "facts.json", "text"),
    "item": ("catalog", "items", "catalog.json", "name"),
}
LATIN = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщыэюя",
        [
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "e",
            "zh",
            "z",
            "i",
            "i",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "kh",
            "ts",
            "ch",
            "sh",
            "shch",
            "y",
            "e",
            "iu",
            "ia",
        ],
        strict=True,
    )
) | {"ъ": "", "ь": ""}


def slug(text: str) -> str:
    """Code of a new entry from its text: the first four words in Latin letters."""
    latin = "".join(LATIN.get(c, c) for c in text.lower())
    return "_".join(re.findall(r"[a-z0-9]+", latin)[:4]) or "entry"


def current(session: Session, site_id: str) -> dict[str, Any]:
    lock_site(session, site_id)
    row = latest(session, site_id)
    if row is None:
        raise HTTPException(404, "Документ площадки не найден")
    return row.body


def entry_errors(kind: str, entry: dict[str, Any], body: dict[str, Any]) -> list[str]:
    section, key, label, _ = KINDS[kind]
    schema = json.loads(
        (content_directory() / "schemas" / f"{section}.schema.json").read_text("utf-8")
    )
    errors: list[str] = []
    one = {"version": 1, key: [entry]}
    validate(one, schema, "$", errors)
    if not errors:
        check_rules({section: one}, {"plan.json": body["plan"]}, None, True, errors)
    prefix = re.compile(rf"^({re.escape(label)}: )?\$\.{key}\[0\]\.?(: )?")
    # Rules on the plan itself are not the new entry's errors.
    return [prefix.sub("", e) for e in errors if prefix.match(e)]


def usage(kind: str, entry_id: str, body: dict[str, Any]) -> list[str]:
    """Places that use the entry: texts of zones and routes, zone exhibits, plan objects."""
    token = f"{{{{{kind}:{entry_id}}}}}"
    places = [
        f"зона «{z['name']}»"
        for z in body["zones"]["zones"]
        if token in json.dumps(z, ensure_ascii=False)
        or (kind == "item" and entry_id in z["exhibits"])
    ]
    places += [
        f"маршрут «{r['title']}»"
        for r in body["routes"]["routes"]
        if token in json.dumps(r, ensure_ascii=False)
    ]
    if kind == "item":
        item = next(i for i in body["catalog"]["items"] if i["id"] == entry_id)
        objects = [o for o in body["plan"]["objects"] if o["typeId"] == item.get("plan_type")]
        if objects:
            places.append(f"план: объектов — {len(objects)}")
    return places


def save(session: Session, site_id: str, body: dict[str, Any], author: str):
    row = append_version(session, site_id, SiteDocument.model_validate(body), "draft", author)
    commit(session)
    return response(row)


def add(kind: str, site_id: str, entry: dict[str, Any], session: Session, user):
    section, key, _, source = KINDS[kind]
    body = current(session, site_id)
    entries = body[section][key]
    ids = {e["id"] for e in entries}
    if entry.get("id") in ids:
        raise HTTPException(409, f"Код «{entry['id']}» уже занят")
    if not entry.get("id") and isinstance(entry.get(source), str):
        base = entry["id"] = slug(entry[source])
        n = 1
        while entry["id"] in ids:
            n += 1
            entry["id"] = f"{base}_{n}"
    errors = entry_errors(kind, entry, body)
    if errors:
        raise HTTPException(422, {"errors": errors})
    entries.append(entry)
    return save(session, site_id, body, user.role)


def remove(kind: str, site_id: str, entry_id: str, session: Session, user):
    section, key, _, _ = KINDS[kind]
    body = current(session, site_id)
    entries = body[section][key]
    if all(e["id"] != entry_id for e in entries):
        raise HTTPException(404, f"Нет записи «{entry_id}»")
    places = usage(kind, entry_id, body)
    if places:
        raise HTTPException(409, {"message": "Запись используется", "usage": places})
    body[section][key] = [e for e in entries if e["id"] != entry_id]
    return save(session, site_id, body, user.role)


@router.post("/facts")
def add_fact(site_id: Slug, fact: dict[str, Any], session: Db, user: Editor) -> SiteDocumentVersion:
    return add("fact", site_id, fact, session, user)


@router.delete("/facts/{fact_id}")
def delete_fact(site_id: Slug, fact_id: str, session: Db, user: Editor) -> SiteDocumentVersion:
    return remove("fact", site_id, fact_id, session, user)


@router.post("/items")
def add_item(site_id: Slug, item: dict[str, Any], session: Db, user: Editor) -> SiteDocumentVersion:
    return add("item", site_id, item, session, user)


@router.delete("/items/{item_id}")
def delete_item(site_id: Slug, item_id: str, session: Db, user: Editor) -> SiteDocumentVersion:
    return remove("item", site_id, item_id, session, user)
