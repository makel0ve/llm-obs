"""add_audit_log_id_sequence

Revision ID: 6d4b8a2e9c11
Revises: 2e6a4d9c8b10
Create Date: 2026-07-09 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d4b8a2e9c11"
down_revision: str | Sequence[str] | None = "2e6a4d9c8b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS audit_log_id_seq")
    op.execute(
        """
        SELECT setval(
            'audit_log_id_seq',
            COALESCE((SELECT MAX(id) FROM audit_log), 0) + 1,
            false
        )
        """
    )
    op.execute(
        """
        ALTER TABLE audit_log
        ALTER COLUMN id SET DEFAULT nextval('audit_log_id_seq')
        """
    )
    op.execute("ALTER SEQUENCE audit_log_id_seq OWNED BY audit_log.id")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE audit_log ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS audit_log_id_seq")
