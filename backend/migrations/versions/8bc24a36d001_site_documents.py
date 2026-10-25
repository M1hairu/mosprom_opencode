"""site documents

Revision ID: 8bc24a36d001
Revises: 28af29cda545
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "8bc24a36d001"
down_revision = "28af29cda545"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_documents",
        sa.Column("site_id", sa.String(64), sa.ForeignKey("sites.id"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("body", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("author", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_site_documents_version"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_site_documents_status"),
    )


def downgrade():
    op.drop_table("site_documents")
