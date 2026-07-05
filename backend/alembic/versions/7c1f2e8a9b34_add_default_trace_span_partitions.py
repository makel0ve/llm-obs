"""add_default_trace_span_partitions

Revision ID: 7c1f2e8a9b34
Revises: bf79868b5f76
Create Date: 2026-07-05 13:20:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1f2e8a9b34"
down_revision: str | Sequence[str] | None = "bf79868b5f76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS spans_default
            PARTITION OF spans DEFAULT
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS traces_default
            PARTITION OF traces DEFAULT
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS spans_default")
    op.execute("DROP TABLE IF EXISTS traces_default")
