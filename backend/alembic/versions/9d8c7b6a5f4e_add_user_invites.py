"""add_user_invites

Revision ID: 9d8c7b6a5f4e
Revises: 4a6c9d2e1f03
Create Date: 2026-07-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d8c7b6a5f4e"
down_revision: str | Sequence[str] | None = "4a6c9d2e1f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("TIMEZONE('utc', now())"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'member', 'viewer')",
            name="ck_organization_invites_role",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_org_invites_org_created",
        "organization_invites",
        ["org_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_org_invites_pending_email",
        "organization_invites",
        ["org_id", "email"],
        postgresql_where=sa.text("accepted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_org_invites_pending_email", table_name="organization_invites")
    op.drop_index("idx_org_invites_org_created", table_name="organization_invites")
    op.drop_table("organization_invites")
