"""add_payload_privacy_settings

Revision ID: 2e6a4d9c8b10
Revises: 0f4d3c2b1a9e
Create Date: 2026-07-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e6a4d9c8b10"
down_revision: str | Sequence[str] | None = "0f4d3c2b1a9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "projects",
        sa.Column(
            "payload_storage_mode",
            sa.String(length=20),
            server_default="all",
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "payload_max_bytes",
            sa.Integer(),
            server_default="262144",
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "payload_redact_keys",
            sa.Text(),
            server_default="api_key,password,secret,token,authorization",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_projects_payload_storage_mode",
        "projects",
        "payload_storage_mode IN ('all', 'errors', 'none')",
    )
    op.create_check_constraint(
        "ck_projects_payload_max_bytes",
        "projects",
        "payload_max_bytes >= 0 AND payload_max_bytes <= 10485760",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_projects_payload_max_bytes", "projects", type_="check")
    op.drop_constraint("ck_projects_payload_storage_mode", "projects", type_="check")
    op.drop_column("projects", "payload_redact_keys")
    op.drop_column("projects", "payload_max_bytes")
    op.drop_column("projects", "payload_storage_mode")
