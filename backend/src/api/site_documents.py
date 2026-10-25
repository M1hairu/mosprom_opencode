"""Versioned site documents, validated publication and non-destructive rollback (#36)."""

from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import auth, db
from api.content_validation import document_errors
from api.contracts import (
    DocumentVersion,
    Finding,
    PlanDocument,
    SiteDocument,
    SiteDocumentVersion,
    VersionInput,
)
from api.model import Site
from api.site_model import SiteDocumentRow
from api.validation import validate_plan
from api.visit_contracts import Slug

router = APIRouter(prefix="/api/sites/{site_id}")
Db = Annotated[Session, Depends(db.get_session)]
Editor = Annotated[auth.Identity, Depends(auth.editor)]
Reader = Annotated[auth.Identity, Depends(auth.identity)]


def findings(body: SiteDocument) -> list[Finding]:
    errors = document_errors(body.model_dump(mode="json"))
    content = [
        Finding(code="CONTENT_INVALID", severity="error", message=e, refs=[]) for e in errors
    ]
    return [*content, *validate_plan(PlanDocument.model_validate(body.plan))]


def latest(session: Session, site_id: str, status: str | None = None) -> SiteDocumentRow | None:
    query = select(SiteDocumentRow).where(SiteDocumentRow.site_id == site_id)
    if status:
        query = query.where(SiteDocumentRow.status == status)
    return session.scalar(query.order_by(SiteDocumentRow.version.desc()).limit(1))


def version(session: Session, site_id: str, number: int) -> SiteDocumentRow:
    row = session.get(SiteDocumentRow, (site_id, number))
    if row is None:
        raise HTTPException(404, "Версия документа не найдена")
    return row


def lock_site(session: Session, site_id: str) -> Site:
    # Parent row serializes version allocation across API workers in PostgreSQL.
    site = session.scalar(select(Site).where(Site.id == site_id).with_for_update())
    if site is None:
        site = Site(id=site_id, name=site_id)
        session.add(site)
        session.flush()  # concurrent first writer gets an integrity conflict, never overwrites
    return site


def append_version(session: Session, site_id: str, body: SiteDocument, status: str, author: str):
    lock_site(session, site_id)
    number = (
        session.scalar(
            select(func.max(SiteDocumentRow.version)).where(SiteDocumentRow.site_id == site_id)
        )
        or 0
    )
    row = SiteDocumentRow(
        site_id=site_id,
        version=number + 1,
        status=status,
        body=body.model_dump(mode="json"),
        author=author,
    )
    session.add(row)
    session.flush()
    return row


def metadata(row: SiteDocumentRow) -> DocumentVersion:
    at = row.created_at
    return DocumentVersion(
        site_id=row.site_id,
        version=row.version,
        status=row.status,
        author=row.author,
        created_at=at if at.tzinfo else at.replace(tzinfo=UTC),
    )


def response(row: SiteDocumentRow, checked: list[Finding] | None = None) -> SiteDocumentVersion:
    body = SiteDocument.model_validate(row.body)
    return SiteDocumentVersion(
        **metadata(row).model_dump(),
        body=body,
        findings=findings(body) if checked is None else checked,
    )


def commit(session: Session):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Документ изменён параллельно. Повторите запрос.") from exc


@router.get("/document")
def published_document(site_id: Slug, session: Db) -> SiteDocumentVersion:
    row = latest(session, site_id, "published")
    if row is None:
        raise HTTPException(404, "Опубликованный документ не найден")
    return response(row)


@router.get("/draft")
def draft_document(site_id: Slug, session: Db, user: Editor) -> SiteDocumentVersion:
    row = latest(session, site_id, "draft")
    if row is None:
        raise HTTPException(404, "Черновик не найден")
    return response(row)


@router.put("/draft")
def save_draft(site_id: Slug, body: SiteDocument, session: Db, user: Editor) -> SiteDocumentVersion:
    checked = findings(body)
    try:
        row = append_version(session, site_id, body, "draft", user.role)
        commit(session)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Документ изменён параллельно. Повторите запрос.") from exc
    return response(row, checked)


@router.get("/versions")
def list_versions(site_id: Slug, session: Db, user: Reader) -> list[DocumentVersion]:
    rows = session.scalars(
        select(SiteDocumentRow)
        .where(SiteDocumentRow.site_id == site_id)
        .order_by(SiteDocumentRow.version.desc())
    )
    return [metadata(row) for row in rows]


def publish_version(site_id: str, number: int, session: Session, user: auth.Identity):
    source = version(session, site_id, number)
    body = SiteDocument.model_validate(source.body)
    checked = findings(body)
    if any(f.severity == "error" for f in checked):
        raise HTTPException(422, {"findings": [f.model_dump() for f in checked]})
    try:
        row = append_version(session, site_id, body, "published", user.role)
        commit(session)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Документ изменён параллельно. Повторите запрос.") from exc
    return response(row, checked)


@router.post("/publish")
def publish_document(
    site_id: Slug, body: VersionInput, session: Db, user: Editor
) -> SiteDocumentVersion:
    return publish_version(site_id, body.version, session, user)


@router.post("/rollback")
def rollback_document(
    site_id: Slug, body: VersionInput, session: Db, user: Editor
) -> SiteDocumentVersion:
    return publish_version(site_id, body.version, session, user)
