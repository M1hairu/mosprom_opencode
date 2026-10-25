"""Load checked content into hall-219, once per distinct seed body."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import db
from api.content_validation import PLAN_GLOB, content_directory
from api.contracts import SiteDocument
from api.site_documents import append_version, findings, latest, lock_site
from api.site_model import SiteDocumentRow


def chosen_plan(directory: Path, plan: str) -> dict:
    """The chosen plan with object types of every content plan (#131).

    catalog.json is shared by all plan*.json, and the CLI checks plan_type against all of
    them. The base hall places no exhibits, so its own type list lacks catalog types.
    Walls, zones and objects stay those of the chosen plan, so norm checks see it as is.
    """
    body = json.loads((directory / plan).read_text("utf-8"))
    types = body["catalog"]["objectTypes"]
    known = {kind["id"] for kind in types}
    for path in sorted(directory.glob(PLAN_GLOB)):
        for kind in json.loads(path.read_text("utf-8"))["catalog"]["objectTypes"]:
            if kind["id"] not in known:
                types.append(kind)
                known.add(kind["id"])
    return body


def seed(session: Session, directory: Path, site_id: str = "hall-219", plan: str = "plan-219.json"):
    body = SiteDocument.model_validate(
        {
            "plan": chosen_plan(directory, plan),
            **{
                name: json.loads((directory / f"{name}.json").read_text("utf-8"))
                for name in ("zones", "routes", "facts", "catalog")
            },
        }
    )
    checked = findings(body)
    try:
        lock_site(session, site_id)
        # Compare all previous imports, not just the current publication. A repeated seed must
        # not replace a newer editor publication with old bundled content.
        imported = session.scalars(
            select(SiteDocumentRow)
            .where(SiteDocumentRow.site_id == site_id, SiteDocumentRow.author == "seed")
            .order_by(SiteDocumentRow.version.desc())
        )
        raw = body.model_dump(mode="json")
        for previous in imported:
            if previous.body == raw:
                session.rollback()
                return previous, False
        # Content changes after the first publication are drafts. Human edits stay published.
        # Draft-only history (an invalid earlier import) does not block a valid one.
        existing = latest(session, site_id, "published")
        status = (
            "published"
            if existing is None and not any(f.severity == "error" for f in checked)
            else "draft"
        )
        row = append_version(session, site_id, body, status, "seed")
        session.commit()
        return row, True
    except IntegrityError as exc:
        session.rollback()
        raise RuntimeError("Параллельный импорт: повторите make seed") from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", type=Path, default=content_directory())
    parser.add_argument("--plan", default="plan-219.json")
    args = parser.parse_args()
    with Session(db.engine(), expire_on_commit=False) as session:
        row, created = seed(session, args.content, plan=args.plan)
        print(f"seed: {row.site_id} version={row.version} status={row.status} created={created}")
        for finding in findings(SiteDocument.model_validate(row.body)):
            print(f"{finding.severity} {finding.code}: {finding.message}")


if __name__ == "__main__":
    main()
