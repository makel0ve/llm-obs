"""add_failed_task_scope

Revision ID: 4a6c9d2e1f03
Revises: 7c1f2e8a9b34
Create Date: 2026-07-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a6c9d2e1f03"
down_revision: str | Sequence[str] | None = "7c1f2e8a9b34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("failed_tasks", sa.Column("org_id", sa.UUID(), nullable=True))
    op.add_column("failed_tasks", sa.Column("project_id", sa.UUID(), nullable=True))
    op.create_index("idx_failed_tasks_org", "failed_tasks", ["org_id", "resolved"])
    op.create_index(
        "idx_failed_tasks_project", "failed_tasks", ["project_id", "resolved"]
    )
    op.create_foreign_key(
        "fk_failed_tasks_org",
        "failed_tasks",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_failed_tasks_project",
        "failed_tasks",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_failed_tasks_project", "failed_tasks", type_="foreignkey")
    op.drop_constraint("fk_failed_tasks_org", "failed_tasks", type_="foreignkey")
    op.drop_index("idx_failed_tasks_project", table_name="failed_tasks")
    op.drop_index("idx_failed_tasks_org", table_name="failed_tasks")
    op.drop_column("failed_tasks", "project_id")
    op.drop_column("failed_tasks", "org_id")
