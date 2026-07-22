"""add_span_metric_buckets

Revision ID: e9a1b2c3d4f5
Revises: d8e7f6a5b4c3
Create Date: 2026-07-22 16:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9a1b2c3d4f5"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d8e7f6a5b4c3"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "span_metric_buckets",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("bucket_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "span_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "error_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_cost_usd",
            sa.Numeric(precision=18, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "latency_sum_ms",
            sa.Numeric(precision=18, scale=3),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("TIMEZONE('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("TIMEZONE('utc', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "bucket_start"),
    )
    op.create_index(
        "idx_span_metric_buckets_project_time",
        "span_metric_buckets",
        ["project_id", sa.text("bucket_start DESC")],
    )
    op.execute("ALTER TABLE span_metric_buckets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE span_metric_buckets FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY span_metric_buckets_project_isolation
            ON span_metric_buckets
            USING (
                current_setting('app.current_project_id', true) <> ''
                AND project_id::text = current_setting('app.current_project_id', true)
            )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP POLICY IF EXISTS span_metric_buckets_project_isolation "
        "ON span_metric_buckets"
    )
    op.drop_index(
        "idx_span_metric_buckets_project_time", table_name="span_metric_buckets"
    )
    op.drop_table("span_metric_buckets")
