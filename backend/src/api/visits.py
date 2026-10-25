"""Visits, guest events, SSE streams of the zone screen and of the tablet.

The guest is anonymous: the visit token is the only identity (D-008). A zone link
`/z/<site>/<zone>?src=qr|nfc` opens the SPA; the guide then calls POST /api/visits (no token yet)
and POST /api/events with kind `arrive`, so QR and NFC give one event.
"""

import secrets
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import auth, db
from api.broker import broker
from api.visit_contracts import (
    EventIn,
    EventMessage,
    EventOut,
    ManualEventIn,
    RoleChange,
    RoleMessage,
    ScreenMessage,
    SiteStreamMessage,
    Slug,
    VisitCreate,
    VisitCreated,
    VisitInfo,
)
from api.visit_model import GuestEvent, Visit, ZoneScreen

router = APIRouter()

Db = Annotated[Session, Depends(db.get_session)]


def utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; PostgreSQL returns aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def screen_message(session: Session, site_id: str, zone_id: str) -> ScreenMessage:
    row = session.get(ZoneScreen, (site_id, zone_id))
    visit = session.get(Visit, row.visit_id) if row else None
    return ScreenMessage(
        site_id=site_id,
        zone_id=zone_id,
        visit_id=visit.id if visit else None,
        role=visit.role if visit else None,
        since=utc(row.since) if row else None,
    )


def publish_screen(message: ScreenMessage) -> None:
    broker.publish((message.site_id, message.zone_id), message)
    broker.publish((message.site_id,), message)


@router.post("/api/visits")
def create_visit(body: VisitCreate, session: Db) -> VisitCreated:
    visit = Visit(
        id=uuid.uuid4().hex,
        token=secrets.token_urlsafe(32),  # secret-scan: allow
        site_id=body.site_id,
        role=body.role,
    )
    session.add(visit)
    session.commit()
    return VisitCreated(
        visit_id=visit.id, token=visit.token, site_id=visit.site_id, role=visit.role
    )


@router.get("/api/visits", dependencies=[Depends(auth.reader)])
def list_visits(
    session: Db, site_id: Slug, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[VisitInfo]:
    """Newest visits first: the tablet picks a guest to change the role or to lead."""
    arrive = (GuestEvent.visit_id == Visit.id) & (GuestEvent.kind == "arrive")
    last_zone = (
        select(GuestEvent.zone_id)
        .where(arrive)
        .order_by(GuestEvent.occurred_at.desc(), GuestEvent.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    last_at = (
        select(GuestEvent.occurred_at)
        .where(GuestEvent.visit_id == Visit.id)
        .order_by(GuestEvent.occurred_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = session.execute(
        select(Visit, last_zone, last_at)
        .where(Visit.site_id == site_id)
        .order_by(Visit.created_at.desc())
        .limit(limit)
    )
    return [
        VisitInfo(
            visit_id=visit.id,
            role=visit.role,
            created_at=utc(visit.created_at),
            last_zone_id=zone_id,
            last_event_at=utc(at) if at else None,
        )
        for visit, zone_id, at in rows
    ]


@router.put("/api/visits/{visit_id}/role", dependencies=[Depends(auth.manager)])
def change_role(visit_id: str, body: RoleChange, session: Db) -> RoleChange:
    visit = session.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(404, "Визит не найден")
    visit.role = body.role
    session.commit()
    broker.publish(
        (visit.site_id,), RoleMessage(site_id=visit.site_id, visit_id=visit.id, role=visit.role)
    )
    # A screen that shows this guest changes its content with the role.
    for row in session.scalars(select(ZoneScreen).where(ZoneScreen.visit_id == visit.id)):
        publish_screen(screen_message(session, row.site_id, row.zone_id))
    return RoleChange(role=visit.role)


def take_screen(session: Session, visit: Visit, zone_id: str, at: datetime) -> ScreenMessage | None:
    """The latest scan wins by event time: a late replay of an old scan does not take the screen."""
    # The client clock must not lock the screen: a scan "from 2099" would win for ever.
    at = min(at, datetime.now(UTC))
    for _ in range(2):  # the second round covers two first scans of a zone at the same moment
        row = session.get(ZoneScreen, (visit.site_id, zone_id), with_for_update=True)
        if row is None:
            session.add(
                ZoneScreen(site_id=visit.site_id, zone_id=zone_id, visit_id=visit.id, since=at)
            )
        elif at >= utc(row.since):
            row.visit_id, row.since = visit.id, at
        else:
            session.rollback()
            return None
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            continue
        return screen_message(session, visit.site_id, zone_id)
    return None


def write_event(session: Session, visit: Visit, body: EventIn | ManualEventIn) -> EventOut:
    """One event of a guest: written once per client_event_id, sent to the tablet and the screen."""
    same_id = (GuestEvent.visit_id == visit.id) & (
        GuestEvent.client_event_id == body.client_event_id
    )
    existing = session.scalar(select(GuestEvent).where(same_id))
    if existing:
        return EventOut(event_id=existing.id, duplicate=True)
    event = GuestEvent(
        visit_id=visit.id,
        site_id=visit.site_id,
        zone_id=body.zone_id,
        kind=body.kind,
        src=body.src,
        client_event_id=body.client_event_id,
        occurred_at=body.occurred_at,
    )
    session.add(event)
    try:
        session.commit()
    except IntegrityError:  # the same event came twice at once
        session.rollback()
        existing = session.scalar(select(GuestEvent).where(same_id))
        if existing is None:
            raise
        return EventOut(event_id=existing.id, duplicate=True)
    broker.publish(
        (visit.site_id,),
        EventMessage(
            event_id=event.id,
            site_id=visit.site_id,
            visit_id=visit.id,
            role=visit.role,
            zone_id=event.zone_id,
            kind=body.kind,
            src=body.src,
            occurred_at=body.occurred_at,
        ),
    )
    if body.kind == "arrive" and body.zone_id:
        screen = take_screen(session, visit, body.zone_id, body.occurred_at)
        if screen:
            publish_screen(screen)
    return EventOut(event_id=event.id, duplicate=False)


@router.post("/api/events")
def post_event(body: EventIn, session: Db) -> EventOut:
    visit = session.scalar(select(Visit).where(Visit.token == body.visit_token))
    if visit is None:
        raise HTTPException(404, "Визит не найден")
    return write_event(session, visit, body)


@router.post("/api/visits/{visit_id}/events", dependencies=[Depends(auth.manager)])
def post_manual_event(visit_id: str, body: ManualEventIn, session: Db) -> EventOut:
    """The tablet leads a guest: `arrive` puts the guest's content on the zone screen."""
    visit = session.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(404, "Визит не найден")
    return write_event(session, visit, body)


def read_screen(site_id: str, zone_id: str) -> ScreenMessage:
    with Session(db.engine()) as session:
        return screen_message(session, site_id, zone_id)


@router.get("/api/sites/{site_id}/zones/{zone_id}/stream", response_class=EventSourceResponse)
async def zone_stream(site_id: Slug, zone_id: Slug) -> AsyncIterator[ScreenMessage]:
    """Zone screen: the current owner at once, then every change."""
    subscriber = broker.subscribe(site_id, zone_id)  # before the read: no change is lost
    try:
        yield await anyio.to_thread.run_sync(read_screen, site_id, zone_id)
        while True:
            yield await subscriber.queue.get()
    finally:
        broker.unsubscribe(subscriber)


@router.get(
    "/api/sites/{site_id}/stream",
    response_class=EventSourceResponse,
    dependencies=[Depends(auth.reader)],
)
async def site_stream(site_id: Slug) -> AsyncIterator[SiteStreamMessage]:
    """Tablet: every guest event, role change and screen change of the site."""
    subscriber = broker.subscribe(site_id)
    try:
        while True:
            yield await subscriber.queue.get()
    finally:
        broker.unsubscribe(subscriber)
