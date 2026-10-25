"""Migrations render to PostgreSQL SQL without a server (alembic offline mode)."""

import io
from pathlib import Path

from alembic import command
from alembic.config import Config

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_upgrade_head_renders_postgres_sql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    out = io.StringIO()
    command.upgrade(Config(toml_file=PYPROJECT, output_buffer=out), "head", sql=True)
    assert "CREATE TABLE sites" in out.getvalue()
