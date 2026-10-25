"""Immutable versions of site documents. JSONB in PostgreSQL, JSON in SQLite tests."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.model import Base


class SiteDocumentRow(Base):
    __tablename__ = "site_documents"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_site_documents_version"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_site_documents_status"),
    )

    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    body: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
