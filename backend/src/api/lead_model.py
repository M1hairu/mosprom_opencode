"""Guest leads and the test protocol filled by the manager (#31). One row per lead.
The protocol columns stay empty until the manager fills them."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.model import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32))
    company: Mapped[str] = mapped_column(String(200))
    material: Mapped[str] = mapped_column(String(200))
    task: Mapped[str] = mapped_column(Text)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consent_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Test protocol. p_mode is a machine mode or "оценка".
    p_material: Mapped[str | None] = mapped_column(String(200))
    p_thickness_mm: Mapped[float | None] = mapped_column()
    p_machine: Mapped[str | None] = mapped_column(String(100))
    p_mode: Mapped[str | None] = mapped_column(String(100))
    p_time_min: Mapped[float | None] = mapped_column()
    p_edge_photo_url: Mapped[str | None] = mapped_column(String(500))
    p_filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
