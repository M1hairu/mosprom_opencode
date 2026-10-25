"""GET /api/analytics: SQL over guest events — time in zones and the visit-to-lead funnel."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import DateTime, Integer, cast, distinct, func, select
from sqlalchemy.orm import Session

from api import db
from api.visit_contracts import Analytics, FunnelStep, Slug, ZoneTime
from api.visit_model import GuestEvent, Visit

router = APIRouter()

Db = Annotated[Session, Depends(db.get_session)]


def epoch(session: Session, column):
    """Seconds since 1970; PostgreSQL in production, SQLite in tests."""
    if session.get_bind().dialect.name == "postgresql":
        return func.extract("epoch", column)
    return cast(func.strftime("%s", column), Integer)


@router.get("/api/analytics")
def analytics(session: Db, site_id: Slug) -> Analytics:
    """A stay is the time from an `arrive` event to the next event of the same visit (arrive,
    leave or lead). The last `arrive` of a visit has no end and is not counted."""
    seq = (
        select(
            GuestEvent.visit_id,
            GuestEvent.zone_id,
            GuestEvent.kind,
            GuestEvent.occurred_at.label("at"),
            func.lead(GuestEvent.occurred_at, type_=DateTime(timezone=True))
            .over(
                partition_by=GuestEvent.visit_id,
                order_by=(GuestEvent.occurred_at, GuestEvent.id),
            )
            .label("next_at"),
        )
        .where(GuestEvent.site_id == site_id)
        .subquery()
    )
    seconds = func.sum(epoch(session, seq.c.next_at) - epoch(session, seq.c.at))
    stays = session.execute(
        select(seq.c.zone_id, func.count(distinct(seq.c.visit_id)), func.count(), seconds)
        .where(seq.c.kind == "arrive", seq.c.next_at.is_not(None))
        .group_by(seq.c.zone_id)
        .order_by(seconds.desc(), seq.c.zone_id)
    )
    zones = [
        ZoneTime(
            zone_id=zone_id,
            visits=visits,
            seconds_total=round(total),
            seconds_avg=round(total / count),
        )
        for zone_id, visits, count, total in stays
    ]

    def visits_with(kind: str) -> int:
        return session.scalar(
            select(func.count(distinct(GuestEvent.visit_id))).where(
                GuestEvent.site_id == site_id, GuestEvent.kind == kind
            )
        )

    all_visits = session.scalar(
        select(func.count()).select_from(Visit).where(Visit.site_id == site_id)
    )
    funnel = [
        FunnelStep(step="visit", visits=all_visits),
        FunnelStep(step="zone", visits=visits_with("arrive")),
        FunnelStep(step="lead", visits=visits_with("lead")),
    ]
    return Analytics(site_id=site_id, zones=zones, funnel=funnel)
