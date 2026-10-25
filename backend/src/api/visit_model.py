"""Visits, guest events and zone screens. site_id and zone_id are plain strings: the tables do
not depend on the site document (#36). A guest is anonymous: the token is the only identity."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.model import Base


class Visit(Base):
    __tablename__ = "visits"

    # id is public (screens and the tablet see it); token is the secret of the guest's phone.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    site_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuestEvent(Base):
    __tablename__ = "guest_events"
    __table_args__ = (
        # The guide queue resends after a lost network: the same id must not write twice.
        UniqueConstraint("visit_id", "client_event_id"),
        Index("ix_guest_events_site_visit_time", "site_id", "visit_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"))
    site_id: Mapped[str] = mapped_column(String(64))
    zone_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    src: Mapped[str] = mapped_column(String(8))
    client_event_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ZoneScreen(Base):
    """Whose content is on the zone screen. The latest scan wins (by occurred_at)."""

    __tablename__ = "zone_screens"

    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    zone_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"))
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
