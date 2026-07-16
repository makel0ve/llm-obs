"""add_invite_project_assignments

Revision ID: c7e4a9b2d135
Revises: 8f2c1d4e9a7b
Create Date: 2026-07-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e4a9b2d135"
down_revision: str | Sequence[str] | None = "8f2c1d4e9a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "organization_invites",
        sa.Column(
            "project_assignments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("organization_invites", "project_assignments")
