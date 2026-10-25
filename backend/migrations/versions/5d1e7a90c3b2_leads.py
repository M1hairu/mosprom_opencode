"""leads

Revision ID: 5d1e7a90c3b2
Revises: 8bc24a36d001
"""

import sqlalchemy as sa
from alembic import op

revision = "5d1e7a90c3b2"
down_revision = "8bc24a36d001"
branch_labels = None
depends_on = None


def upgrade():
    now = sa.func.now()
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.String(64), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("material", sa.String(200), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.Column("p_material", sa.String(200)),
        sa.Column("p_thickness_mm", sa.Float()),
        sa.Column("p_machine", sa.String(100)),
        sa.Column("p_mode", sa.String(100)),
        sa.Column("p_time_min", sa.Float()),
        sa.Column("p_edge_photo_url", sa.String(500)),
        sa.Column("p_filled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_leads_site_id", "leads", ["site_id"])


def downgrade():
    op.drop_index("ix_leads_site_id", table_name="leads")
    op.drop_table("leads")
