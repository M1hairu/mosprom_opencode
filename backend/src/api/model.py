"""SQLAlchemy 2 ORM models. Alembic migrations (backend/migrations) follow this metadata."""

import os
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL не задан: make demo передаёт его из .env")
    return url


class Base(DeclarativeBase):
    pass


class Site(Base):
    """Showroom site. Every product table refers to it by site_id; the demo has one site."""

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
