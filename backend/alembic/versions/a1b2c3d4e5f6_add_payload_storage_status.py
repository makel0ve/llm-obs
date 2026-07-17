"""add_payload_storage_status

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9d0
Create Date: 2026-07-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("spans", sa.Column("payload_status", sa.String(length=30)))
    op.add_column("spans", sa.Column("payload_drop_reason", sa.String(length=100)))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("spans", "payload_drop_reason")
    op.drop_column("spans", "payload_status")
